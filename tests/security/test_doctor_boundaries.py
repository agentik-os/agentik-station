from __future__ import annotations

import json
from pathlib import Path

from agentik_station.doctor import station_doctor
from agentik_station.installer import StationInstaller
from agentik_station.models import InstallSpec, SeedSpec
from agentik_station.paths import LayoutPaths

ROOT = Path(__file__).resolve().parents[2]


def _install(tmp_path: Path, operation_id: str = "op-doctor-boundaries") -> tuple[LayoutPaths, Path, Path]:
    paths = LayoutPaths.under(tmp_path / "root")
    spec = InstallSpec(
        operation_id=operation_id,
        host_id="moonbase-prod-01",
        role="client",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
        seed=SeedSpec("CLIENTS", "moonbase", "production", "moonbase", "platform"),
    )
    assert StationInstaller(ROOT, spec, paths=paths).apply() == "READY_FOR_SETUP"
    zone = paths.runtime / "2_ZONES" / "4_CLIENTS" / "moonbase" / "prod"
    record = paths.config / "zones.d" / "moonbase-prod.json"
    return paths, zone, record


def test_doctor_rejects_untrusted_zone_path_before_traversal(tmp_path: Path) -> None:
    paths, _, record = _install(tmp_path)
    payload = json.loads(record.read_text())
    payload["human_root"] = str(tmp_path / "outside-controlled-by-record")
    record.write_text(json.dumps(payload))

    result = station_doctor(paths, repo_root=ROOT, full=True)

    assert not result.ok
    issue = next(item for item in result.issues if item["name"] == "zone:moonbase-prod:contract")
    assert "human_root must be exactly" in issue["message"]
    # Invalid records are not followed into arbitrary filesystem paths.
    assert not any(item["name"] == "zone:moonbase-prod:human" for item in result.checks)


def test_doctor_rejects_project_runtime_path_drift(tmp_path: Path) -> None:
    paths, zone, _ = _install(tmp_path, "op-doctor-project-drift")
    manifest = zone / "projects" / "platform" / "PROJECT.json"
    payload = json.loads(manifest.read_text())
    payload["runtime_state_root"] = str(tmp_path / "outside-project-state")
    manifest.write_text(json.dumps(payload))

    result = station_doctor(paths, repo_root=ROOT, full=True)

    assert not result.ok
    issue = next(item for item in result.issues if item["name"] == "project:moonbase-prod:platform:contract")
    assert "runtime_state_root" in issue["message"]


def test_doctor_rejects_false_os_runtime_claim(tmp_path: Path) -> None:
    paths, zone, _ = _install(tmp_path, "op-doctor-os-claim")
    desired_path = zone / "os" / "DESIRED.json"
    payload = json.loads(desired_path.read_text())
    # Client seed has no packages by default; add a catalogued scaffold and falsely claim it runs.
    payload["packages"] = [
        {
            "id": "devops-os",
            "desired": True,
            "package_maturity": "SCAFFOLDED",
            "runtime_state": "OPERATIONAL",
            "claim": "DECLARED_ONLY",
        }
    ]
    desired_path.write_text(json.dumps(payload))

    result = station_doctor(paths, repo_root=ROOT, full=True)

    assert not result.ok
    issue = next(item for item in result.issues if item["name"] == "zone:moonbase-prod:os-desired-contract")
    assert "unsupported runtime claim" in issue["message"]


def test_doctor_accepts_bounded_remote_desired_zone_record(tmp_path: Path) -> None:
    paths, _, _ = _install(tmp_path, "op-doctor-remote-desired")
    remote = {
        "schema_version": 1,
        "id": "verba-prod",
        "category": "PROJECTS",
        "organization": "gareth",
        "environment": "production",
        "host_id": "verba-prod-01",
        "placement": "REMOTE_DESIRED_NOT_APPLIED",
        "runtime_state": "NOT_INSTALLED",
        "next_repair_action": "Bootstrap and reconcile the remote Host.",
    }
    path = paths.config / "zones.d" / "remote-verba-prod-01-verba-prod.json"
    path.write_text(json.dumps(remote))

    result = station_doctor(paths, repo_root=ROOT, full=True)

    assert result.ok, result.to_dict()
    assert any(
        item["name"] == "zone-record:remote-verba-prod-01-verba-prod:contract"
        for item in result.checks
    )
