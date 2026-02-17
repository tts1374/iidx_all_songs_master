"""ビルド成果物（SQLite / latest.json）の検証ユーティリティ。"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """現在UTC時刻を ISO8601（Z付き）で返す。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: str) -> str:
    """ファイルの SHA-256（16進文字列）を返す。"""
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_byte_size(path: str) -> int:
    """ファイルサイズ（byte）を返す。"""
    return os.path.getsize(path)


def build_latest_manifest(
    sqlite_path: str,
    schema_version: str,
    generated_at: str,
    source_hashes: dict[str, str] | None = None,
) -> dict:
    """
    `latest.json` 用のメタ情報辞書を生成する。

    Args:
        sqlite_path: 生成済み SQLite ファイルパス。
        schema_version: スキーマバージョン。
        generated_at: 生成時刻（ISO8601）。
        source_hashes: 元データ（titletbl/datatbl/actbl）のハッシュ辞書。
    """
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
    """`latest.json` を UTF-8 / indent=2 で書き出す。"""
    os.makedirs(os.path.dirname(latest_json_path) or ".", exist_ok=True)
    with open(latest_json_path, "w", encoding="utf-8") as file_obj:
        json.dump(manifest, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def validate_latest_manifest(latest_json_path: str, sqlite_path: str):
    """
    `latest.json` と SQLite 実体の整合性を検証する。

    検証項目:
    - file_name
    - sha256
    - byte_size
    """
    with open(latest_json_path, "r", encoding="utf-8") as file_obj:
        manifest = json.load(file_obj)

    actual_sha = file_sha256(sqlite_path)
    actual_size = file_byte_size(sqlite_path)
    actual_name = os.path.basename(sqlite_path)

    if manifest.get("file_name") != actual_name:
        raise RuntimeError(
            f"latest.json の file_name が不一致です: {manifest.get('file_name')} != {actual_name}"
        )
    if manifest.get("sha256") != actual_sha:
        raise RuntimeError("latest.json の sha256 が SQLite 実体と一致しません")
    if manifest.get("byte_size") != actual_size:
        raise RuntimeError("latest.json の byte_size が SQLite 実体と一致しません")


def _index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    """指定インデックスの列順を返す。"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_info({index_name});")
    rows = cur.fetchall()
    return [row[2] for row in rows]


def _has_unique_index(
    conn: sqlite3.Connection,
    table_name: str,
    expected_columns: list[str],
) -> bool:
    """指定テーブルに期待列順の UNIQUE インデックスが存在するか判定する。"""
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
    """列が存在し、NOT NULL 制約を持つことを検証する。"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    for row in cur.fetchall():
        if row[1] == column_name:
            if row[3] != 1:
                raise RuntimeError(f"{table_name}.{column_name} は NOT NULL 制約が必要です")
            return
    raise RuntimeError(f"列が見つかりません: {table_name}.{column_name}")


def _assert_index_exists(conn: sqlite3.Connection, table_name: str, index_name: str):
    """指定テーブルに指定インデックスが存在することを検証する。"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_list({table_name});")
    names = {row[1] for row in cur.fetchall()}
    if index_name not in names:
        raise RuntimeError(f"インデックスが見つかりません: {index_name}")


def _read_meta_schema_version(conn: sqlite3.Connection) -> str:
    """Read `meta.schema_version` from SQLite."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT schema_version
        FROM meta
        ORDER BY rowid DESC
        LIMIT 1;
        """
    )
    row = cur.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError("meta.schema_version が見つかりません")
    return str(row[0])


def validate_db_schema_and_data(sqlite_path: str, expected_schema_version: str | None = None):
    """
    生成SQLiteの最低限スキーマ・データ要件を検証する。

    検証項目:
    - `music.textage_id` が NOT NULL
    - `music.title_search_key` が NOT NULL
    - `music.textage_id` に UNIQUE 制約がある
    - `chart(music_id, play_style, difficulty)` に UNIQUE 制約がある
    - `idx_music_title_search_key` が存在する
    - `title_search_key` の NULL 行がない
    - `meta.schema_version` が存在する
    - `expected_schema_version` 指定時は `meta.schema_version` と一致する
    """
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
            raise RuntimeError(f"title_search_key に NULL が含まれています: {null_count} 件")

        actual_schema_version = _read_meta_schema_version(conn)
        if expected_schema_version is not None and actual_schema_version != str(
            expected_schema_version
        ):
            raise RuntimeError(
                "meta.schema_version が不一致です: "
                f"{actual_schema_version} != {expected_schema_version}"
            )
    finally:
        conn.close()


def _load_chart_key_map(sqlite_path: str) -> dict[tuple[str, str, str], int]:
    """比較キー `(textage_id, play_style, difficulty)` から `chart_id` を引く辞書を作る。"""
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
    """
    旧版SQLiteと新版SQLiteで `chart_id` の永続性を検証する。

    比較キー:
    - textage_id
    - play_style
    - difficulty

    Args:
        old_sqlite_path: ベースライン SQLite。
        new_sqlite_path: 新規生成 SQLite。
        missing_policy: 旧版に存在し新版にない譜面の扱い。
            - `"error"`: 失敗
            - `"warn"`: 許容（件数のみ返す）
    """
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
