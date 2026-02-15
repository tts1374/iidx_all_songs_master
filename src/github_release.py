"""GitHub Releases の取得・アップロード操作をまとめたヘルパー。"""

from __future__ import annotations

import os

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    """GitHub API 用の共通ヘッダーを返す。"""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def get_latest_release(repo: str, token: str) -> dict | None:
    """
    最新リリース情報を取得する。

    Args:
        repo: `owner/repo` 形式。
        token: GitHub API token。

    Returns:
        リリースが存在すれば dict、存在しなければ None。
    """
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    response = requests.get(url, headers=_headers(token), timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()


def create_release(repo: str, token: str, tag_name: str = "latest") -> dict:
    """`tag_name` のリリースを作成して JSON を返す。"""
    url = f"{GITHUB_API}/repos/{repo}/releases"
    payload = {
        "tag_name": tag_name,
        "name": tag_name,
        "draft": False,
        "prerelease": False,
        "generate_release_notes": False,
    }

    response = requests.post(url, headers=_headers(token), json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def find_asset_by_name(release: dict, asset_name: str) -> dict | None:
    """リリース assets から `asset_name` と一致するものを返す。"""
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return asset
    return None


def delete_asset(repo: str, token: str, asset_id: int):
    """リリース資産を ID 指定で削除する。"""
    url = f"{GITHUB_API}/repos/{repo}/releases/assets/{asset_id}"
    response = requests.delete(url, headers=_headers(token), timeout=30)
    response.raise_for_status()


def download_asset(asset: dict, output_path: str, token: str | None = None):
    """
    リリース資産をダウンロードして保存する。

    Args:
        asset: GitHub API の asset dict。
        output_path: 出力先パス。
        token: private リポジトリ等に必要な場合の token。
    """
    download_url = asset.get("browser_download_url")
    if not download_url:
        raise RuntimeError("release asset に browser_download_url がありません")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(download_url, headers=headers, timeout=60)
    response.raise_for_status()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as file_obj:
        file_obj.write(response.content)


def upload_asset(upload_url_template: str, token: str, filepath: str, name: str):
    """1ファイルを release upload URL にアップロードする。"""
    upload_url = upload_url_template.split("{")[0] + f"?name={name}"

    with open(filepath, "rb") as file_obj:
        data = file_obj.read()

    headers = _headers(token)
    headers["Content-Type"] = "application/octet-stream"

    response = requests.post(upload_url, headers=headers, data=data, timeout=60)
    response.raise_for_status()
    return response.json()


def upload_files_to_latest_release(repo: str, token: str, file_paths: list[str]):
    """
    最新リリースに複数ファイルをアップロードする。

    同名資産が既に存在する場合は削除してから再アップロードする。
    """
    release = get_latest_release(repo, token)
    if release is None:
        release = create_release(repo, token, tag_name="latest")

    assets = release.get("assets", [])
    assets_by_name = {asset["name"]: asset for asset in assets}

    for file_path in file_paths:
        asset_name = os.path.basename(file_path)
        existing = assets_by_name.get(asset_name)
        if existing:
            delete_asset(repo, token, existing["id"])

        upload_asset(
            upload_url_template=release["upload_url"],
            token=token,
            filepath=file_path,
            name=asset_name,
        )


def upload_sqlite_to_latest_release(repo: str, token: str, sqlite_path: str):
    """SQLite 1ファイルのみを最新リリースへアップロードする。"""
    upload_files_to_latest_release(repo=repo, token=token, file_paths=[sqlite_path])
