"""The CLI chooses full trusted instances, not a sticky profile or another client."""
import json
import sys
from types import SimpleNamespace

import pytest

from agentik_station import cli
from agentik_station.errors import ValidationError
from agentik_station.os_runtime import instance_profile_map
from test_orchestration_cli import gateway


@pytest.fixture
def instance_gateway(gateway, monkeypatch):
    zone, _ = gateway
    mapping = instance_profile_map(zone["id"], "engineering", ["atlas", "forge"])
    record = {"os_id": "devops-os", "instance_id": "engineering", "organization_id": "example",
              "allowed_project_ids": ["platform"], "nano_director": mapping["atlas"],
              "role_profile_map": mapping, "state": "CONFIGURED", "bundle_sha256": "a" * 64}
    calls = []
    def load(paths, **kwargs):
        calls.append(kwargs)
        return record
    monkeypatch.setitem(sys.modules, "agentik_station.os_instances", SimpleNamespace(load_os_instance_record=load))
    return zone, record, calls


def test_instance_gateway_targets_its_qualified_director(instance_gateway, capsys):
    zone, record, calls = instance_gateway
    assert cli.main(["platform", "setup", "--zone", zone["id"], "--instance", "engineering", "--platform", "discord", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == record["nano_director"]
    assert result["instance_id"] == "engineering" and result["organization_id"] == "example"
    assert result["project_id"] is None and result["allowed_project_ids"] == ["platform"]
    assert "HERMES_HOME=" + zone["state_root"] + "/os-instances/engineering/hermes" in result["argv"]
    assert "HOME=" + zone["state_root"] + "/home" in result["argv"]
    assert calls == [{"zone": zone, "instance_id": "engineering", "require_configured": True}]
    assert result["operational"] is False


def test_worker_provider_setup_resolves_canonical_role_not_raw_profile(instance_gateway, capsys):
    zone, record, _ = instance_gateway
    assert cli.main(["os", "instance", "setup", "--zone", zone["id"], "--instance", "engineering", "--role", "forge", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["argv"][-4:] == ["--profile", record["role_profile_map"]["forge"], "setup", "model"]
    assert result["role"] == "forge"


def test_optional_worker_bot_routes_only_declared_team_role(instance_gateway, capsys):
    zone, record, _ = instance_gateway
    assert cli.main(["platform", "setup", "--zone", zone["id"], "--instance", "engineering", "--role", "forge", "--platform", "discord", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["argv"][-4:] == ["--profile", record["role_profile_map"]["forge"], "gateway", "setup"]


@pytest.mark.parametrize("role", ["outside-worker", "../forge", "default"])
def test_undeclared_or_unsafe_role_never_runs(instance_gateway, role):
    assert cli.main(["platform", "setup", "--zone", "example-dev", "--instance", "engineering", "--role", role, "--plan"]) == 2


def test_role_cannot_override_legacy_zone_profile(gateway):
    assert cli.main(["platform", "setup", "--zone", "example-dev", "--role", "forge", "--plan"]) == 2


@pytest.mark.parametrize("action", ["install", "start", "restart"])
def test_degraded_instance_cannot_activate_even_worker_gateway(instance_gateway, action):
    instance_gateway[1]["state"] = "DEGRADED"
    assert cli.main(["platform", action, "--zone", "example-dev", "--instance", "engineering", "--role", "forge", "--plan"]) == 2


def test_untrusted_instance_stops_before_native_commands(instance_gateway, monkeypatch):
    def reject(*a, **k):
        raise ValidationError("Instance invalid")
    monkeypatch.setattr(sys.modules["agentik_station.os_instances"], "load_os_instance_record", reject)
    assert cli.main(["platform", "start", "--zone", "example-dev", "--instance", "engineering"]) == 2


def test_legacy_client_controller_cannot_silently_create_second_client_tree(monkeypatch):
    monkeypatch.setattr(cli, "_agk_launcher", lambda: pytest.fail("unapproved legacy launcher discovery"))
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("unapproved legacy execution"))
    assert cli.main(["client", "create", "acme"]) == 2


def test_explicit_legacy_optin_preserves_compatibility_without_migration(monkeypatch):
    from pathlib import Path
    calls = []
    monkeypatch.setattr(cli, "_agk_launcher", lambda: Path("/reviewed/agk"))
    monkeypatch.setattr(cli.subprocess, "run", lambda argv, **k: calls.append(argv) or SimpleNamespace(returncode=0))
    assert cli.main(["client", "--legacy", "doctor", "acme"]) == 0
    assert calls == [["/reviewed/agk", "client", "doctor", "acme"]]


def test_remote_client_zone_plan_never_registers_or_requires_root(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_installed_host", lambda: ("core-host", "core"))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli.SafeFS, "write_text", lambda *a, **k: pytest.fail("plan mutated remote desired state"))
    assert cli.main(["zone", "create", "--category", "ORGANIZATIONS", "--name", "acme", "--env", "production", "--organization", "acme", "--host", "acme-host", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["desired"]["id"] == "acme-prod"
    assert result["desired"]["placement"] == "REMOTE_DESIRED_NOT_APPLIED"
    assert result["mutates"] is False and result["operational"] is False
