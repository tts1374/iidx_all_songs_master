"""Discord通知用の最小ユーティリティ。"""

import requests


def send_discord_message(webhook_url: str, content: str) -> None:
    """
    Discord Webhook にテキストメッセージを送信する。

    Args:
        webhook_url: Discord Webhook URL。
        content: 送信本文。

    Raises:
        requests.exceptions.HTTPError:
            Discord API がエラーを返した場合。
    """
    payload = {"content": content}
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()
