from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
from pathlib import Path

import pytest

from src.build_validation import validate_chart_id_stability


def _sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_sql(sql: str) -> str:
    return " ".join((sql or "").lower().split())


@pytest.mark.required
@pytest.mark.full
def test_generated_sqlite_integrity_and_constraints(artifact_paths: dict):
    sqlite_path: Path = artifact_paths["sqlite_path"]
    assert sqlite_path.exists(), f"SQLite が存在しません: {sqlite_path}"

    conn = sqlite3.connect(str(sqlite_path))
    try:
        assert conn.execute("PRAGMA integrity_check;").fetchall() == [("ok",)]
        assert conn.execute("PRAGMA quick_check;").fetchall() == [("ok",)]
        assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []

        music_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='music';"
        ).fetchone()
        assert music_sql is not None
        music_sql_norm = _normalize_sql(music_sql[0])
        assert "textage_id text not null unique" in music_sql_norm

        chart_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='chart';"
        ).fetchone()
        assert chart_sql is not None
        chart_sql_norm = _normalize_sql(chart_sql[0])
        assert "unique(music_id, play_style, difficulty)" in chart_sql_norm

        music_cols = {row[1]: row for row in conn.execute("PRAGMA table_info(music);").fetchall()}
        assert music_cols["textage_id"][3] == 1
        assert music_cols["title_search_key"][3] == 1

        idx = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='index' AND name='idx_music_title_search_key';
            """
        ).fetchone()
        assert idx is not None
    finally:
        conn.close()


@pytest.mark.required
@pytest.mark.full
def test_latest_json_integrity(artifact_paths: dict):
    latest_json_path: Path = artifact_paths["latest_json_path"]
    sqlite_path: Path = artifact_paths["sqlite_path"]
    manifest: dict = artifact_paths["manifest"]

    required_keys = {"file_name", "schema_version", "generated_at", "sha256", "byte_size"}
    missing = required_keys - set(manifest.keys())
    assert not missing, f"latest.json の必須キー不足: {missing}"

    assert manifest["file_name"] == sqlite_path.name
    assert sqlite_path.exists()
    assert int(manifest["byte_size"]) == sqlite_path.stat().st_size
    assert manifest["sha256"] == _sha256_hex(sqlite_path)
    dt.datetime.fromisoformat(str(manifest["generated_at"]).replace("Z", "+00:00"))
    assert latest_json_path.exists()


@pytest.mark.required
@pytest.mark.full
def test_chart_id_stability_against_baseline(baseline_sqlite_path: Path, artifact_paths: dict):
    sqlite_path: Path = artifact_paths["sqlite_path"]
    summary = validate_chart_id_stability(
        old_sqlite_path=str(baseline_sqlite_path),
        new_sqlite_path=str(sqlite_path),
        missing_policy="error",
    )
    assert summary["shared_total"] > 0
