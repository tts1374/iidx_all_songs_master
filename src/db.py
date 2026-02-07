"""
SQLiteへの曲マスタ保存処理を提供するモジュール。

スクレイピングで取得した曲情報(SongRow)をSQLiteへ登録し、
music_key(sha1)を用いてupsertを行う。

処理方針:
- 実行開始時に全レコードを論理削除(is_active=0)する
- スクレイピング結果を走査し、存在する曲をis_active=1で復活させる
- chartは(music_id, play_style, difficulty)を一意制約として管理する
"""

import sqlite3
import hashlib
from datetime import datetime, timezone
from src.models import SongRow
from src.normalize import normalize_text


def now_iso() -> str:
    """
    現在時刻(UTC)をISO 8601形式で返す。

    Returns:
        UTC時刻のISO文字列。
    """
    return datetime.now(timezone.utc).isoformat()


def sha1_hex(s: str) -> str:
    """
    文字列をSHA1でハッシュ化し、16進文字列で返す。

    Args:
        s: ハッシュ化対象文字列。

    Returns:
        SHA1ハッシュの16進表現。
    """
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def build_music_key(title: str, artist: str) -> str:
    """
    title/artistからmusic_keyを生成する。

    music_keyは正規化済みtitle/artistを結合した文字列をSHA1化したもの。

    Args:
        title: 曲名。
        artist: アーティスト名。

    Returns:
        music_key(sha1)。
    """
    nt = normalize_text(title)
    na = normalize_text(artist)
    return sha1_hex(f"{nt}|{na}")


def connect_db(path: str) -> sqlite3.Connection:
    """
    SQLite DBへ接続する。

    Args:
        path: SQLiteファイルパス。

    Returns:
        sqlite3.Connectionオブジェクト。
    """
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_schema(con: sqlite3.Connection) -> None:
    """
    DBスキーマを初期化する。

    music/chartテーブルが存在しない場合に作成する。

    Args:
        con: SQLite接続。
    """
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS music (
        music_id INTEGER PRIMARY KEY AUTOINCREMENT,
        music_key TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        normalized_title TEXT NOT NULL,
        artist TEXT NOT NULL,
        normalized_artist TEXT NOT NULL,
        genre TEXT NULL,
        is_active INTEGER NOT NULL,
        last_seen_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chart (
        chart_id INTEGER PRIMARY KEY AUTOINCREMENT,
        music_id INTEGER NOT NULL,
        play_style TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        level INTEGER NOT NULL,
        is_active INTEGER NOT NULL,
        last_seen_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(music_id, play_style, difficulty),
        FOREIGN KEY(music_id) REFERENCES music(music_id)
    )
    """)

    con.commit()


def get_prev_active_count(con: sqlite3.Connection) -> int:
    """
    現在DBにおける有効曲(music.is_active=1)の件数を取得する。

    Args:
        con: SQLite接続。

    Returns:
        有効曲数。
    """
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM music WHERE is_active=1")
    row = cur.fetchone()
    return int(row["cnt"])


def deactivate_all(con: sqlite3.Connection) -> None:
    """
    music/chartの全レコードを論理削除(is_active=0)にする。

    Args:
        con: SQLite接続。
    """
    cur = con.cursor()
    cur.execute("UPDATE music SET is_active=0")
    cur.execute("UPDATE chart SET is_active=0")


def upsert_music(con: sqlite3.Connection, song: SongRow) -> int:
    """
    曲情報をmusicテーブルにupsertする。

    music_keyをキーに存在判定を行い、
    存在しなければINSERT、存在すればUPDATEを行う。

    Args:
        con: SQLite接続。
        song: 曲情報。

    Returns:
        対象のmusic_id。
    """
    cur = con.cursor()

    nt = normalize_text(song.title)
    na = normalize_text(song.artist)
    mkey = sha1_hex(f"{nt}|{na}")

    cur.execute("SELECT music_id FROM music WHERE music_key=?", (mkey,))
    row = cur.fetchone()

    now = now_iso()

    if row is None:
        cur.execute("""
        INSERT INTO music (
            music_key, title, normalized_title, artist, normalized_artist,
            genre, is_active, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            mkey,
            song.title,
            nt,
            song.artist,
            na,
            song.genre,
            now,
            now,
            now,
        ))
        return int(cur.lastrowid)

    music_id = int(row["music_id"])
    cur.execute("""
    UPDATE music
    SET genre=?,
        is_active=1,
        last_seen_at=?,
        updated_at=?
    WHERE music_id=?
    """, (song.genre, now, now, music_id))

    return music_id


def upsert_chart(
    con: sqlite3.Connection,
    music_id: int,
    play_style: str,
    difficulty: str,
    level: int,
) -> None:
    """
    chartテーブルにupsertする。

    UNIQUE(music_id, play_style, difficulty)制約を前提として存在判定し、
    INSERTまたはUPDATEを行う。

    Args:
        con: SQLite接続。
        music_id: musicテーブルのID。
        play_style: SP/DP。
        difficulty: BEGINNER/NORMAL/HYPER/ANOTHER/LEGGENDARIA。
        level: 譜面レベル。
    """
    cur = con.cursor()
    now = now_iso()

    cur.execute("""
    SELECT chart_id FROM chart
    WHERE music_id=? AND play_style=? AND difficulty=?
    """, (music_id, play_style, difficulty))

    row = cur.fetchone()

    if row is None:
        cur.execute("""
        INSERT INTO chart (
            music_id, play_style, difficulty, level,
            is_active, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (music_id, play_style, difficulty, level, now, now, now))
        return

    chart_id = int(row["chart_id"])
    cur.execute("""
    UPDATE chart
    SET level=?,
        is_active=1,
        last_seen_at=?,
        updated_at=?
    WHERE chart_id=?
    """, (level, now, now, chart_id))


def apply_song(con: sqlite3.Connection, song: SongRow) -> None:
    """
    SongRowをmusic/chartへ反映する。

    - musicはupsert
    - chartは存在する譜面のみupsert (Noneは無視)

    Args:
        con: SQLite接続。
        song: 曲情報。
    """
    music_id = upsert_music(con, song)

    mapping = [
        ("SP", "BEGINNER", song.sp_beginner),
        ("SP", "NORMAL", song.sp_normal),
        ("SP", "HYPER", song.sp_hyper),
        ("SP", "ANOTHER", song.sp_another),
        ("SP", "LEGGENDARIA", song.sp_leggendaria),
        ("DP", "NORMAL", song.dp_normal),
        ("DP", "HYPER", song.dp_hyper),
        ("DP", "ANOTHER", song.dp_another),
        ("DP", "LEGGENDARIA", song.dp_leggendaria),
    ]

    for play_style, diff, lvl in mapping:
        if lvl is None:
            continue
        upsert_chart(con, music_id, play_style, diff, lvl)


def get_new_active_count(con: sqlite3.Connection) -> int:
    """
    更新後の有効曲数(music.is_active=1)を取得する。

    Args:
        con: SQLite接続。

    Returns:
        有効曲数。
    """
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM music WHERE is_active=1")
    return int(cur.fetchone()["cnt"])
