"""GitHub Releases 操作用ヘルパー関数。"""

from __future__ import annotations

import os

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def get_latest_release(repo: str, token: str) -> dict | None:
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    response = requests.get(url, headers=_headers(token), timeout=30)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()


def create_release(repo: str, token: str, tag_name: str = "latest") -> dict:
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
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return asset
    return None


def delete_asset(repo: str, token: str, asset_id: int):
    url = f"{GITHUB_API}/repos/{repo}/releases/assets/{asset_id}"
    response = requests.delete(url, headers=_headers(token), timeout=30)
    response.raise_for_status()


def download_asset(asset: dict, output_path: str, token: str | None = None):
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
    upload_url = upload_url_template.split("{")[0] + f"?name={name}"

    with open(filepath, "rb") as file_obj:
        data = file_obj.read()

    headers = _headers(token)
    headers["Content-Type"] = "application/octet-stream"

    response = requests.post(upload_url, headers=headers, data=data, timeout=60)
    response.raise_for_status()
    return response.json()


def upload_files_to_latest_release(repo: str, token: str, file_paths: list[str]):
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
    upload_files_to_latest_release(repo=repo, token=token, file_paths=[sqlite_path])
