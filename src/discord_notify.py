"""
Discord通知機能を提供するモジュール。
このモジュールは、Discord Webhook URLを使用してDiscordチャネルにメッセージを送信する機能を提供します。
"""
import requests

def send_discord_message(webhook_url: str, content: str):
    """
    Discord webhook を通じてメッセージを送信します。

    Args:
        webhook_url (str): Discord webhook URL
        content (str): 送信するメッセージ内容

    Raises:
        requests.exceptions.HTTPError: HTTP リクエストが失敗した場合
    """
    payload = {"content": content}
    r = requests.post(webhook_url, json=payload, timeout=15)
    r.raise_for_status()
