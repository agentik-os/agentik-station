from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from agentik_station.errors import SecurityError, ValidationError
from agentik_station.models import InstallSpec, SeedSpec
from agentik_station.remote import build_remote_plan, create_release_tar


def remote_spec() -> InstallSpec:
    return InstallSpec(
        operation_id="op-remote-test",
        host_id="moonbase-prod-01",
        role="client",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
        seed=SeedSpec("CLIENTS", "moonbase", "production", "moonbase", "platform"),
    )


def test_remote_plan_keeps_desired_values_in_json_not_shell_arguments() -> None:
    plan = build_remote_plan("operator@remote.example.com", 22, remote_spec())
    command_text = "\n".join(" ".join(command) for command in plan["commands"])
    assert "StrictHostKeyChecking=yes" in command_text
    assert "moonbase" not in command_text
    assert "platform" not in command_text
    assert plan["spec"]["seed"]["name"] == "moonbase"
    assert plan["claim"] == "BOOTSTRAP_TRANSPORT_ONLY"


def test_remote_plan_requires_explicit_host_key_relaxation() -> None:
    strict = build_remote_plan("operator@moonbase-prod-01", 22, remote_spec())
    first_use = build_remote_plan(
        "operator@moonbase-prod-01", 22, remote_spec(), accept_new_host_key=True
    )
    assert strict["strict_host_key_checking"] == "yes"
    assert first_use["strict_host_key_checking"] == "accept-new"


def test_remote_target_injection_is_rejected_before_plan() -> None:
    with pytest.raises(ValidationError):
        build_remote_plan("operator@host;touch /tmp/pwn", 22, remote_spec())


def test_release_tar_is_normalized_and_contains_no_local_owner_claims(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello")
    executable = repo / "station"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    archive = create_release_tar(repo, tmp_path / "release.tar")
    with tarfile.open(archive) as tf:
        members = {member.name: member for member in tf.getmembers()}
    assert members["agentik-station/README.md"].uid == 0
    assert members["agentik-station/README.md"].mtime == 0
    assert members["agentik-station/README.md"].mode == 0o644
    assert members["agentik-station/station"].mode == 0o755


def test_release_tar_rejects_repository_symlinks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    (repo / "bad").symlink_to(outside)
    with pytest.raises(SecurityError):
        create_release_tar(repo, tmp_path / "release.tar")
