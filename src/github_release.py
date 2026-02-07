"""
GitHub Releases の操作を行うモジュール。

- latest release の取得
- 既存 asset の削除
- sqlite ファイル等の asset アップロード

GitHub Actions 上で GITHUB_TOKEN を利用して動作する想定。
"""

from __future__ import annotations

from typing import Any, Dict

import requests

from src.errors import GithubReleaseError


def _github_headers(token: str) -> Dict[str, str]:
    """
    GitHub REST API 呼び出し用の共通ヘッダを生成する。

    Args:
        token: GitHub API用トークン（GITHUB_TOKEN 等）

    Returns:
        GitHub API呼び出しに必要なHTTPヘッダ辞書。
    """
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_latest_release(owner: str, repo: str, token: str) -> Dict[str, Any]:
    """
    対象リポジトリの latest release 情報を取得する。

    Args:
        owner: GitHub owner名
        repo: GitHub repository名
        token: GitHub API用トークン

    Returns:
        latest release のJSONレスポンス（dict）。

    Raises:
        GithubReleaseError: latest release の取得に失敗した場合。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    r = requests.get(url, headers=_github_headers(token), timeout=30)
    if r.status_code != 200:
        raise GithubReleaseError(f"Failed to get latest release: {r.status_code} {r.text}")
    return r.json()


def delete_asset_if_exists(release: Dict[str, Any], asset_name: str, token: str) -> None:
    """
    Release内に同名のassetが存在する場合、それを削除する。

    Args:
        release: GitHub APIから取得したrelease情報
        asset_name: 削除対象のasset名
        token: GitHub API用トークン

    Raises:
        GithubReleaseError: asset削除URLが取得できない、または削除APIが失敗した場合。
    """
    assets = release.get("assets") or []
    for asset in assets:
        if asset.get("name") == asset_name:
            delete_url = asset.get("url")
            if not delete_url:
                raise GithubReleaseError("Asset delete url not found")

            r = requests.delete(delete_url, headers=_github_headers(token), timeout=30)
            if r.status_code != 204:
                raise GithubReleaseError(f"Failed to delete asset: {r.status_code} {r.text}")
            return


def upload_asset(upload_url: str, asset_name: str, file_path: str, token: str) -> None:
    """
    Releaseのupload_urlに対してassetファイルをアップロードする。

    Args:
        upload_url: release情報に含まれる upload_url（テンプレート形式）
        asset_name: アップロードするasset名
        file_path: アップロード対象ファイルパス
        token: GitHub API用トークン

    Raises:
        GithubReleaseError: assetアップロードが失敗した場合。
    """
    upload_url = upload_url.split("{")[0]
    url = f"{upload_url}?name={asset_name}"

    with open(file_path, "rb") as f:
        data = f.read()

    headers = _github_headers(token)
    headers["Content-Type"] = "application/octet-stream"

    r = requests.post(url, headers=headers, data=data, timeout=60)
    if r.status_code not in (200, 201):
        raise GithubReleaseError(f"Failed to upload asset: {r.status_code} {r.text}")
