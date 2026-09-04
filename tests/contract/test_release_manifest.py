from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import jsonschema

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
    schema = json.loads((ROOT / "contracts" / "release-manifest.schema.json").read_text())
    jsonschema.validate(manifest, schema)
    assert manifest["release"] == PRODUCT_VERSION
    assert manifest["archive_root"] == "agentik-station"
    assert manifest["verified_claim"] == "READY_FOR_SETUP"
    assert manifest["files"] == _actual_files(ROOT)
    assert manifest["file_count"] == len(manifest["files"])


def test_ci_runs_the_shipped_agk_tui_component_suite() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pytest -q -p no:cacheprovider components/agk-tui/tests" in workflow


def test_release_has_checked_provenance_and_cyclonedx_sbom() -> None:
    provenance = json.loads((ROOT / "RELEASE_PROVENANCE.json").read_text())
    sbom = json.loads((ROOT / "SBOM.cdx.json").read_text())
    assert provenance["schema_version"] == "agk-release-provenance/v1"
    assert provenance["subject_count"] == len(provenance["subjects"])
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert any(item["name"] == "discord.js" and item["version"] == "14.27.0" for item in sbom["components"])
    subprocess.run(
        ["python3", str(ROOT / "scripts" / "generate_release_metadata.py"), "--check"],
        cwd=ROOT,
        check=True,
    )


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


def test_repository_doctor_fails_closed_on_provenance_hash_drift(tmp_path: Path) -> None:
    copy = tmp_path / "repo"
    shutil.copytree(ROOT, copy)
    target = copy / "README.md"
    target.write_text(target.read_text() + "\nmodified after release\n")

    result = repo_doctor(copy)

    assert not result.ok
    assert any(issue["name"] == "repo:release-provenance" for issue in result.issues)
