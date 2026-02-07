"""
文字列正規化ユーティリティ。

曲名・アーティスト名の揺れを吸収し、music_key生成や検索用途で利用する。
正規化方針は「同一視すべき表記揺れをできるだけ統一する」ことを目的とする。
"""

from __future__ import annotations

import re
import unicodedata


_HYPHEN_CHARS = [
    "‐", "-", "‒", "–", "—", "―",
    "−", "ー", "ｰ", "〜", "～",
]

_QUOTE_MAP = {
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "’": "'",
    "‘": "'",
    "‚": "'",
    "‛": "'",
    "「": '"',
    "」": '"',
    "『": '"',
    "』": '"',
}


def normalize_text(s: str) -> str:
    """
    曲名・アーティスト名などの文字列を正規化して返す。

    正規化内容:
    - Unicode正規化 (NFKC)
    - 改行/タブをスペースへ置換
    - 引用符の統一
    - ハイフン類の統一
    - 全角スペース→半角スペース
    - trim
    - 連続空白を単一化
    - 小文字化

    Args:
        s: 入力文字列。

    Returns:
        正規化済み文字列。入力が None の場合は空文字を返す。
    """
    if s is None:
        return ""

    s = unicodedata.normalize("NFKC", s)

    # 改行・タブ除去
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # 引用符統一
    for k, v in _QUOTE_MAP.items():
        s = s.replace(k, v)

    # ハイフン統一
    for c in _HYPHEN_CHARS:
        s = s.replace(c, "-")

    # 全角スペース→半角スペース
    s = s.replace("　", " ")

    # trim
    s = s.strip()

    # 連続空白を単一化
    s = re.sub(r"\s+", " ", s)

    # lower統一
    s = s.lower()

    return s
