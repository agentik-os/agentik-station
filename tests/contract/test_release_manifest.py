from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentik_station.doctor import repo_doctor
from agentik_station.constants import PRODUCT_VERSION

ROOT = Path(__file__).resolve().parents[2]


def _actual_files(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )


def test_release_manifest_matches_exact_repository_inventory() -> None:
    manifest = json.loads((ROOT / "MANIFEST.json").read_text())
    assert manifest["release"] == PRODUCT_VERSION
    assert manifest["archive_root"] == "agentik-station"
    assert manifest["verified_claim"] == "READY_FOR_SETUP"
    assert manifest["files"] == _actual_files(ROOT)
    assert manifest["file_count"] == len(manifest["files"])


def test_repository_doctor_fails_closed_on_manifest_inventory_drift(tmp_path: Path) -> None:
    copy = tmp_path / "repo"
    shutil.copytree(ROOT, copy)
    manifest_path = copy / "MANIFEST.json"
    payload = json.loads(manifest_path.read_text())
    payload["files"] = payload["files"][:-1]
    payload["file_count"] -= 1
    manifest_path.write_text(json.dumps(payload))

    result = repo_doctor(copy)

    assert not result.ok
    assert any(issue["name"] == "repo:release-manifest" for issue in result.issues)
