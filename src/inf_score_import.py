"""INF resource import report generation and Discord notification."""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import logging
import os
import pickle
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

ALIAS_SCOPE_INF = "inf"
TRACKER_TITLE_COLUMN = "title"
DISCORD_SAFE_LIMIT = 1900
UNMATCHED_TOP_N = 10

LOGGER = logging.getLogger(__name__)


def now_utc_iso() -> str:
    """Return current UTC timestamp in ISO8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_inf_alias_map(conn: sqlite3.Connection) -> dict[str, str]:
    """Load INF alias map and return `alias -> textage_id`."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT alias, textage_id
        FROM music_title_alias
        WHERE alias_scope = ?
          AND alias_type IN ('official', 'manual')
        """,
        (ALIAS_SCOPE_INF,),
    )
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError(
            "music_title_alias alias_scope='inf' with alias_type in (official, manual) has no rows; "
            "run alias generation first"
        )

    return {str(alias): str(textage_id) for alias, textage_id in rows}


def _sorted_unmatched(counter: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def load_tracker_titles(tracker_tsv_path: str) -> list[str]:
    """Load tracker.tsv and return titles from the `title` column."""
    try:
        with open(tracker_tsv_path, "r", encoding="utf-8-sig", newline="") as file_obj:
            reader = csv.DictReader(file_obj, delimiter="\t")
            if not reader.fieldnames or TRACKER_TITLE_COLUMN not in reader.fieldnames:
                raise RuntimeError(
                    f"tracker TSV missing required column: {TRACKER_TITLE_COLUMN}"
                )

            return [
                str(row[TRACKER_TITLE_COLUMN]).strip()
                if row[TRACKER_TITLE_COLUMN] is not None
                else ""
                for row in reader
            ]
    except RuntimeError:
        raise
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise RuntimeError(f"Failed to read tracker TSV: {tracker_tsv_path}") from exc


class _FakeNumpyDType:
    """Minimal stub for numpy.dtype used by inf-notebook pickle resources."""

    def __init__(self, *_args: Any):
        self.state: Any = None

    def __setstate__(self, state: Any) -> None:
        self.state = state


class _FakeNumpyNdArray:
    """Minimal stub for numpy.ndarray used by inf-notebook pickle resources."""

    def __init__(self, shape: Any = None, dtype: Any = None):
        self.shape = shape
        self.dtype = dtype
        self.state: Any = None

    def __setstate__(self, state: Any) -> None:
        self.state = state

    def reshape(self, *shape: Any) -> "_FakeNumpyNdArray":
        """Mimic ndarray.reshape for pickle compatibility."""
        if len(shape) == 1 and isinstance(shape[0], tuple):
            self.shape = shape[0]
        else:
            self.shape = shape
        return self


def _safe_numpy_scalar(_dtype: Any, raw_bytes: Any) -> Any:
    """Decode simple scalar payloads found in resources without numpy runtime."""
    if isinstance(raw_bytes, (bytes, bytearray)) and len(raw_bytes) in (1, 2, 4, 8):
        return int.from_bytes(raw_bytes, "little", signed=False)
    return raw_bytes


def _safe_numpy_reconstruct(_subtype: Any, shape: Any, dtype: Any) -> _FakeNumpyNdArray:
    """Reconstruct ndarray object as a harmless stub instance."""
    return _FakeNumpyNdArray(shape=shape, dtype=dtype)


def _safe_numpy_frombuffer(
    raw_buffer: Any,
    dtype: Any = None,
    count: Any = -1,
    offset: Any = 0,
) -> _FakeNumpyNdArray:
    """Mimic numpy._core.numeric._frombuffer for pickle compatibility."""
    array = _FakeNumpyNdArray(shape=None, dtype=dtype)
    normalized_count = count if isinstance(count, int) else -1
    normalized_offset = offset if isinstance(offset, int) else 0
    if isinstance(raw_buffer, (bytes, bytearray)):
        sliced = raw_buffer[normalized_offset:] if normalized_offset > 0 else raw_buffer
        array.state = {"buffer": sliced, "count": normalized_count}
    return array


class _ResUnpickler(pickle.Unpickler):
    """Restricted unpickler for inf-notebook .res resources."""

    ALLOWED_GLOBALS: dict[tuple[str, str], Any] = {
        ("builtins", "slice"): slice,
        ("numpy.core.multiarray", "scalar"): _safe_numpy_scalar,
        ("numpy._core.multiarray", "scalar"): _safe_numpy_scalar,
        ("numpy", "dtype"): _FakeNumpyDType,
        ("numpy.core.multiarray", "_reconstruct"): _safe_numpy_reconstruct,
        ("numpy._core.multiarray", "_reconstruct"): _safe_numpy_reconstruct,
        ("numpy._core.numeric", "_frombuffer"): _safe_numpy_frombuffer,
        ("numpy", "ndarray"): _FakeNumpyNdArray,
    }

    def find_class(self, module: str, name: str) -> Any:
        key = (module, name)
        if key in self.ALLOWED_GLOBALS:
            return self.ALLOWED_GLOBALS[key]
        raise pickle.UnpicklingError(f"forbidden global in .res: {module}.{name}")


def _load_res_object(path: str) -> dict:
    """Load one `.res` resource file with restricted pickle globals."""
    try:
        with open(path, "rb") as file_obj:
            raw = file_obj.read()
            if raw.startswith(b"\x1f\x8b"):
                raw = gzip.decompress(raw)
            loaded = _ResUnpickler(io.BytesIO(raw)).load()
    except (OSError, pickle.PickleError, EOFError, AttributeError) as exc:
        raise RuntimeError(f"Failed to load .res file: {path}") from exc

    if not isinstance(loaded, dict):
        raise RuntimeError(f".res root object is not dict: {path}")
    return loaded


def _extract_titles_from_res_objects(
    informations_obj: dict,
    musictable_obj: dict,
) -> tuple[list[str], list[str]]:
    music_block = informations_obj.get("music")
    if not isinstance(music_block, dict):
        raise RuntimeError("informations .res missing required dict key: music")

    info_titles_raw = music_block.get("musics")
    if not isinstance(info_titles_raw, list):
        raise RuntimeError("informations .res missing required list key: music.musics")

    musics_block = musictable_obj.get("musics")
    if not isinstance(musics_block, dict):
        raise RuntimeError("musictable .res missing required dict key: musics")

    info_titles = [
        str(value).strip() if value is not None else ""
        for value in info_titles_raw
    ]
    musictable_titles = [
        str(value).strip() if value is not None else ""
        for value in musics_block.keys()
    ]

    return info_titles, musictable_titles


def load_inf_source_titles(
    informations_path: str,
    musictable_path: str,
    tracker_tsv_path: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Load INF source resources and return title lists."""
    informations_obj = _load_res_object(informations_path)
    musictable_obj = _load_res_object(musictable_path)
    info_titles, musictable_titles = _extract_titles_from_res_objects(
        informations_obj,
        musictable_obj,
    )
    tracker_titles = load_tracker_titles(tracker_tsv_path) if tracker_tsv_path else []
    return info_titles, musictable_titles, tracker_titles


def _identify_titles(
    source_titles: list[str],
    alias_map: dict[str, str],
) -> tuple[int, int, Counter[str]]:
    total_song_rows = 0
    matched_song_rows = 0
    unmatched_titles: Counter[str] = Counter()

    for title in source_titles:
        total_song_rows += 1
        if alias_map.get(title) is not None:
            matched_song_rows += 1
        else:
            unmatched_titles[title] += 1

    return total_song_rows, matched_song_rows, unmatched_titles


def generate_import_report(
    source_informations_file: str,
    source_musictable_file: str,
    source_tracker_file: str | None,
    total_song_rows: int,
    matched_song_rows: int,
    unmatched_titles: Counter[str],
    informations_song_rows: int,
    musictable_song_rows: int,
    tracker_song_rows: int,
    titles_only_in_informations: set[str],
    titles_only_in_musictable: set[str],
) -> dict:
    """Generate report used by JSON output and Discord notifications."""
    unmatched_song_rows = total_song_rows - matched_song_rows
    match_rate = 0.0
    if total_song_rows > 0:
        match_rate = (matched_song_rows / total_song_rows) * 100.0

    top_unmatched = [
        {"title": title, "count": count}
        for title, count in _sorted_unmatched(unmatched_titles)[:UNMATCHED_TOP_N]
    ]
    return {
        "source_informations_file": str(source_informations_file),
        "source_musictable_file": str(source_musictable_file),
        "source_tracker_file": str(source_tracker_file) if source_tracker_file else None,
        "alias_scope": ALIAS_SCOPE_INF,
        "total_song_rows": int(total_song_rows),
        "matched_song_rows": int(matched_song_rows),
        "unmatched_song_rows": int(unmatched_song_rows),
        "match_rate": float(round(match_rate, 4)),
        "unmatched_titles_topN": top_unmatched,
        "informations_song_rows": int(informations_song_rows),
        "musictable_song_rows": int(musictable_song_rows),
        "tracker_song_rows": int(tracker_song_rows),
        "titles_only_in_informations_count": len(titles_only_in_informations),
        "titles_only_in_musictable_count": len(titles_only_in_musictable),
        "titles_only_in_informations_topN": sorted(titles_only_in_informations)[:UNMATCHED_TOP_N],
        "titles_only_in_musictable_topN": sorted(titles_only_in_musictable)[:UNMATCHED_TOP_N],
        "generated_at": now_utc_iso(),
    }


def print_report_summary(report: dict) -> None:
    """Print summary report to stdout."""
    print("INF resource alias identification report")
    print(f"- source_informations_file: {report['source_informations_file']}")
    print(f"- source_musictable_file: {report['source_musictable_file']}")
    if report.get("source_tracker_file"):
        print(f"- source_tracker_file: {report['source_tracker_file']}")
    print(f"- alias_scope: {report['alias_scope']}")
    print(f"- total_song_rows: {report['total_song_rows']}")
    print(f"- matched_song_rows: {report['matched_song_rows']}")
    print(f"- unmatched_song_rows: {report['unmatched_song_rows']}")
    print(f"- match_rate: {report['match_rate']:.2f}%")
    print(
        "- source_title_counts: "
        f"informations={report['informations_song_rows']}, "
        f"musictable={report['musictable_song_rows']}, "
        f"tracker={report['tracker_song_rows']}"
    )
    print(
        "- source_set_gap_counts: "
        f"informations_only={report['titles_only_in_informations_count']}, "
        f"musictable_only={report['titles_only_in_musictable_count']}"
    )

    unmatched_top = report.get("unmatched_titles_topN", [])
    if not unmatched_top:
        print("- unmatched_titles_top10: None")
        return

    print("- unmatched_titles_top10:")
    for item in unmatched_top:
        print(f"  - {item['title']} ({item['count']})")


def save_report_json(report: dict, report_path: str) -> None:
    """Save report as JSON file."""
    with open(report_path, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)


def save_unmatched_titles_csv(unmatched_titles: Counter[str], path: str) -> None:
    """Save unmatched title list as CSV file."""
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(["title", "count"])
        for title, count in _sorted_unmatched(unmatched_titles):
            writer.writerow([title, count])


def _build_unmatched_block(unmatched_items: list[dict]) -> list[str]:
    if not unmatched_items:
        return ["Unmatched Titles: None"]

    lines = ["Unmatched Titles (Top):"]
    for item in unmatched_items:
        lines.append(f"- {item['title']} ({item['count']})")
    return lines


def _render_discord_message(
    report: dict,
    unmatched_items: list[dict],
    fallback_note: str | None,
) -> str:
    lines = [
        "INF RES Alias Import Report",
        f"Informations File: {Path(report['source_informations_file']).name}",
        f"MusicTable File: {Path(report['source_musictable_file']).name}",
        f"Total Songs: {report['total_song_rows']}",
        f"Matched Songs: {report['matched_song_rows']}",
        f"Unmatched Songs: {report['unmatched_song_rows']}",
        f"Match Rate: {report['match_rate']:.2f}%",
        "Source Set Gap: "
        f"info_only={report['titles_only_in_informations_count']}, "
        f"musictable_only={report['titles_only_in_musictable_count']}",
    ]

    if fallback_note is None:
        lines.extend(_build_unmatched_block(unmatched_items))
    else:
        lines.append(fallback_note)

    return "\n".join(lines)


def build_discord_import_message(report: dict, limit: int = DISCORD_SAFE_LIMIT) -> str:
    """Build Discord message with fallback for message length limits."""
    unmatched_top = list(report.get("unmatched_titles_topN", []))
    content = _render_discord_message(report, unmatched_top[:UNMATCHED_TOP_N], fallback_note=None)
    if len(content) <= limit:
        return content

    content = _render_discord_message(report, unmatched_top[:5], fallback_note=None)
    if len(content) <= limit:
        return content

    return _render_discord_message(report, [], fallback_note="Unmatched Titles: See log")


def send_discord_import_notification(webhook_url: str | None, content: str) -> None:
    """Send a Discord webhook notification and keep import process non-fatal."""
    if not webhook_url:
        LOGGER.warning("DISCORD_WEBHOOK_URL is not set; skipping import notification")
        return

    try:
        response = requests.post(webhook_url, json={"content": content}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("Failed to send Discord import notification: %s", exc)


def resolve_discord_webhook_url(settings_path: str = "settings.yaml") -> str | None:
    """Resolve webhook URL from environment first, then settings file."""
    env_value = os.environ.get("DISCORD_WEBHOOK_URL")
    if env_value and env_value.strip():
        return env_value.strip()

    settings_file = Path(settings_path)
    if not settings_file.exists():
        return None

    try:
        with settings_file.open("r", encoding="utf-8") as file_obj:
            settings = yaml.safe_load(file_obj) or {}
    except (OSError, yaml.YAMLError) as exc:
        LOGGER.warning("Failed to load settings file for webhook URL: %s", exc)
        return None

    direct = settings.get("discord_webhook_url")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    discord_section = settings.get("discord", {})
    if isinstance(discord_section, dict):
        nested = discord_section.get("webhook_url")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()

    return None


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def import_inf_score_res(
    sqlite_path: str,
    informations_path: str,
    musictable_path: str,
    report_path: str = "inf_import_report.json",
    unmatched_csv_path: str = "inf_unmatched_titles.csv",
    webhook_url: str | None = None,
    settings_path: str = "settings.yaml",
    send_discord: bool = True,
    tracker_tsv_path: str | None = None,
) -> dict:
    """Import INF resources, generate alias identification report, and notify Discord."""
    conn = sqlite3.connect(sqlite_path)
    try:
        alias_map = load_inf_alias_map(conn)
    finally:
        conn.close()

    information_titles, musictable_titles, tracker_titles = load_inf_source_titles(
        informations_path=informations_path,
        musictable_path=musictable_path,
        tracker_tsv_path=tracker_tsv_path,
    )
    source_titles = [*information_titles, *tracker_titles]
    total_song_rows, matched_song_rows, unmatched_titles = _identify_titles(source_titles, alias_map)

    titles_only_in_informations = set(information_titles) - set(musictable_titles)
    titles_only_in_musictable = set(musictable_titles) - set(information_titles)
    report = generate_import_report(
        source_informations_file=informations_path,
        source_musictable_file=musictable_path,
        source_tracker_file=tracker_tsv_path,
        total_song_rows=total_song_rows,
        matched_song_rows=matched_song_rows,
        unmatched_titles=unmatched_titles,
        informations_song_rows=len(information_titles),
        musictable_song_rows=len(musictable_titles),
        tracker_song_rows=len(tracker_titles),
        titles_only_in_informations=titles_only_in_informations,
        titles_only_in_musictable=titles_only_in_musictable,
    )

    save_report_json(report, report_path)
    save_unmatched_titles_csv(unmatched_titles, unmatched_csv_path)
    print_report_summary(report)

    if send_discord:
        webhook = (
            webhook_url
            if webhook_url is not None
            else resolve_discord_webhook_url(settings_path)
        )
        content = build_discord_import_message(report)
        send_discord_import_notification(webhook, content)

    return report


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="INF resources を取り込み、別名同定レポートを出力する。"
    )
    parser.add_argument("informations_path", help="Path to informations4.0.res")
    parser.add_argument("musictable_path", help="Path to musictable1.1.res")
    parser.add_argument("--sqlite-path", default="song_master.sqlite", help="Path to sqlite DB")
    parser.add_argument(
        "--report-path",
        default="inf_import_report.json",
        help="Path to output JSON report",
    )
    parser.add_argument(
        "--unmatched-csv-path",
        default="inf_unmatched_titles.csv",
        help="Path to output unmatched titles CSV",
    )
    parser.add_argument(
        "--settings-path",
        default="settings.yaml",
        help="Path to settings file used when DISCORD_WEBHOOK_URL is not set",
    )
    parser.add_argument(
        "--tracker-tsv-path",
        default=None,
        help="Path to tracker.tsv title source (auto-detects data/tracker.tsv when present)",
    )
    parser.add_argument("--webhook-url", default=None, help="Override Discord webhook URL")
    parser.add_argument(
        "--no-discord",
        action="store_true",
        help="Skip Discord notification",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    tracker_tsv_path = args.tracker_tsv_path
    default_tracker_path = Path("data/tracker.tsv")
    if tracker_tsv_path is None and default_tracker_path.exists():
        tracker_tsv_path = str(default_tracker_path)

    import_inf_score_res(
        sqlite_path=args.sqlite_path,
        informations_path=args.informations_path,
        musictable_path=args.musictable_path,
        report_path=args.report_path,
        unmatched_csv_path=args.unmatched_csv_path,
        webhook_url=args.webhook_url,
        settings_path=args.settings_path,
        send_discord=not args.no_discord,
        tracker_tsv_path=tracker_tsv_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
