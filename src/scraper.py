"""
スクレイピング処理。

指定されたURLからHTMLを取得する責務を持つ。
HTMLの解析やテーブル抽出は parser.py 側で行い、本モジュールは通信のみを担当する。

例外方針:
- requests 由来の例外は ScrapeError に変換して上位へ伝播する。
"""

from __future__ import annotations

import requests

from src.errors import ScrapeError


def fetch_html(url: str, timeout: int = 30) -> str:
    """
    指定URLへHTTP GETを行い、レスポンスHTML文字列を返す。

    Args:
        url: 取得対象URL。
        timeout: requests.get に渡すタイムアウト秒。

    Returns:
        HTML文字列。

    Raises:
        ScrapeError: HTTPエラーや通信失敗が発生した場合。
    """
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        return r.text
    except requests.RequestException as e:
        raise ScrapeError(f"HTTP fetch failed: {url} ({e})") from e
