"""
HTMLパーサ。

bemaniwiki の曲リストページHTMLから、対象の table.style_table を特定し、
曲情報（SongRow）へ変換する責務を持つ。

想定仕様:
- thead 内テキストから対象テーブルを判定する
- tbody 内の td を13列構成として解釈する
- 難易度セルは "-" を None として扱う
- [CN] [BSS] [MSS] 等の付随情報は除去して数値判定する
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from bs4 import BeautifulSoup

from src.errors import TableNotFoundError, ValidationError
from src.models import SongRow


def _thead_text(table: Any) -> str:
    """
    table 要素の thead からテキストを抽出し、空白除去した文字列を返す。

    Args:
        table: BeautifulSoup の table タグ。

    Returns:
        thead テキスト（空白除去済み）。thead が存在しない場合は空文字。
    """
    thead = table.find("thead")
    if not thead:
        return ""

    text = thead.get_text(" ", strip=True)
    text = re.sub(r"\s+", "", text)
    return text


def _is_target_table(table: Any) -> bool:
    """
    対象の曲リストテーブルかどうか判定する。

    判定条件:
    - thead テキストに TITLE / ARTIST / GENRE / SP / DP が含まれる
    - thead テキストに B N H A L が含まれる

    Args:
        table: BeautifulSoup の table タグ。

    Returns:
        対象テーブルであれば True。
    """
    th = _thead_text(table)
    if not th:
        return False

    required = ["TITLE", "ARTIST", "GENRE", "SP", "DP"]
    if not all(x in th for x in required):
        return False

    if not all(x in th for x in ["B", "N", "H", "A", "L"]):
        return False

    return True


def find_target_table(html: str) -> Tuple[int, Any]:
    """
    HTML文字列から対象の table.style_table を特定して返す。

    条件に合致するテーブルが0件または複数件の場合はエラーとする。

    Args:
        html: 対象ページのHTML文字列。

    Returns:
        (table_index, table_tag) のタプル。

    Raises:
        TableNotFoundError: 条件に合致するテーブルが存在しない、または複数存在する場合。
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.style_table")

    matched = []
    for idx, t in enumerate(tables):
        if _is_target_table(t):
            matched.append((idx, t))

    if len(matched) == 0:
        raise TableNotFoundError("No matching table.style_table found.")
    if len(matched) >= 2:
        raise TableNotFoundError(f"Multiple matching tables found: {len(matched)}")

    return matched[0]


def _parse_level_cell(text: str) -> Optional[int]:
    """
    難易度セル文字列を解析し、レベル値を返す。

    "-" または空の場合は None を返す。
    "[CN]" 等の角括弧付き付随情報は除去する。

    Args:
        text: tdセルの文字列。

    Returns:
        レベル値(int) または None。

    Raises:
        ValidationError: 数値に変換できない場合。
    """
    s = (text or "").strip()
    if s == "-" or s == "":
        return None

    s = re.sub(r"\[[^\]]+\]", "", s)
    s = s.strip()

    if s == "-" or s == "":
        return None

    if not re.fullmatch(r"\d+", s):
        raise ValidationError(f"Invalid level cell: {text}")

    return int(s)


def parse_song_table(table: Any) -> List[SongRow]:
    """
    対象テーブルから曲リストを抽出し SongRow のリストとして返す。

    想定列構成（td 13列）:
    1-9列目: SP/DP 各譜面レベル
    10列目: BPM (未使用)
    11列目: GENRE
    12列目: TITLE
    13列目: ARTIST

    Args:
        table: BeautifulSoup の table タグ。

    Returns:
        SongRow のリスト。

    Raises:
        ValidationError: フォーマット不正（列数不足、TITLE/ARTIST空、譜面が全て"-"等）の場合。
    """
    tbody = table.find("tbody")
    if not tbody:
        raise ValidationError("Table has no tbody")

    rows: List[SongRow] = []
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        if any(td.has_attr("colspan") for td in tds):
            continue

        if len(tds) < 13:
            raise ValidationError(f"Row has insufficient columns: {len(tds)}")

        cols = [td.get_text(" ", strip=True) for td in tds[:13]]

        sp_b = _parse_level_cell(cols[0])
        sp_n = _parse_level_cell(cols[1])
        sp_h = _parse_level_cell(cols[2])
        sp_a = _parse_level_cell(cols[3])
        sp_l = _parse_level_cell(cols[4])

        dp_n = _parse_level_cell(cols[5])
        dp_h = _parse_level_cell(cols[6])
        dp_a = _parse_level_cell(cols[7])
        dp_l = _parse_level_cell(cols[8])

        genre = cols[10].strip() if cols[10].strip() else None
        title = cols[11].strip()
        artist = cols[12].strip()

        if not title:
            raise ValidationError("TITLE is empty")
        if not artist:
            raise ValidationError("ARTIST is empty")

        if all(x is None for x in [sp_b, sp_n, sp_h, sp_a, sp_l, dp_n, dp_h, dp_a, dp_l]):
            raise ValidationError(f"All charts are '-' : {title} / {artist}")

        rows.append(
            SongRow(
                title=title,
                artist=artist,
                genre=genre,
                sp_beginner=sp_b,
                sp_normal=sp_n,
                sp_hyper=sp_h,
                sp_another=sp_a,
                sp_leggendaria=sp_l,
                dp_normal=dp_n,
                dp_hyper=dp_h,
                dp_another=dp_a,
                dp_leggendaria=dp_l,
            )
        )

    return rows
