"""Gateway activation requires current verification, without obstructing repair."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import cli, native_process, os_instances, os_lifecycle
from agentik_station.errors import ValidationError
from agentik_station.os_discovery import resolve_package


ACTIVATION = ("install", "start", "restart")
REPAIR = ("status", "doctor", "configure", "setup")
SELECTORS = {
    "instance": ["--instance", "engineering"],
    "legacy": ["--os", "devops-os"],
}


@pytest.fixture
def activation(monkeypatch):
    zone = {"id": "example-dev", "unix_user": "z-org-example-dev",
            "state_root": "/var/lib/station/zones/example-dev",
            "hermes_home": "/var/lib/station/zones/example-dev/hermes"}
    profile = "i-1234567890-atlas"
    package = resolve_package(Path(__file__).resolve().parents[2], "devops-os")
    record = {
        "zone_id": zone["id"], "os_version": package["version"],
        "os_id": "devops-os", "instance_id": "engineering", "organization_id": "example",
        "project_id": "platform", "allowed_project_ids": [], "nano_director": profile,
        "role_profile_map": {role: f"i-1234567890-{role}" for role in package["roles"]},
        "expected_profiles": [profile], "profile_states": {profile: {"state": "INSTALLED"}},
        "bundle_sha256": "a" * 64, "state": "VERIFIED",
        "verification": {"config_sha256": {profile: "current-config-hash"}},
    }
    readers = {"instance": os_instances.load_os_instance_record,
               "legacy": os_lifecycle.load_os_runtime_record}
    monkeypatch.setattr(cli, "_load_zone_record", lambda _: zone)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/reviewed/bin/{name}")
    original_is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: True if str(path) in {
        "/usr/local/bin/hermes", "/reviewed/bin/runuser",
    } else original_is_file(path))
    monkeypatch.setattr(cli.pwd, "getpwnam", lambda _: SimpleNamespace(
        pw_uid=12001, pw_gid=12001, pw_dir=zone["state_root"] + "/home", pw_shell="/usr/sbin/nologin"))
    monkeypatch.setattr(cli.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=12001))
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("unexpected native execution"))
    monkeypatch.setattr(native_process, "run_bounded_native", lambda *a, **k: pytest.fail("unexpected native execution"))
    monkeypatch.setattr(os_instances, "load_os_instance_record", lambda *a, **k: record)
    monkeypatch.setattr(os_lifecycle, "load_os_runtime_record", lambda *a, **k: record)
    return record, readers


def command(action, selector, *, plan=True):
    return ["platform", action, "--zone", "example-dev", *SELECTORS[selector], *(["--plan"] if plan else [])]


def repair_command(selector):
    return ("sudo station os instance verify --zone example-dev --instance engineering" if selector == "instance"
            else "sudo station os verify --zone example-dev --id devops-os")


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("action", ACTIVATION)
@pytest.mark.parametrize("state", ["CONFIGURED", "DEGRADED"])
@pytest.mark.parametrize("plan", [False, True])
def test_unverified_team_cannot_activate_or_plan_activation(activation, capsys, selector, action, state, plan):
    activation[0]["state"] = state
    assert cli.main(command(action, selector, plan=plan)) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert repair_command(selector) in output.err
    assert f"local state: {state}" in output.err
    assert "PREPARED_NOT_RUN" not in output.err


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("action", ACTIVATION)
def test_current_verified_team_can_plan_activation(activation, capsys, selector, action):
    assert cli.main(command(action, selector)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["claim"] == "PREPARED_NOT_RUN"
    assert result["profile"] == activation[0]["nano_director"]
    assert result["operational"] is False
    assert result["action"] == action


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("action", ACTIVATION)
@pytest.mark.parametrize("plan", [False, True])
def test_real_stale_reader_downgrade_prevents_activation(activation, monkeypatch, capsys, selector, action, plan):
    record, readers = activation
    # Exercise the actual reader's hash comparison, not a mocked STALE result.
    monkeypatch.setattr(os_lifecycle, "_context", lambda *a, **k: {})
    monkeypatch.setattr(os_lifecycle, "_readback", lambda *a, **k: "changed-config-hash")
    if selector == "instance":
        monkeypatch.setattr(os_instances, "_read_record", lambda *a, **k: record)
        monkeypatch.setattr(os_instances, "_runtime_context", lambda *a, **k: {})
        monkeypatch.setattr(os_instances, "load_os_instance_record", readers[selector])
    else:
        monkeypatch.setattr(os_lifecycle, "_read_record", lambda *a, **k: record)
        monkeypatch.setattr(os_lifecycle, "load_os_runtime_record", readers[selector])
    assert cli.main(command(action, selector, plan=plan)) == 2
    assert record["state"] == "CONFIGURED"
    assert record["verification"]["state"] == "STALE"
    output = capsys.readouterr()
    assert output.out == ""
    assert repair_command(selector) in output.err


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("action", REPAIR)
@pytest.mark.parametrize("state", ["CONFIGURED", "VERIFIED", "DEGRADED"])
def test_verification_gate_preserves_repair_and_observation(activation, capsys, selector, action, state):
    activation[0]["state"] = state
    assert cli.main(command(action, selector)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == activation[0]["nano_director"]
    assert result["claim"] == "PREPARED_NOT_RUN"
    assert result["operational"] is False


@pytest.mark.parametrize("action", [*ACTIVATION, *REPAIR])
def test_zone_default_has_no_new_os_verification_requirement(activation, monkeypatch, capsys, action):
    monkeypatch.setattr(os_instances, "load_os_instance_record", lambda *a, **k: pytest.fail("default must not select an instance"))
    monkeypatch.setattr(os_lifecycle, "load_os_runtime_record", lambda *a, **k: pytest.fail("default must not select a legacy OS"))
    assert cli.main(["platform", action, "--zone", "example-dev", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == "default"
    assert result["instance_id"] is None and result["os_id"] is None
    assert result["claim"] == "PREPARED_NOT_RUN" and not result["operational"]


@pytest.mark.parametrize("selector", SELECTORS)
def test_invalid_runtime_cannot_route_or_plan(activation, monkeypatch, capsys, selector):
    def reject(*args, **kwargs):
        raise ValidationError("Synthetic invalid runtime")

    if selector == "instance":
        monkeypatch.setattr(os_instances, "load_os_instance_record", reject)
    else:
        monkeypatch.setattr(os_lifecycle, "load_os_runtime_record", reject)
    assert cli.main(command("start", selector)) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("action", ACTIVATION)
@pytest.mark.parametrize("state", ["CONFIGURED", "DEGRADED"])
def test_worker_selection_cannot_bypass_full_team_verification(activation, capsys, action, state):
    activation[0]["state"] = state
    assert cli.main([*command(action, "instance"), "--role", "forge"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert repair_command("instance") in output.err


def test_unknown_worker_cannot_route_even_with_verified_team(activation, capsys):
    assert cli.main([*command("start", "instance"), "--role", "unknown-worker"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "not in this instance's trusted Hermes team" in output.err
