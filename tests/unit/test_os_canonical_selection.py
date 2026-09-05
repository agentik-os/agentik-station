"""Current package selection is enforced at actual entrypoints, not only display."""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import cli
from agentik_station.errors import ValidationError
from agentik_station.os_discovery import bind_instance, resolve_package
from agentik_station.os_runtime import instance_profile_map
from test_orchestration_cli import gateway


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def source(tmp_path):
    (tmp_path / "os").mkdir()
    shutil.copyfile(ROOT / "os/CATALOG.json", tmp_path / "os/CATALOG.json")
    shutil.copytree(ROOT / "os/builder", tmp_path / "os/builder")
    return tmp_path


@pytest.mark.parametrize("file", ["CONTRACT.json", "MANIFEST.json"])
@pytest.mark.parametrize("field,value", [("version", "0.5.0"), ("version", None), ("identity", "devops-os")])
def test_source_contract_and_manifest_must_match_catalog(source, file, field, value):
    path = source / "os/builder" / file
    payload = json.loads(path.read_text())
    field = ("os_id" if file == "CONTRACT.json" else "id") if field == "identity" else field
    payload[field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="differs"):
        resolve_package(source, "builder")


@pytest.mark.parametrize("file", ["CONTRACT.json", "MANIFEST.json"])
@pytest.mark.parametrize("contents", ["[", "[]", "null", "x" * 65537])
def test_malformed_source_metadata_is_an_actionable_validation_error(source, file, contents):
    (source / "os/builder" / file).write_text(contents)
    with pytest.raises(ValidationError, match="OS source"):
        resolve_package(source, "builder")


@pytest.mark.parametrize("target", ["CONTRACT.json", "MANIFEST.json", "directory"])
def test_source_metadata_rejects_symlink_substitution(source, target):
    original = source / "os/builder" if target == "directory" else source / "os/builder" / target
    alternate = source / "relocated"
    original.rename(alternate)
    original.symlink_to(alternate, target_is_directory=target == "directory")
    with pytest.raises(ValidationError, match="unsafe"):
        resolve_package(source, "builder")


@pytest.fixture
def selection(gateway, monkeypatch):
    zone, _ = gateway
    package = resolve_package(ROOT, "builder")
    mapping = instance_profile_map(zone["id"], "builder", package["roles"])
    record = {
        "schema_version": 3, "zone_id": zone["id"], "os_id": "builder-os", "instance_id": "builder",
        "os_version": package["version"], "organization_id": "example", "allowed_project_ids": [],
        "role_profile_map": mapping, "nano_director": mapping[package["director_role"]],
        "expected_profiles": sorted(mapping.values()), "state": "VERIFIED", "bundle_sha256": "a" * 64,
        "compiled_distribution": "/opt/station/os-instance-distributions/example-dev/builder/builder-os/" + package["version"],
        "hermes_home": zone["state_root"] + "/os-instances/builder/hermes",
        "workspace_root": "/srv/station/2_ZONES/4_ORGANIZATIONS/example/dev/os/instances/builder/workspace",
    }
    calls = []

    def load(paths, **kwargs):
        calls.append(kwargs)
        assert kwargs["require_configured"] is True
        return record

    monkeypatch.setitem(sys.modules, "agentik_station.os_instances", SimpleNamespace(load_os_instance_record=load))
    monkeypatch.setattr(sys.modules["agentik_station.os_lifecycle"], "load_os_runtime_record", load)
    return package, record, calls


def command(action, selector="instance", *, plan=True, role=None):
    if action == "chat":
        assert selector == "instance"
        result = ["os", "instance", "chat", "--zone", "example-dev", "--instance", "builder"]
    else:
        selected = ["--instance", "builder"] if selector == "instance" else ["--os", "builder-os"]
        result = ["platform", action, "--zone", "example-dev", *selected]
    return [*result, *(["--role", role] if role else []), *(["--plan"] if plan else [])]


def legacy(record, package):
    record["schema_version"] = 2
    record.pop("instance_id")
    record.pop("role_profile_map")
    record["nano_director"] = package["director_role"]
    record["expected_profiles"] = package["roles"].copy()
    record["project_id"] = "factory"


def test_resolver_reports_current_and_installed_bundle_without_granting_authority(selection, capsys):
    package, record, calls = selection
    assert cli.main(["os", "resolve", "--name", "BuilderOS", "--zone", "example-dev", "--instance", "builder"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["current_version"] == result["installed_version"] == package["version"]
    assert result["source_version_matches"] and result["source_roles_match"]
    assert result["routing_state"] == "CURRENT_VERSION_SELECTED"
    assert result["director_profile"] == record["nano_director"]
    assert result["compiled_distribution"] == record["compiled_distribution"]
    assert result["bundle_sha256"] == record["bundle_sha256"]
    assert result["source_bytes_compared"] is False
    assert result["access"]["execution_authorized"] is False
    assert result["operational"] is False and len(calls) == 1


@pytest.mark.parametrize("drift", ["version", "roles", "director"])
def test_resolution_remains_diagnostic_and_never_recommends_stale_profile(selection, capsys, drift):
    package, record, _ = selection
    before = copy.deepcopy(record)
    if drift == "version":
        record["os_version"] = "0.5.0"
    elif drift == "roles":
        record["role_profile_map"].pop("domain-scout")
    else:
        record["nano_director"] = record["role_profile_map"]["domain-scout"]
    assert cli.main(["os", "resolve", "--name", "builder", "--zone", "example-dev", "--instance", "builder"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["current_version"] == package["version"]
    assert result["installed_version"] == record["os_version"]
    assert result["source_version_matches"] is (drift != "version")
    assert result["routing_state"] == "MIGRATION_REQUIRED"
    assert result["director_profile"] is None
    assert result["installed_director_profile"] == record["nano_director"]
    assert "Preserve" in result["next_action"] and "backed-up migration" in result["next_action"]
    assert "sudo station os instance show --zone example-dev --instance builder" in result["next_action"]
    assert result["access"]["execution_authorized"] is False
    assert record["compiled_distribution"] == before["compiled_distribution"]


@pytest.mark.parametrize("action", ["chat", "install", "start", "restart"])
@pytest.mark.parametrize("plan", [True, False])
@pytest.mark.parametrize("role", [None, "domain-scout"])
def test_actual_instance_entrypoints_reject_old_version_even_with_identical_verified_roles(selection, capsys, action, plan, role):
    selection[1]["os_version"] = "0.5.0"
    before = copy.deepcopy(selection[1])
    assert cli.main(command(action, plan=plan, role=role)) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "not the current canonical Station package" in output.err
    assert "installed 0.5.0" in output.err
    assert "Preserve" in output.err and "forced profile replacement" in output.err
    assert selection[1] == before


@pytest.mark.parametrize("selector", ["instance", "legacy"])
@pytest.mark.parametrize("action", ["install", "start", "restart"])
@pytest.mark.parametrize("drift", ["version", "roles", "director"])
def test_verified_legacy_and_instance_activation_check_version_and_complete_roles(selection, capsys, selector, action, drift):
    package, record, _ = selection
    if selector == "legacy":
        legacy(record, package)
    if drift == "version":
        record["os_version"] = "0.5.0"
    elif drift == "roles":
        if selector == "legacy":
            record["expected_profiles"].remove("domain-scout")
        else:
            record["role_profile_map"].pop("domain-scout")
    else:
        record["nano_director"] = "domain-scout"
    assert cli.main(command(action, selector)) == 2
    output = capsys.readouterr()
    assert "not the current canonical Station package" in output.err and not output.out
    if selector == "legacy":
        assert "sudo station setup --zone example-dev --os builder-os --json" in output.err


@pytest.mark.parametrize("state", ["CONFIGURED", "VERIFIED", "DEGRADED"])
@pytest.mark.parametrize("role", [None, "domain-scout"])
def test_current_instance_chat_has_no_new_full_team_verification_gate(selection, capsys, state, role):
    selection[1]["state"] = state
    assert cli.main(command("chat", role=role)) == 0
    result = json.loads(capsys.readouterr().out)
    expected = selection[1]["role_profile_map"][role or "master-os-builder"]
    assert result["argv"][-3:] == ["--profile", expected, "chat"]
    assert result["canonical_source_selection"]["canonical_selection_current"] is True
    assert result["claim"] == "PREPARED_NOT_RUN" and result["operational"] is False


def test_current_configured_chat_executes_only_the_selected_namespaced_profile(selection, monkeypatch, capsys):
    selection[1]["state"] = "CONFIGURED"
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda argv, **kwargs:
                        calls.append((argv, kwargs)) or SimpleNamespace(returncode=0))
    assert cli.main(command("chat", plan=False, role="domain-scout")) == 0
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert kwargs == {"check": False, "cwd": selection[1]["workspace_root"]}
    assert argv[-3:] == ["--profile", selection[1]["role_profile_map"]["domain-scout"], "chat"]
    assert "HERMES_HOME=" + selection[1]["hermes_home"] in argv
    result = json.loads(capsys.readouterr().out)
    assert result["canonical_source_selection"]["canonical_selection_current"] is True
    assert result["operational"] is False


@pytest.mark.parametrize("selector", ["instance", "legacy"])
@pytest.mark.parametrize("action", ["configure", "setup", "status", "doctor"])
def test_old_versions_keep_configuration_and_observation_access(selection, capsys, selector, action):
    package, record, _ = selection
    if selector == "legacy":
        legacy(record, package)
    record["os_version"] = "0.5.0"
    assert cli.main(command(action, selector)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == record["nano_director"]
    assert result["installed_version"] == "0.5.0"
    assert result["canonical_source_selection"] is None
    assert result["claim"] == "PREPARED_NOT_RUN"


@pytest.mark.parametrize("selector", ["instance", "legacy"])
@pytest.mark.parametrize("action", ["install", "start", "restart"])
def test_current_verified_native_team_can_plan_activation(selection, capsys, selector, action):
    package, record, _ = selection
    if selector == "legacy":
        legacy(record, package)
    assert cli.main(command(action, selector)) == 0
    result = json.loads(capsys.readouterr().out)
    status = result["canonical_source_selection"]
    assert status["source_version_matches"] and status["source_roles_match"]
    assert status["current_version"] == record["os_version"]
    assert result["profile"] == record["nano_director"]


@pytest.mark.parametrize("action", ["chat", "install", "start", "restart"])
def test_inconsistent_canonical_source_cannot_bypass_execution_guard(selection, source, monkeypatch, capsys, action):
    contract = source / "os/builder/CONTRACT.json"
    payload = json.loads(contract.read_text())
    payload["version"] = "0.5.0"
    contract.write_text(json.dumps(payload))
    monkeypatch.setattr(cli, "repository_root", lambda: source)
    assert cli.main(command(action)) == 2
    assert "differs between catalog" in capsys.readouterr().err


def test_different_os_binding_still_fails_before_version_comparison():
    with pytest.raises(ValidationError, match="another OS"):
        bind_instance(resolve_package(ROOT, "builder"), {"os_id": "devops-os"})
