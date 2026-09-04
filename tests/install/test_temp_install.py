from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from agentik_station.doctor import station_doctor
from agentik_station.errors import SecurityError
from agentik_station.installer import StationInstaller
from agentik_station.models import InstallSpec, SeedSpec
from agentik_station.paths import LayoutPaths

ROOT = Path(__file__).resolve().parents[2]


def _spec(operation_id: str = "op-temp-install") -> InstallSpec:
    return InstallSpec(
        operation_id=operation_id,
        host_id="organization-alpha-prod-01",
        role="team",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
        seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha", "platform"),
    )


def test_client_install_isolated_layout_ownership_and_honest_state(tmp_path: Path) -> None:
    paths = LayoutPaths.under(tmp_path / "root")
    assert StationInstaller(ROOT, _spec(), paths=paths).apply() == "READY_FOR_SETUP"

    zone = paths.runtime / "2_ZONES" / "4_ORGANIZATIONS" / "organization-alpha" / "prod"
    project = zone / "projects" / "platform"
    assert zone.is_dir() and project.is_dir()
    assert not (paths.runtime / "2_ZONES" / "2_PRIVATE" / "operator").exists()
    assert not (paths.runtime / "2_ZONES" / "3_AGENTIK" / "dev").exists()
    assert (os.lstat(zone / "credentials").st_mode & 0o777) == 0o700
    assert (os.lstat(project / "credentials").st_mode & 0o777) == 0o700
    assert (os.lstat(project).st_uid, os.lstat(project).st_gid) == (os.getuid(), os.getgid())
    # Simulated installs use one UID: explicitly assert the ancestor traversal
    # bits that a DIFFERENT live Zone identity needs (without directory listing).
    for parent in (paths.varlib, paths.log, paths.run, paths.backups, paths.varlib / "zone-bindings", zone.parent):
        assert parent.stat().st_mode & 0o777 == 0o711
    binding = paths.varlib / "zone-bindings" / "organization-alpha-prod.json"
    assert binding.stat().st_mode & 0o777 == 0o640
    assert json.loads(binding.read_text()) == json.loads((zone / "ZONE.json").read_text())

    discord_hermes = paths.zones_state / "discord-bootstrap" / "hermes" / "config.yaml"
    voice_config = discord_hermes.read_text()
    assert "provider: openai" in voice_config
    assert "model: gpt-transcribe" in voice_config
    assert "model: gpt-4o-mini-tts" in voice_config
    assert "station-parakeet-transcribe" in voice_config
    assert os.lstat(discord_hermes).st_mode & 0o777 == 0o600

    desired_os = json.loads((zone / "os" / "DESIRED.json").read_text())
    assert all(package["runtime_state"] == "NOT_INSTALLED" for package in desired_os["packages"])

    observed = json.loads((paths.observed / "host.json").read_text())
    assert observed["state"] == "READY_FOR_SETUP"
    module_states = {module["id"]: module["runtime_readiness"] for module in observed["modules"]}
    assert module_states["station-kernel"] == "CONFIGURED"
    assert module_states["zone-runtime"] == "CONFIGURED"
    assert module_states["hermes-runtime"] != "OPERATIONAL"

    release = paths.releases / _spec().release_version
    assert release.is_dir() and not release.is_symlink()
    assert (os.lstat(release).st_mode & 0o222) == 0
    assert paths.current.is_symlink()
    assert paths.current.readlink() == Path(f"releases/{_spec().release_version}")

    result = station_doctor(paths, repo_root=ROOT, full=True)
    assert result.ok, result.to_dict()


def test_reconcile_is_idempotent_for_same_immutable_release(tmp_path: Path) -> None:
    paths = LayoutPaths.under(tmp_path / "root")
    first = StationInstaller(ROOT, _spec("op-idempotent-one"), paths=paths)
    second = StationInstaller(ROOT, _spec("op-idempotent-two"), paths=paths)
    assert first.apply() == "READY_FOR_SETUP"
    assert second.apply() == "READY_FOR_SETUP"
    assert (paths.receipts / "op-idempotent-one.json").is_file()
    assert (paths.receipts / "op-idempotent-two.json").is_file()
    receipt = json.loads((paths.receipts / "op-idempotent-two.json").read_text())
    release_evidence = receipt["evidence"]["release_provenance"]
    assert release_evidence["verified_equal"] is True
    assert len(
        {
            release_evidence["source_manifest_sha256"],
            release_evidence["installed_manifest_sha256"],
            release_evidence["loaded_manifest_sha256"],
        }
    ) == 1
    assert station_doctor(paths, repo_root=ROOT, full=True).ok


def test_reconcile_preserves_existing_zone_hermes_config(tmp_path: Path) -> None:
    paths = LayoutPaths.under(tmp_path / "root")
    StationInstaller(ROOT, _spec("op-voice-seed-one"), paths=paths).apply()
    config = paths.zones_state / "discord-bootstrap" / "hermes" / "config.yaml"
    config.write_text("operator_owned: true\n", encoding="utf-8")

    StationInstaller(ROOT, _spec("op-voice-seed-two"), paths=paths).apply()

    assert config.read_text(encoding="utf-8") == "operator_owned: true\n"


def test_preexisting_symlink_in_managed_zone_blocks_apply_without_touching_target(tmp_path: Path) -> None:
    paths = LayoutPaths.under(tmp_path / "root")
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("safe")

    category = paths.runtime / "2_ZONES" / "4_ORGANIZATIONS"
    category.mkdir(parents=True)
    (category / "organization-alpha").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SecurityError):
        StationInstaller(ROOT, _spec("op-symlink-block"), paths=paths).apply()
    assert victim.read_text() == "safe"
