"""
データモデル定義モジュール。

スクレイピング結果を内部処理・DB登録に渡すための
SongRow（1曲分の情報）を定義する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SongRow:
    """
    1曲分の曲情報および譜面レベル情報を保持するモデル。

    - title/artist/genre は楽曲のメタ情報
    - sp_*/dp_* は各譜面のレベル（存在しない場合は None）

    仕様上、BEGINNER譜面はSPのみ存在する。
    """

    title: str
    artist: str
    genre: Optional[str]

    sp_beginner: Optional[int]
    sp_normal: Optional[int]
    sp_hyper: Optional[int]
    sp_another: Optional[int]
    sp_leggendaria: Optional[int]

    dp_normal: Optional[int]
    dp_hyper: Optional[int]
    dp_another: Optional[int]
    dp_leggendaria: Optional[int]
