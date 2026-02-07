import os
import sys
import traceback
from datetime import datetime, timezone

from src.textage_loader import fetch_textage_tables
from src.sqlite_builder import build_or_update_sqlite
from src.github_release import upload_sqlite_to_latest_release
from src.discord_notify import send_discord_message


def now_iso() -> str:
    """
    現在のUTC時刻をISO 8601形式の文字列で取得する。
    
    Returns:
        str: ISO 8601形式でフォーマットされた現在のUTC時刻文字列。
    """
    return datetime.now(timezone.utc).isoformat()


def main():
    """
    IIDX全曲マスターデータの更新と配布を行うメイン処理。
    以下の処理を順序実行する:
    1. Textageから楽曲情報テーブルを取得
    2. SQLiteデータベースを構築または更新
    3. 更新したSQLiteファイルをGitHub Releasesの最新リリースにアップロード
    4. Discord Webhookで処理結果を通知（成功/失敗）
    環境変数の要件:
    - GITHUB_REPOSITORY: GitHubのリポジトリ(owner/repo形式)
    - GITHUB_TOKEN: GitHubAPI認証用トークン
    - SQLITE_PATH: SQLiteファイルパス(デフォルト: "song_master.sqlite")
    - DISCORD_WEBHOOK_URL: Discord通知先(オプション)
    処理の成功時はSUCCESS、失敗時は例外を発生させる。
    Raises:
        Exception: 処理中に任意のエラーが発生した場合。
                   エラー内容はDiscordに通知される（設定済みの場合）
    """
    try:
        repo = os.environ["GITHUB_REPOSITORY"]  # owner/repo
        token = os.environ["GITHUB_TOKEN"]
        sqlite_path = os.environ.get("SQLITE_PATH", "song_master.sqlite")

        discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

        # 1. textage JS取得
        titletbl, datatbl, actbl = fetch_textage_tables()

        # 2. SQLite更新
        result = build_or_update_sqlite(
            sqlite_path=sqlite_path,
            titletbl=titletbl,
            datatbl=datatbl,
            actbl=actbl
        )

        # 3. GitHub Releasesへアップロード（latest release）
        upload_sqlite_to_latest_release(
            repo=repo,
            token=token,
            sqlite_path=sqlite_path,
        )

        # 4. Discord通知（成功）
        if discord_webhook:
            msg = (
                f"✅ song_master.sqlite 更新成功\n"
                f"- music processed: {result['music_processed']}\n"
                f"- chart processed: {result['chart_processed']}\n"
                f"- ignored: {result['ignored']}\n"
                f"- updated_at: {now_iso()}\n"
            )
            send_discord_message(discord_webhook, msg)

        print("SUCCESS")

    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)

        discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
        if discord_webhook:
            msg = (
                f"❌ song_master.sqlite 更新失敗\n"
                f"```{err[:1800]}```"
            )
            send_discord_message(discord_webhook, msg)

        raise


if __name__ == "__main__":
    main()
