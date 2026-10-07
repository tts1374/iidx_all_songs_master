"""Tests for build source hash skip decision."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

import main as build_main
from main import (
    INF_PACK_HASH_KEY,
    LEGACY_MANUAL_ALIAS_HASH_KEY,
    MANUAL_ALIAS_AC_HASH_KEY,
    MANUAL_ALIAS_INF_HASH_KEY,
    has_same_textage_source_hashes,
)
from src.ac_score_import import TITLE_COLUMN, import_ac_score_csv
from src.build_validation import file_sha256, should_create_release, validate_latest_manifest
from src.sqlite_builder import ensure_schema, upsert_meta


@pytest.mark.light
def test_has_same_textage_source_hashes_true_when_all_required_hashes_match():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    assert has_same_textage_source_hashes(previous, current) is True


@pytest.mark.light
@pytest.mark.parametrize("output_dir_name", [".", "artifacts"])
def test_unchanged_sources_leave_valid_artifacts_for_score_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output_dir_name: str
):
    """A skipped rebuild replaces stale manifests and supports downstream imports."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    source_files = {}
    for name in ("ac", "inf", "pack"):
        path = tmp_path / f"{name}.csv"
        path.write_text("source\n", encoding="utf-8")
        source_files[name] = str(path)
    source_hashes = {
        "titletbl.js": "a", "datatbl.js": "b", "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: file_sha256(source_files["ac"]),
        MANUAL_ALIAS_INF_HASH_KEY: file_sha256(source_files["inf"]),
        INF_PACK_HASH_KEY: file_sha256(source_files["pack"]),
    }
    previous_sqlite = tmp_path / "previous.sqlite"
    with sqlite3.connect(previous_sqlite) as conn:
        ensure_schema(conn)
        upsert_meta(conn, "33", "old", "old")
        conn.execute(
            """INSERT INTO music (
                textage_id, version, title, title_search_key, artist, genre,
                is_ac_active, is_inf_active, last_seen_at, created_at, updated_at
            ) VALUES ('song_a', '33', 'Song A', 'song a', '', '', 1, 0, 'old', 'old', 'old')"""
        )
        conn.execute(
            """INSERT INTO music_title_alias (
                textage_id, alias_scope, alias, alias_type, created_at, updated_at
            ) VALUES ('song_a', 'ac', 'Song A', 'official', 'old', 'old')"""
        )
    original_bytes = previous_sqlite.read_bytes()
    output_dir = tmp_path / output_dir_name
    output_dir.mkdir(exist_ok=True)
    latest_path = output_dir / "latest.json"
    latest_path.write_text('{"file_name":"missing-old.sqlite"}', encoding="utf-8")
    settings = {
        "output_db_path": str(output_dir / "song_master.sqlite"),
        "schema_version": "33",
        "music_alias_manual_ac_csv_path": source_files["ac"],
        "music_alias_manual_inf_csv_path": source_files["inf"],
        "inf_pack_csv_path": source_files["pack"],
        "github": {"owner": "owner", "repo": "repo", "upload_to_release": True},
    }
    monkeypatch.setattr(build_main, "load_settings", lambda _: settings)
    monkeypatch.setattr(build_main, "download_previous_sqlite_from_release", lambda **_: {
        "sqlite_path": str(previous_sqlite), "asset_updated_at": "old",
        "manifest": {"source_hashes": source_hashes},
    })
    monkeypatch.setattr(build_main, "fetch_textage_tables_with_hashes", lambda: (
        {}, {}, {}, {key: source_hashes[key] for key in ("titletbl.js", "datatbl.js", "actbl.js")}
    ))
    rebuild = Mock(side_effect=AssertionError("unchanged sources must not rebuild"))
    publish = Mock(side_effect=AssertionError("unchanged sources must not publish"))
    monkeypatch.setattr(build_main, "build_or_update_sqlite", rebuild)
    monkeypatch.setattr(build_main, "publish_files_as_new_date_release", publish)

    build_main.main()

    manifest = json.loads(latest_path.read_text(encoding="utf-8"))
    sqlite_path = output_dir / manifest["file_name"]
    assert sqlite_path.read_bytes() == original_bytes
    assert previous_sqlite.read_bytes() == original_bytes
    assert manifest["source_hashes"] == source_hashes
    validate_latest_manifest(str(latest_path), str(sqlite_path))
    assert not should_create_release(str(previous_sqlite), str(sqlite_path))
    rebuild.assert_not_called()
    publish.assert_not_called()
    score_csv = tmp_path / "scores.csv"
    score_csv.write_text(f"{TITLE_COLUMN}\nSong A\n", encoding="utf-8-sig")
    report = import_ac_score_csv(
        str(sqlite_path), str(score_csv), str(tmp_path / "report.json"),
        str(tmp_path / "unmatched.csv"), send_discord=False,
    )
    assert report["total_song_rows"] == report["matched_song_rows"] == 1


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_inf_hash_is_missing_in_previous():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        INF_PACK_HASH_KEY: "f",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    assert has_same_textage_source_hashes(previous, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_ac_hash_differs():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "old",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "new",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    assert has_same_textage_source_hashes(previous, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_inf_hash_differs():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "old",
        INF_PACK_HASH_KEY: "f",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "new",
        INF_PACK_HASH_KEY: "f",
    }
    assert has_same_textage_source_hashes(previous, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_inf_pack_hash_differs():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "old",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "new",
    }
    assert has_same_textage_source_hashes(previous, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_previous_hashes_is_none():
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    assert has_same_textage_source_hashes(None, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_accepts_legacy_manual_alias_key_for_ac():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        LEGACY_MANUAL_ALIAS_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_AC_HASH_KEY: "d",
        MANUAL_ALIAS_INF_HASH_KEY: "e",
        INF_PACK_HASH_KEY: "f",
    }
    assert has_same_textage_source_hashes(previous, current) is True
