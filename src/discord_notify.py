"""
Discord Webhook通知を行うユーティリティ。

このモジュールは処理結果(成功/失敗/統計)をDiscordへ送信する用途で使用する。
通知失敗は処理全体の失敗とはみなさず、例外は握りつぶす。
"""

from __future__ import annotations

import requests
from requests import RequestException


def send_discord(webhook_url: str, message: str) -> None:
    """
    Discord Webhookへメッセージを送信する。

    webhook_urlが空の場合は何もせず終了する。
    通知失敗は致命的なエラーとせず、例外は握りつぶす。

    Args:
        webhook_url: Discord Webhook URL。
        message: 送信する本文。
    """
    if not webhook_url:
        return

    payload = {"content": message}

    try:
        requests.post(webhook_url, json=payload, timeout=15)
    except RequestException:
        # 通知失敗は致命にしない
        return
