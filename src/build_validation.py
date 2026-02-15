"""
ビルド後検証用のヘルパー群。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_byte_size(path: str) -> int:
    return os.path.getsize(path)


def build_latest_manifest(
    sqlite_path: str,
    schema_version: str,
    generated_at: str,
    source_hashes: dict[str, str] | None = None,
) -> dict:
    manifest = {
        "file_name": os.path.basename(sqlite_path),
        "schema_version": schema_version,
        "generated_at": generated_at,
        "sha256": file_sha256(sqlite_path),
        "byte_size": file_byte_size(sqlite_path),
    }
    if source_hashes:
        manifest["source_hashes"] = source_hashes
    return manifest


def write_latest_manifest(latest_json_path: str, manifest: dict):
    os.makedirs(os.path.dirname(latest_json_path) or ".", exist_ok=True)
    with open(latest_json_path, "w", encoding="utf-8") as file_obj:
        json.dump(manifest, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def validate_latest_manifest(latest_json_path: str, sqlite_path: str):
    with open(latest_json_path, "r", encoding="utf-8") as file_obj:
        manifest = json.load(file_obj)

    actual_sha = file_sha256(sqlite_path)
    actual_size = file_byte_size(sqlite_path)
    actual_name = os.path.basename(sqlite_path)

    if manifest.get("file_name") != actual_name:
        raise RuntimeError(
            f"latest.json の file_name 不一致: {manifest.get('file_name')} != {actual_name}"
        )
    if manifest.get("sha256") != actual_sha:
        raise RuntimeError("latest.json の sha256 が SQLite 実体と不一致です")
    if manifest.get("byte_size") != actual_size:
        raise RuntimeError("latest.json の byte_size が SQLite 実体と不一致です")


def _index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_info({index_name});")
    rows = cur.fetchall()
    return [row[2] for row in rows]


def _has_unique_index(
    conn: sqlite3.Connection,
    table_name: str,
    expected_columns: list[str],
) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_list({table_name});")
    for row in cur.fetchall():
        index_name = row[1]
        is_unique = row[2]
        if is_unique != 1:
            continue
        if _index_columns(conn, index_name) == expected_columns:
            return True
    return False


def _assert_not_null_column(conn: sqlite3.Connection, table_name: str, column_name: str):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    for row in cur.fetchall():
        if row[1] == column_name:
            if row[3] != 1:
                raise RuntimeError(f"{table_name}.{column_name} は NOT NULL である必要があります")
            return
    raise RuntimeError(f"列が見つかりません: {table_name}.{column_name}")


def _assert_index_exists(conn: sqlite3.Connection, table_name: str, index_name: str):
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_list({table_name});")
    names = {row[1] for row in cur.fetchall()}
    if index_name not in names:
        raise RuntimeError(f"インデックスが見つかりません: {index_name}")


def validate_db_schema_and_data(sqlite_path: str):
    conn = sqlite3.connect(sqlite_path)
    try:
        _assert_not_null_column(conn, "music", "textage_id")
        _assert_not_null_column(conn, "music", "title_search_key")

        if not _has_unique_index(conn, "music", ["textage_id"]):
            raise RuntimeError("music.textage_id の UNIQUE 制約が見つかりません")

        if not _has_unique_index(conn, "chart", ["music_id", "play_style", "difficulty"]):
            raise RuntimeError("chart の複合 UNIQUE 制約が見つかりません")

        _assert_index_exists(conn, "music", "idx_music_title_search_key")

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM music WHERE title_search_key IS NULL;")
        null_count = int(cur.fetchone()[0])
        if null_count > 0:
            raise RuntimeError(
                f"title_search_key に NULL が含まれています: {null_count} 件"
            )
    finally:
        conn.close()


def _load_chart_key_map(sqlite_path: str) -> dict[tuple[str, str, str], int]:
    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.textage_id, c.play_style, c.difficulty, c.chart_id
            FROM chart c
            INNER JOIN music m ON m.music_id = c.music_id
            """
        )
        rows = cur.fetchall()
        return {(row[0], row[1], row[2]): int(row[3]) for row in rows}
    finally:
        conn.close()


def validate_chart_id_stability(
    old_sqlite_path: str,
    new_sqlite_path: str,
    missing_policy: str = "error",
) -> dict:
    if missing_policy not in {"error", "warn"}:
        raise ValueError("missing_policy は 'error' または 'warn' を指定してください")

    old_map = _load_chart_key_map(old_sqlite_path)
    new_map = _load_chart_key_map(new_sqlite_path)

    mismatches: list[tuple[tuple[str, str, str], int, int]] = []
    missing_in_new: list[tuple[str, str, str]] = []

    for key, old_chart_id in old_map.items():
        new_chart_id = new_map.get(key)
        if new_chart_id is None:
            missing_in_new.append(key)
            continue
        if new_chart_id != old_chart_id:
            mismatches.append((key, old_chart_id, new_chart_id))

    if mismatches:
        sample = ", ".join(
            [
                f"{k[0]}/{k[1]}/{k[2]} old={old_id} new={new_id}"
                for k, old_id, new_id in mismatches[:10]
            ]
        )
        raise RuntimeError(
            f"chart_id の不一致を検出しました ({len(mismatches)} 件): {sample}"
        )

    if missing_in_new and missing_policy == "error":
        sample = ", ".join([f"{k[0]}/{k[1]}/{k[2]}" for k in missing_in_new[:10]])
        raise RuntimeError(
            f"新DBに存在しない譜面があります ({len(missing_in_new)} 件): {sample}"
        )

    return {
        "old_total": len(old_map),
        "new_total": len(new_map),
        "shared_total": len(old_map) - len(missing_in_new),
        "new_only_total": len(new_map) - (len(old_map) - len(missing_in_new)),
        "missing_in_new_total": len(missing_in_new),
        "missing_policy": missing_policy,
    }
