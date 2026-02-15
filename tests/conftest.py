from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.github_release import download_asset, find_asset_by_name, get_latest_release


def _read_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _resolve_local_artifacts() -> dict | None:
    latest_json_path = Path("latest.json")
    if not latest_json_path.exists():
        return None

    manifest = _read_manifest(latest_json_path)
    file_name = manifest.get("file_name")
    if not file_name:
        return None

    sqlite_path = latest_json_path.parent / file_name
    if not sqlite_path.exists():
        return None

    return {
        "latest_json_path": latest_json_path.resolve(),
        "sqlite_path": sqlite_path.resolve(),
        "manifest": manifest,
        "source": "local",
    }


def _resolve_repo() -> tuple[str, str]:
    settings = yaml.safe_load(Path("settings.yaml").read_text(encoding="utf-8"))
    github_cfg = settings.get("github", {})
    owner = github_cfg.get("owner")
    repo = github_cfg.get("repo")
    if not owner or not repo:
        raise RuntimeError("settings.yaml の github.owner / github.repo が必要です")
    return owner, repo


def _download_latest_artifacts(target_dir: Path) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN が未設定です")

    owner, repo = _resolve_repo()
    release = get_latest_release(f"{owner}/{repo}", token)
    if release is None:
        raise RuntimeError("latest release が見つかりません")

    target_dir.mkdir(parents=True, exist_ok=True)

    latest_asset = find_asset_by_name(release, "latest.json")
    if latest_asset is None:
        raise RuntimeError("latest release に latest.json がありません")

    latest_json_path = target_dir / "latest.json"
    download_asset(latest_asset, str(latest_json_path), token=token)
    manifest = _read_manifest(latest_json_path)

    file_name = manifest.get("file_name")
    if not file_name:
        raise RuntimeError("latest.json に file_name がありません")

    sqlite_asset = find_asset_by_name(release, file_name)
    if sqlite_asset is None:
        raise RuntimeError(f"latest release に sqlite asset がありません: {file_name}")

    sqlite_path = target_dir / file_name
    download_asset(sqlite_asset, str(sqlite_path), token=token)

    return {
        "latest_json_path": latest_json_path.resolve(),
        "sqlite_path": sqlite_path.resolve(),
        "manifest": manifest,
        "source": "release",
    }


@pytest.fixture(scope="session")
def artifact_paths(tmp_path_factory: pytest.TempPathFactory) -> dict:
    local = _resolve_local_artifacts()
    if local:
        return local

    try:
        target_dir = tmp_path_factory.mktemp("downloaded_artifacts")
        return _download_latest_artifacts(target_dir)
    except Exception as exc:
        if os.environ.get("CI"):
            pytest.fail(f"成果物を解決できません: {exc}")
        pytest.skip(f"成果物を解決できないためスキップ: {exc}")


@pytest.fixture(scope="session")
def baseline_sqlite_path() -> Path:
    baseline = os.environ.get("BASELINE_SQLITE_PATH")
    if baseline:
        path = Path(baseline)
        if path.exists():
            return path.resolve()
        if os.environ.get("CI"):
            pytest.fail(f"BASELINE_SQLITE_PATH が存在しません: {path}")

    if os.environ.get("CI"):
        pytest.fail("CIでは BASELINE_SQLITE_PATH が必須です")

    pytest.skip("baseline SQLite が未指定のためスキップ")
