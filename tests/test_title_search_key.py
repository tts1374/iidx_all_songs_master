from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.sqlite_builder import normalize_title_search_key


@pytest.mark.light
def test_normalize_title_search_key_golden_cases():
    cases = [
        ("\u00f6", "o"),  # ö
        ("Stra\u00dfe", "strasse"),  # ß
        ("\u00e6", "ae"),  # æ
        ("\u0153", "oe"),  # œ
        ("\u00f8", "o"),  # ø
        ("\u00e5", "a"),  # å
        ("\u00e7", "c"),  # ç
        ("\u00f1", "n"),  # ñ
        ("\u00e1\u00e0\u00e2\u00e3", "aaaa"),
        ("\u00e9\u00e8\u00ea\u00eb", "eeee"),
        ("\u00ed\u00ec\u00ee\u00ef", "iiii"),
        ("\u00f3\u00f2\u00f4\u00f5", "oooo"),
        ("\u00fa\u00f9\u00fb", "uuu"),
        ("\u00fd\u00ff", "yy"),
        ("o\u0308", "o"),  # 合成文字
        ("  MiXeD   CaSe  ", "mixed case"),
    ]

    for source, expected in cases:
        assert normalize_title_search_key(source) == expected


@pytest.mark.full
def test_title_search_key_matches_normalizer_for_sample_rows(artifact_paths: dict):
    sqlite_path: Path = artifact_paths["sqlite_path"]
    conn = sqlite3.connect(str(sqlite_path))
    try:
        rows = conn.execute(
            "SELECT title, title_search_key FROM music ORDER BY music_id LIMIT 100;"
        ).fetchall()
        assert rows, "検証対象の music 行がありません"
        for title, key in rows:
            assert normalize_title_search_key(title) == key
    finally:
        conn.close()
