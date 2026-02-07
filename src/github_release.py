"""GitHub APIを使用してリリースとアセットを管理するためのモジュール。"""
import os
import requests


GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def get_latest_release(repo: str, token: str) -> dict | None:
    """
    指定されたGitHubリポジトリの最新リリース情報を取得する。
    Args:
        repo (str): リポジトリ名（owner/repoの形式）
        token (str): GitHubのアクセストークン
    Returns:
        dict | None: リリース情報をJSON形式で返す。リリースが見つからない場合はNoneを返す。
    """
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    r = requests.get(url, headers=_headers(token), timeout=30)

    if r.status_code == 404:
        return None

    r.raise_for_status()
    return r.json()


def create_release(repo: str, token: str, tag_name: str = "latest") -> dict:
    """
    GitHubリポジトリに新しいリリースを作成する。
    Args:
        repo (str): リポジトリの所有者とリポジトリ名（例: "owner/repo"）
        token (str): GitHub APIアクセス用の認証トークン
        tag_name (str): リリースのタグ名。デフォルトは"latest"
    Returns:
        dict: GitHub APIから返されたリリース情報のレスポンスJSON
    Raises:
        requests.exceptions.HTTPError: APIリクエストが失敗した場合
    """
    url = f"{GITHUB_API}/repos/{repo}/releases"
    payload = {
        "tag_name": tag_name,
        "name": tag_name,
        "draft": False,
        "prerelease": False,
        "generate_release_notes": False,
    }

    r = requests.post(url, headers=_headers(token), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def delete_asset(repo: str, token: str, asset_id: int):
    """
    GitHubリポジトリのリリースアセットを削除する。

    Args:
        repo (str): リポジトリ名（オーナー/リポジトリ形式）
        token (str): GitHub APIアクセストークン
        asset_id (int): 削除するアセットのID

    Raises:
        requests.exceptions.HTTPError: APIリクエストが失敗した場合
    """
    url = f"{GITHUB_API}/repos/{repo}/releases/assets/{asset_id}"
    r = requests.delete(url, headers=_headers(token), timeout=30)
    r.raise_for_status()


def upload_asset(upload_url_template: str, token: str, filepath: str, name: str):
    """
    GitHubのリリースにアセットをアップロードする。
    指定されたファイルをGitHubのリリースアセットとしてアップロードします。
    Args:
        upload_url_template: アップロードURL テンプレート
        token: GitHub認証トークン
        filepath: アップロードするファイルのパス
        name: GitHubで表示されるアセット名
    Returns:
        dict: GitHubのレスポンスJSON
    Raises:
        requests.exceptions.HTTPError: HTTPリクエストが失敗した場合
    """
    upload_url = upload_url_template.split("{")[0] + f"?name={name}"

    with open(filepath, "rb") as f:
        data = f.read()

    headers = _headers(token)
    headers["Content-Type"] = "application/octet-stream"

    r = requests.post(upload_url, headers=headers, data=data, timeout=60)
    r.raise_for_status()
    return r.json()


def upload_sqlite_to_latest_release(repo: str, token: str, sqlite_path: str):
    """
    最新のリリースにSQLiteファイルをアップロードします。
    既存のリリースがない場合は新しく作成し、同名のアセットが存在する場合は削除した後、
    指定されたSQLiteファイルをアップロードします。
    Args:
        repo (str): リポジトリ名（形式: owner/repo）
        token (str): GitHubアクセストークン
        sqlite_path (str): アップロードするSQLiteファイルのパス
    """
    release = get_latest_release(repo, token)
    if release is None:
        release = create_release(repo, token, tag_name="latest")

    assets = release.get("assets", [])
    for a in assets:
        if a["name"] == os.path.basename(sqlite_path):
            delete_asset(repo, token, a["id"])

    upload_asset(
        upload_url_template=release["upload_url"],
        token=token,
        filepath=sqlite_path,
        name=os.path.basename(sqlite_path),
    )
