"""
設定ファイル(settings.yaml)の読み込み処理を提供するモジュール。

settings.yaml から曲マスタ生成に必要な各種設定を読み込み、
アプリ内で扱いやすい dataclass に変換する。
"""

from dataclasses import dataclass
import yaml


@dataclass(frozen=True)
class GithubConfig:
    """
    GitHub Releases 連携設定。

    Attributes:
        owner: GitHubリポジトリのowner名。
        repo: GitHubリポジトリ名。
        upload_to_release: Releaseへのアップロードを行うかどうか。
        asset_name: Releaseに添付するSQLiteファイル名。
    """

    owner: str
    repo: str
    upload_to_release: bool
    asset_name: str


@dataclass(frozen=True)
class Settings:
    """
    アプリケーション全体設定。

    settings.yaml の内容を保持する。

    Attributes:
        version: IIDXのバージョン番号。
        new_song_url: 新曲リストURL。
        old_song_url: 旧曲リストURL。
        output_db_path: 出力SQLiteファイルパス。
        github: GitHub連携設定。
    """

    version: int
    new_song_url: str
    old_song_url: str
    output_db_path: str
    github: GithubConfig


def load_settings(path: str) -> Settings:
    """
    settings.yaml を読み込み Settings に変換する。

    Args:
        path: settings.yaml のファイルパス。

    Returns:
        Settingsオブジェクト。

    Raises:
        FileNotFoundError: 設定ファイルが存在しない場合。
        KeyError: 必須キー(version/new_song_url/old_song_url)が存在しない場合。
        yaml.YAMLError: YAMLのパースに失敗した場合。
        ValueError: versionのint変換に失敗した場合。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    github_data = data.get("github") or {}

    return Settings(
        version=int(data["version"]),
        new_song_url=str(data["new_song_url"]),
        old_song_url=str(data["old_song_url"]),
        output_db_path=str(data.get("output_db_path", "song_master.sqlite")),
        github=GithubConfig(
            owner=str(github_data.get("owner", "")).strip(),
            repo=str(github_data.get("repo", "")).strip(),
            upload_to_release=bool(github_data.get("upload_to_release", False)),
            asset_name=str(github_data.get("asset_name", "song_master.sqlite")),
        ),
    )
