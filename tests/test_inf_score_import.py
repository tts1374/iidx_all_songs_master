"""Tests for INF resource alias import report."""

from __future__ import annotations

import json
import pickle
import sqlite3
import gzip
from pathlib import Path

import pytest
import requests

from src.inf_score_import import (
    build_discord_import_message,
    import_inf_score_res,
)
from src.sqlite_builder import ensure_schema


def _seed_aliases(
    sqlite_path: Path,
    aliases: list[tuple[str, str, str]],
) -> None:
    """Insert INF aliases into test sqlite database."""
    conn = sqlite3.connect(str(sqlite_path))
    try:
        ensure_schema(conn)
        now = "2026-03-16T00:00:00Z"
        conn.executemany(
            """
            INSERT INTO music_title_alias (
                textage_id, alias_scope, alias, alias_type, created_at, updated_at
            )
            VALUES (?, 'inf', ?, ?, ?, ?)
            """,
            [
                (textage_id, alias, alias_type, now, now)
                for textage_id, alias, alias_type in aliases
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _write_res_files(
    tmp_path: Path,
    information_titles: list[str],
    musictable_titles: list[str],
    compress: bool = False,
) -> tuple[Path, Path]:
    informations_path = tmp_path / "informations4.0.res"
    musictable_path = tmp_path / "musictable1.1.res"

    informations = {
        "play_mode": {},
        "difficulty": {},
        "notes": {},
        "playspeed": {},
        "music": {
            "trim": (),
            "masks": {},
            "tables": {},
            "musics": information_titles,
            "factors": {},
        },
    }
    musictable = {
        "versions": {},
        "musics": {
            title: {"version": "test", "SP": {"NORMAL": "1"}, "DP": {"NORMAL": "1"}}
            for title in musictable_titles
        },
        "levels": {},
        "beginners": [],
        "leggendarias": [],
    }

    info_payload = pickle.dumps(informations, protocol=4)
    musictable_payload = pickle.dumps(musictable, protocol=4)
    if compress:
        info_payload = gzip.compress(info_payload)
        musictable_payload = gzip.compress(musictable_payload)

    informations_path.write_bytes(info_payload)
    musictable_path.write_bytes(musictable_payload)

    return informations_path, musictable_path


@pytest.mark.light
def test_import_reports_match_counts_and_outputs_artifacts(tmp_path: Path):
    """Import report counts and output files are generated as expected."""
    sqlite_path = tmp_path / "song_master.sqlite"
    report_path = tmp_path / "inf_import_report.json"
    unmatched_csv_path = tmp_path / "inf_unmatched_titles.csv"
    informations_path, musictable_path = _write_res_files(
        tmp_path,
        information_titles=["Song A", "Song B", "Unknown Song", "Unknown Song"],
        musictable_titles=["Song A", "Song B", "Unknown Song"],
    )

    _seed_aliases(
        sqlite_path,
        [("T001", "Song A", "manual"), ("T002", "Song B", "official")],
    )

    report = import_inf_score_res(
        sqlite_path=str(sqlite_path),
        informations_path=str(informations_path),
        musictable_path=str(musictable_path),
        report_path=str(report_path),
        unmatched_csv_path=str(unmatched_csv_path),
        send_discord=False,
    )

    assert report["alias_scope"] == "inf"
    assert report["total_song_rows"] == 4
    assert report["matched_song_rows"] == 2
    assert report["unmatched_song_rows"] == 2
    assert report["match_rate"] == 50.0
    assert report["informations_song_rows"] == 4
    assert report["musictable_song_rows"] == 3
    assert report["titles_only_in_informations_count"] == 0
    assert report["titles_only_in_musictable_count"] == 0
    assert report["unmatched_titles_topN"] == [{"title": "Unknown Song", "count": 2}]

    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["matched_song_rows"] == 2

    lines = unmatched_csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "title,count"
    assert lines[1] == "Unknown Song,2"


@pytest.mark.light
def test_import_fails_when_inf_alias_map_is_empty(tmp_path: Path):
    """Import fails when INF alias map is empty."""
    sqlite_path = tmp_path / "song_master.sqlite"
    conn = sqlite3.connect(str(sqlite_path))
    try:
        ensure_schema(conn)
        conn.commit()
    finally:
        conn.close()

    informations_path, musictable_path = _write_res_files(
        tmp_path,
        information_titles=["Song A"],
        musictable_titles=["Song A"],
    )

    with pytest.raises(RuntimeError, match="alias_scope='inf'"):
        import_inf_score_res(
            sqlite_path=str(sqlite_path),
            informations_path=str(informations_path),
            musictable_path=str(musictable_path),
            report_path=str(tmp_path / "inf_import_report.json"),
            unmatched_csv_path=str(tmp_path / "inf_unmatched_titles.csv"),
            send_discord=False,
        )


@pytest.mark.light
def test_import_fails_when_res_structure_is_invalid(tmp_path: Path):
    """Invalid .res structure should raise RuntimeError."""
    sqlite_path = tmp_path / "song_master.sqlite"
    _seed_aliases(sqlite_path, [("T001", "Song A", "manual")])

    informations_path = tmp_path / "informations4.0.res"
    musictable_path = tmp_path / "musictable1.1.res"
    with informations_path.open("wb") as file_obj:
        pickle.dump({"music": {}}, file_obj, protocol=4)
    with musictable_path.open("wb") as file_obj:
        pickle.dump({"musics": {"Song A": {}}}, file_obj, protocol=4)

    with pytest.raises(RuntimeError, match="music.musics"):
        import_inf_score_res(
            sqlite_path=str(sqlite_path),
            informations_path=str(informations_path),
            musictable_path=str(musictable_path),
            report_path=str(tmp_path / "inf_import_report.json"),
            unmatched_csv_path=str(tmp_path / "inf_unmatched_titles.csv"),
            send_discord=False,
        )


@pytest.mark.light
def test_import_supports_gzip_compressed_res(tmp_path: Path):
    """Gzip-compressed .res files should be supported."""
    sqlite_path = tmp_path / "song_master.sqlite"
    report_path = tmp_path / "inf_import_report.json"
    unmatched_csv_path = tmp_path / "inf_unmatched_titles.csv"
    informations_path, musictable_path = _write_res_files(
        tmp_path,
        information_titles=["Song A", "Song B"],
        musictable_titles=["Song A", "Song B"],
        compress=True,
    )
    _seed_aliases(
        sqlite_path,
        [("T001", "Song A", "official"), ("T002", "Song B", "manual")],
    )

    report = import_inf_score_res(
        sqlite_path=str(sqlite_path),
        informations_path=str(informations_path),
        musictable_path=str(musictable_path),
        report_path=str(report_path),
        unmatched_csv_path=str(unmatched_csv_path),
        send_discord=False,
    )

    assert report["matched_song_rows"] == 2
    assert report["unmatched_song_rows"] == 0


@pytest.mark.light
def test_discord_message_limits_to_top10_unmatched():
    """Discord message should include up to Top10 unmatched titles."""
    report = {
        "source_informations_file": "data/informations4.0.res",
        "source_musictable_file": "data/musictable1.1.res",
        "total_song_rows": 100,
        "matched_song_rows": 80,
        "unmatched_song_rows": 20,
        "match_rate": 80.0,
        "titles_only_in_informations_count": 0,
        "titles_only_in_musictable_count": 0,
        "unmatched_titles_topN": [
            {"title": f"Title{i:02d}", "count": 1} for i in range(1, 16)
        ],
    }

    content = build_discord_import_message(report, limit=1900)
    assert "Title10" in content
    assert "Title11" not in content


@pytest.mark.light
def test_discord_message_falls_back_to_top5_when_too_long():
    """Long Discord message should fall back to Top5 unmatched titles."""
    report = {
        "source_informations_file": "data/informations4.0.res",
        "source_musictable_file": "data/musictable1.1.res",
        "total_song_rows": 100,
        "matched_song_rows": 80,
        "unmatched_song_rows": 20,
        "match_rate": 80.0,
        "titles_only_in_informations_count": 0,
        "titles_only_in_musictable_count": 0,
        "unmatched_titles_topN": [
            {"title": f"{i:02d}_" + ("L" * 48), "count": i} for i in range(1, 11)
        ],
    }

    report_top5 = dict(report)
    report_top5["unmatched_titles_topN"] = report["unmatched_titles_topN"][:5]
    content_top5_reference = build_discord_import_message(report_top5, limit=100_000)

    content_top5 = build_discord_import_message(report, limit=len(content_top5_reference))
    assert content_top5 == content_top5_reference
    assert report["unmatched_titles_topN"][5]["title"] not in content_top5
    assert "Unmatched Titles: See log" not in content_top5


@pytest.mark.light
def test_discord_message_omits_list_when_even_top5_is_too_long():
    """Very long Discord message should omit unmatched title list."""
    report = {
        "source_informations_file": "data/informations4.0.res",
        "source_musictable_file": "data/musictable1.1.res",
        "total_song_rows": 100,
        "matched_song_rows": 80,
        "unmatched_song_rows": 20,
        "match_rate": 80.0,
        "titles_only_in_informations_count": 0,
        "titles_only_in_musictable_count": 0,
        "unmatched_titles_topN": [
            {"title": f"{i:02d}_" + ("X" * 64), "count": i} for i in range(1, 11)
        ],
    }

    report_top5 = dict(report)
    report_top5["unmatched_titles_topN"] = report["unmatched_titles_topN"][:5]
    content_top5_reference = build_discord_import_message(report_top5, limit=100_000)

    content = build_discord_import_message(report, limit=len(content_top5_reference) - 1)
    assert "Unmatched Titles: See log" in content
    assert "01_" not in content


@pytest.mark.light
def test_webhook_failure_does_not_fail_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
):
    """Webhook failure should not fail import process."""
    sqlite_path = tmp_path / "song_master.sqlite"
    report_path = tmp_path / "inf_import_report.json"
    unmatched_csv_path = tmp_path / "inf_unmatched_titles.csv"
    informations_path, musictable_path = _write_res_files(
        tmp_path,
        information_titles=["Song A", "Song B"],
        musictable_titles=["Song A", "Song B"],
    )

    _seed_aliases(
        sqlite_path,
        [("T001", "Song A", "manual"), ("T002", "Song B", "official")],
    )

    def _raise_post(*_args, **_kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr("src.inf_score_import.requests.post", _raise_post)
    caplog.set_level("WARNING")

    report = import_inf_score_res(
        sqlite_path=str(sqlite_path),
        informations_path=str(informations_path),
        musictable_path=str(musictable_path),
        report_path=str(report_path),
        unmatched_csv_path=str(unmatched_csv_path),
        webhook_url="https://discord.invalid/webhook",
        send_discord=True,
    )

    assert report["matched_song_rows"] == 2
    assert "Failed to send Discord import notification" in caplog.text
