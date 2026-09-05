"""CLI contracts for the setup → owned OS → named Director workflow."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import cli
from agentik_station.errors import SecurityError, ValidationError
from agentik_station.paths import LayoutPaths


def test_setup_cli_passes_explicit_scope_without_executing_next_actions(monkeypatch, capsys):
    calls = []
    report = {"operational": False, "next_action": {"argv": ["sudo", "station", "os", "install"]}}
    def build(paths, repo, **scope):
        calls.append(scope)
        return report
    monkeypatch.setitem(sys.modules, "agentik_station.onboarding", SimpleNamespace(
        build_onboarding_report=build, render_onboarding_report=lambda report: "setup report"))
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("Setup executed a next action"))
    assert cli.main(["setup", "--zone", "example-dev", "--project", "platform", "--os", "devops-os", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert calls == [{"zone_id": "example-dev", "project_id": "platform", "os_id": "devops-os", "probe": False}]


def test_provider_setup_cli_selects_os_director_and_preserves_plan(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_platform_gateway", lambda args: calls.append(vars(args)) or 0)
    assert cli.main(["os", "setup", "--zone", "example-dev", "--id", "devops-os", "--plan"]) == 0
    assert calls[0]["os"] == "devops-os"
    assert calls[0]["platform_command"] == "configure"
    assert calls[0]["plan"] is True


def test_project_create_cli_preserves_scoped_plan(monkeypatch, capsys):
    calls = []
    zone = {"id": "dev"}
    def create(paths, repo, **scope):
        calls.append(scope)
        return {"claim": "PREPARED_NOT_RUN", "operational": False}
    monkeypatch.setattr(cli, "_load_zone_record", lambda _: zone)
    monkeypatch.setitem(sys.modules, "agentik_station.projects", SimpleNamespace(create_project=create))
    assert cli.main(["project", "create", "--zone", "dev", "--id", "first-mission", "--plan"]) == 0
    assert calls == [{"zone": zone, "project_id": "first-mission", "plan": True}]
    assert json.loads(capsys.readouterr().out)["claim"] == "PREPARED_NOT_RUN"


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    binaries = {}
    for name in ("hermes", "runuser"):
        binary = tmp_path / name
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        binaries[name] = str(binary)
    monkeypatch.setattr(cli.shutil, "which", lambda name: binaries.get(name))
    monkeypatch.setattr(cli.pwd, "getpwnam", lambda _: SimpleNamespace(
        pw_uid=12001, pw_gid=12001, pw_dir="/var/lib/station/zones/example-dev/home", pw_shell="/usr/sbin/nologin"))
    monkeypatch.setattr(cli.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=12001))
    zone = {"id": "example-dev", "unix_user": "z-org-example-dev",
            "state_root": "/var/lib/station/zones/example-dev",
            "hermes_home": "/var/lib/station/zones/example-dev/hermes"}
    monkeypatch.setattr(cli, "_load_zone_record", lambda _: zone)
    calls = []
    def load(paths, **kwargs):
        calls.append(kwargs)
        return {"os_id": "devops-os", "project_id": "platform", "nano_director": "atlas",
                "bundle_sha256": "a" * 64, "state": "CONFIGURED"}
    monkeypatch.setitem(sys.modules, "agentik_station.os_lifecycle", SimpleNamespace(load_os_runtime_record=load))
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("Plan executed a command"))
    return zone, calls


def test_platform_plan_uses_trusted_director_not_sticky_profile(gateway, capsys):
    assert cli.main(["platform", "setup", "--zone", "example-dev", "--os", "devops-os", "--platform", "discord", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == "atlas"
    assert result["project_id"] == "platform"
    assert result["argv"][-4:] == ["--profile", "atlas", "gateway", "setup"]
    assert result["operational"] is False
    assert gateway[1][0]["require_configured"] is True


def test_provider_plan_uses_native_profile_setup_not_gateway_setup(gateway, capsys):
    assert cli.main(["os", "setup", "--zone", "example-dev", "--id", "devops-os", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["argv"][-3:] == ["--profile", "atlas", "setup"]


@pytest.mark.parametrize("field,value", [("pw_uid", 0), ("pw_gid", 0), ("pw_gid", 12002), ("pw_dir", "/root"), ("pw_shell", "/bin/bash")])
def test_default_gateway_rejects_unsafe_unix_identity(gateway, monkeypatch, field, value):
    account = cli.pwd.getpwnam("example")
    setattr(account, field, value)
    monkeypatch.setattr(cli.pwd, "getpwnam", lambda _: account)
    assert cli.main(["platform", "setup", "--zone", "example-dev", "--plan"]) == 2


def test_untrusted_or_partial_os_stops_before_any_gateway_command(gateway, monkeypatch):
    def reject(*args, **kwargs):
        raise ValidationError("OS installation is incomplete")
    monkeypatch.setattr(sys.modules["agentik_station.os_lifecycle"], "load_os_runtime_record", reject)
    assert cli.main(["platform", "start", "--zone", "example-dev", "--os", "devops-os"]) == 2


def test_gateway_json_does_not_export_native_account_material(gateway, monkeypatch, capsys):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="synthetic-private-key", stderr="synthetic-private-account"))
    assert cli.main(["platform", "status", "--zone", "example-dev", "--os", "devops-os"]) == 0
    text = capsys.readouterr().out
    result = json.loads(text)
    assert "synthetic-private" not in text
    assert result["native_output_exported"] is False
    assert result["operational"] is False


def test_gateway_timeout_is_bounded_and_sanitized(gateway, monkeypatch, capsys):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    def timeout(*a, **k):
        raise cli.subprocess.TimeoutExpired("synthetic-private-command", 300, output="synthetic-private-key")
    monkeypatch.setattr(cli.subprocess, "run", timeout)
    assert cli.main(["platform", "status", "--zone", "example-dev", "--os", "devops-os"]) == 124
    text = capsys.readouterr().out
    assert "synthetic-private" not in text
    assert json.loads(text)["claim"] == "COMMAND_FAILED_NOT_ACCEPTED"


@pytest.mark.parametrize("failure", ["timeout", "missing", "nonzero"])
def test_service_prerequisite_failure_is_bounded_private_and_stops_native(gateway, monkeypatch, capsys, failure):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    existing_which = cli.shutil.which
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"loginctl", "systemctl"} else existing_which(name))
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda path: True if str(path) == "/run/systemd/system" else original_is_dir(path))
    calls = []
    def fail(argv, **kwargs):
        calls.append(argv)
        assert kwargs["timeout"] == 30
        assert kwargs["stdout"] == kwargs["stderr"] == cli.subprocess.DEVNULL
        if failure == "timeout":
            raise cli.subprocess.TimeoutExpired("synthetic-private-command", 30)
        if failure == "missing":
            raise OSError("synthetic-private-path")
        return SimpleNamespace(returncode=1, stderr="synthetic-private-account")
    monkeypatch.setattr(cli.subprocess, "run", fail)
    assert cli.main(["platform", "install", "--zone", "example-dev", "--os", "devops-os"]) == 2
    assert len(calls) == 1
    assert calls[0][1] == "enable-linger"
    output = capsys.readouterr()
    assert "synthetic-private" not in output.out + output.err


@pytest.mark.parametrize("action", ["install", "start", "restart"])
def test_degraded_complete_os_must_verify_before_gateway_activation(gateway, monkeypatch, action):
    loader = sys.modules["agentik_station.os_lifecycle"].load_os_runtime_record
    monkeypatch.setattr(sys.modules["agentik_station.os_lifecycle"], "load_os_runtime_record",
                        lambda *a, **k: {**loader(*a, **k), "state": "DEGRADED"})
    assert cli.main(["platform", action, "--zone", "example-dev", "--os", "devops-os", "--plan"]) == 2


def test_degraded_complete_os_can_open_repair_wizard(gateway, monkeypatch, capsys):
    loader = sys.modules["agentik_station.os_lifecycle"].load_os_runtime_record
    monkeypatch.setattr(sys.modules["agentik_station.os_lifecycle"], "load_os_runtime_record",
                        lambda *a, **k: {**loader(*a, **k), "state": "DEGRADED"})
    assert cli.main(["os", "setup", "--zone", "example-dev", "--id", "devops-os", "--plan"]) == 0
    assert json.loads(capsys.readouterr().out)["argv"][-3:] == ["--profile", "atlas", "setup"]


def test_zone_loader_rejects_record_paths_as_authority(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    monkeypatch.setattr(cli.LayoutPaths, "live", lambda: paths)
    directory = paths.config / "zones.d"
    directory.mkdir(parents=True)
    (directory / "example-dev.json").write_text(json.dumps({
        "id": "example-dev", "placement": "local", "state_root": "/root",
        "hermes_home": "/root/hermes", "unix_user": "root",
    }))
    with pytest.raises(ValidationError, match="canonical ownership/layout"):
        cli._load_zone_record("example-dev")


def test_zone_loader_rejects_symlinked_record_parent(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    monkeypatch.setattr(cli.LayoutPaths, "live", lambda: paths)
    paths.config.mkdir(parents=True)
    alternate = tmp_path / "alternate"
    alternate.mkdir()
    (paths.config / "zones.d").symlink_to(alternate, target_is_directory=True)
    with pytest.raises(SecurityError, match="Symlink forbidden"):
        cli._load_zone_record("example-dev")
