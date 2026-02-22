"""ACスコアCSV取り込みレポート機能のテスト。"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest
import requests

from src.ac_score_import import (
    build_discord_import_message,
    import_ac_score_csv,
    send_discord_import_notification,
)
from src.sqlite_builder import ensure_schema


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_AC_SCORE_CSV_PATH = PROJECT_ROOT / "data" / "7229-6088_dp_score.csv"


def _seed_aliases(
    sqlite_path: Path,
    aliases: list[tuple[str, str, str]],
) -> None:
    """テスト用SQLiteにAC別名データを投入する。"""
    conn = sqlite3.connect(str(sqlite_path))
    try:
        ensure_schema(conn)
        now = "2026-02-22T00:00:00Z"
        conn.executemany(
            """
            INSERT INTO music_title_alias (
                textage_id, alias_scope, alias, alias_type, created_at, updated_at
            )
            VALUES (?, 'ac', ?, ?, ?, ?)
            """,
            [
                (textage_id, alias, alias_type, now, now)
                for textage_id, alias, alias_type in aliases
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _read_titles(csv_path: Path) -> list[str]:
    """CSVからタイトル列を読み込み、前後空白を除去して返す。"""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        assert reader.fieldnames is not None
        assert "タイトル" in reader.fieldnames
        return [str(row["タイトル"]).strip() for row in reader]


@pytest.mark.light
def test_import_reports_match_counts_and_outputs_artifacts(tmp_path: Path):
    """取り込み件数と成果物出力が期待どおりであることを確認する。"""
    sqlite_path = tmp_path / "song_master.sqlite"
    report_path = tmp_path / "import_report.json"
    unmatched_csv_path = tmp_path / "unmatched_titles.csv"
    csv_path = FIXTURE_DIR / "ac_score_mini.csv"

    _seed_aliases(
        sqlite_path,
        [("T001", "Song A", "manual"), ("T002", "Song B", "official")],
    )

    report = import_ac_score_csv(
        sqlite_path=str(sqlite_path),
        csv_path=str(csv_path),
        report_path=str(report_path),
        unmatched_csv_path=str(unmatched_csv_path),
        send_discord=False,
    )

    assert report["source_csv_file"] == str(csv_path)
    assert report["alias_scope"] == "ac"
    assert report["total_song_rows"] == 5
    assert report["matched_song_rows"] == 3
    assert report["unmatched_song_rows"] == 2
    assert report["unmatched_titles_topN"] == [{"title": "Unknown Song", "count": 2}]

    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["matched_song_rows"] == 3

    lines = unmatched_csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "title,count"
    assert lines[1] == "Unknown Song,2"


@pytest.mark.light
def test_import_fails_when_title_column_missing(tmp_path: Path):
    """必須タイトル列が欠落したCSVで例外になることを確認する。"""
    sqlite_path = tmp_path / "song_master.sqlite"
    csv_path = tmp_path / "missing_title.csv"
    csv_path.write_text("曲名,バージョン\nSong A,33\n", encoding="utf-8")

    _seed_aliases(sqlite_path, [("T001", "Song A", "manual")])

    with pytest.raises(RuntimeError, match="タイトル"):
        import_ac_score_csv(
            sqlite_path=str(sqlite_path),
            csv_path=str(csv_path),
            report_path=str(tmp_path / "import_report.json"),
            unmatched_csv_path=str(tmp_path / "unmatched_titles.csv"),
            send_discord=False,
        )


@pytest.mark.light
def test_import_reads_utf8_sig_csv(tmp_path: Path):
    """UTF-8 BOM付きCSVを正常に読み込めることを確認する。"""
    sqlite_path = tmp_path / "song_master.sqlite"
    csv_path = tmp_path / "with_bom.csv"
    csv_path.write_text("タイトル,バージョン\n灼熱Beach Side Bunny,33\n", encoding="utf-8-sig")

    _seed_aliases(sqlite_path, [("T900", "灼熱Beach Side Bunny", "official")])

    report = import_ac_score_csv(
        sqlite_path=str(sqlite_path),
        csv_path=str(csv_path),
        report_path=str(tmp_path / "import_report.json"),
        unmatched_csv_path=str(tmp_path / "unmatched_titles.csv"),
        send_discord=False,
    )
    assert report["total_song_rows"] == 1
    assert report["matched_song_rows"] == 1
    assert report["unmatched_song_rows"] == 0


@pytest.mark.light
def test_import_fails_when_ac_alias_map_is_empty(tmp_path: Path):
    """AC別名マップが空の場合に例外になることを確認する。"""
    sqlite_path = tmp_path / "song_master.sqlite"
    csv_path = tmp_path / "simple.csv"
    csv_path.write_text("タイトル\nSong A\n", encoding="utf-8")

    conn = sqlite3.connect(str(sqlite_path))
    try:
        ensure_schema(conn)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="alias_scope='ac'"):
        import_ac_score_csv(
            sqlite_path=str(sqlite_path),
            csv_path=str(csv_path),
            report_path=str(tmp_path / "import_report.json"),
            unmatched_csv_path=str(tmp_path / "unmatched_titles.csv"),
            send_discord=False,
        )


@pytest.mark.light
def test_discord_message_limits_to_top10_unmatched():
    """Discordメッセージには未一致Top10までのみ含まれることを確認する。"""
    report = {
        "source_csv_file": "data/sample.csv",
        "total_song_rows": 100,
        "matched_song_rows": 80,
        "unmatched_song_rows": 20,
        "match_rate": 80.0,
        "unmatched_titles_topN": [
            {"title": f"Title{i:02d}", "count": 1} for i in range(1, 16)
        ],
    }

    content = build_discord_import_message(report, limit=1900)
    assert "Title10" in content
    assert "Title11" not in content


@pytest.mark.light
def test_discord_message_falls_back_to_top5_when_too_long():
    """長文時に未一致一覧がTop5へフォールバックすることを確認する。"""
    long_titles = [
        {"title": f"{i:02d}_" + ("L" * 48), "count": i} for i in range(1, 11)
    ]
    report = {
        "source_csv_file": "data/sample.csv",
        "total_song_rows": 100,
        "matched_song_rows": 80,
        "unmatched_song_rows": 20,
        "match_rate": 80.0,
        "unmatched_titles_topN": long_titles,
    }

    content = build_discord_import_message(report, limit=450)
    assert "06_" not in content
    assert "05_" in content
    assert "Unmatched Titles: See log" not in content


@pytest.mark.light
def test_discord_message_omits_list_when_even_top5_is_too_long():
    """さらに長文時は未一致一覧が省略されることを確認する。"""
    long_titles = [
        {"title": f"{i:02d}_" + ("X" * 64), "count": i} for i in range(1, 11)
    ]
    report = {
        "source_csv_file": "data/sample.csv",
        "total_song_rows": 100,
        "matched_song_rows": 80,
        "unmatched_song_rows": 20,
        "match_rate": 80.0,
        "unmatched_titles_topN": long_titles,
    }

    content = build_discord_import_message(report, limit=200)
    assert "Unmatched Titles: See log" in content
    assert "01_" not in content


@pytest.mark.light
def test_webhook_failure_does_not_fail_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
):
    """Webhook失敗が取り込み処理全体を失敗させないことを確認する。"""
    sqlite_path = tmp_path / "song_master.sqlite"
    report_path = tmp_path / "import_report.json"
    unmatched_csv_path = tmp_path / "unmatched_titles.csv"
    csv_path = FIXTURE_DIR / "ac_score_mini.csv"

    _seed_aliases(
        sqlite_path,
        [("T001", "Song A", "manual"), ("T002", "Song B", "official")],
    )

    def _raise_post(*_args, **_kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr("src.ac_score_import.requests.post", _raise_post)
    caplog.set_level("WARNING")

    report = import_ac_score_csv(
        sqlite_path=str(sqlite_path),
        csv_path=str(csv_path),
        report_path=str(report_path),
        unmatched_csv_path=str(unmatched_csv_path),
        webhook_url="https://discord.invalid/webhook",
        send_discord=True,
    )

    assert report["matched_song_rows"] == 3
    assert "Failed to send Discord import notification" in caplog.text


@pytest.mark.full
def test_real_ac_score_csv_report_and_discord_fallbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    capsys,
):  # pylint: disable=too-many-locals
    """実CSVでレポート生成とDiscordメッセージの段階フォールバックを検証する。"""
    sqlite_path = tmp_path / "song_master.sqlite"
    report_path = tmp_path / "import_report.json"
    unmatched_csv_path = tmp_path / "unmatched_titles.csv"

    titles = _read_titles(REAL_AC_SCORE_CSV_PATH)
    assert len(titles) > 1000
    unique_titles = list(dict.fromkeys(titles))
    assert len(unique_titles) >= 10

    matched_alias_titles = unique_titles[:3]
    _seed_aliases(
        sqlite_path,
        [
            ("REAL001", matched_alias_titles[0], "manual"),
            ("REAL002", matched_alias_titles[1], "official"),
            ("REAL003", matched_alias_titles[2], "manual"),
        ],
    )

    report = import_ac_score_csv(
        sqlite_path=str(sqlite_path),
        csv_path=str(REAL_AC_SCORE_CSV_PATH),
        report_path=str(report_path),
        unmatched_csv_path=str(unmatched_csv_path),
        send_discord=False,
    )
    printed = capsys.readouterr().out
    assert "AC score CSV identification report" in printed
    assert "- unmatched_titles_top10:" in printed
    assert report["source_csv_file"] == str(REAL_AC_SCORE_CSV_PATH)
    assert report["total_song_rows"] == len(titles)

    matched_title_set = set(matched_alias_titles)
    expected_matched_rows = sum(1 for title in titles if title in matched_title_set)
    assert report["matched_song_rows"] == expected_matched_rows
    assert report["unmatched_song_rows"] == report["total_song_rows"] - expected_matched_rows
    assert len(report["unmatched_titles_topN"]) == 10

    content_top10 = build_discord_import_message(report, limit=100_000)
    for item in report["unmatched_titles_topN"]:
        assert item["title"] in content_top10

    report_top5 = dict(report)
    report_top5["unmatched_titles_topN"] = report["unmatched_titles_topN"][:5]
    content_top5_reference = build_discord_import_message(report_top5, limit=100_000)
    assert len(content_top10) > len(content_top5_reference)

    content_top5 = build_discord_import_message(report, limit=len(content_top5_reference))
    assert content_top5 == content_top5_reference
    if len(report["unmatched_titles_topN"]) >= 6:
        assert report["unmatched_titles_topN"][5]["title"] not in content_top5

    content_omitted = build_discord_import_message(report, limit=len(content_top5_reference) - 1)
    assert "Unmatched Titles: See log" in content_omitted

    def _raise_post(*_args, **_kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr("src.ac_score_import.requests.post", _raise_post)
    caplog.set_level("WARNING")

    send_discord_import_notification("https://discord.invalid/webhook", content_top10)
    assert "Failed to send Discord import notification" in caplog.text
