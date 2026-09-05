"""Read-only native user-service link contracts; no systemd or provider calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import runtime_links
from agentik_station.errors import SecurityError
from agentik_station.filesystem import SafeFS, ensure_no_symlinks
from test_runtime_links import assert_denied, install_fixture, policy, runtime, snapshot, write
from test_os_instances import legacy_runtime, runtime as installed_instance


def native_unit(data, *, profile=None, hermes_home=None, target=None, mode=0o644, watchdog=False):
    """Pinned Hermes generate_systemd_unit user-layout fixture, not an executable."""
    home = hermes_home or data.state_root / "hermes"
    home.mkdir(parents=True, exist_ok=True)
    service = "hermes-gateway" + (f"-{profile}" if profile else "") + ".service"
    unit = data.home / ".config/systemd/user" / service
    python = data.paths.software / "tools/hermes/current/venv/bin/python"
    payload = (
        "[Unit]\nDescription=Hermes Agent Gateway - Messaging Platform Integration\n"
        "After=network-online.target\nWants=network-online.target\nStartLimitIntervalSec=0\n\n"
        "[Service]\n" + ("Type=notify\nNotifyAccess=main\nWatchdogSec=60s\n" if watchdog else "Type=simple\n")
        + f"ExecStart={python} -m hermes_cli.main" + (f" --profile {profile}" if profile else "") + " gateway run\n"
        + f"WorkingDirectory={home}\nEnvironment=\"PATH=/usr/local/bin:/usr/bin:/bin\"\n"
        + f"Environment=\"VIRTUAL_ENV={python.parent.parent}\"\nEnvironment=\"HERMES_HOME={home}\"\n"
        + "Environment=\"HERMES_SUPERVISED_CHILD=1\"\nRestart=always\nRestartSec=5\n"
        + "RestartForceExitStatus=75\nRestartPreventExitStatus=78\nKillMode=mixed\nKillSignal=SIGTERM\n"
        + "ExecReload=/bin/kill -USR1 $MAINPID\n"
        + f"ExecStopPost=-{python} -m gateway.cgroup_cleanup\nTimeoutStopSec=90\n"
        + "StandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=default.target\n"
    )
    write(unit, payload, mode)
    link = unit.parent / "default.target.wants" / service
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(target or str(unit))
    return unit, link


@pytest.mark.parametrize("relative", [False, True])
@pytest.mark.parametrize("mode", [0o600, 0o640, 0o644])
@pytest.mark.parametrize("watchdog", [False, True])
def test_default_native_enablement_link_is_allowed_without_runtime_claim(runtime, relative, mode, watchdog):
    unit, link = native_unit(runtime, target="../hermes-gateway.service" if relative else None,
                             mode=mode, watchdog=watchdog)
    report = runtime.audit()
    assert report == {"unsafe": [], "allowed": [link], "errors": []}
    assert link in ensure_no_symlinks(runtime.state_root)
    before = unit.read_bytes()
    with pytest.raises(SecurityError):
        SafeFS([runtime.state_root]).write_text(link, "privileged overwrite forbidden")
    assert unit.read_bytes() == before


@pytest.mark.parametrize("target", ["../other.service", "../../user/hermes-gateway.service",
                                   ".././hermes-gateway.service", "../../../hermes-gateway.service",
                                   "/etc/systemd/system/hermes-gateway.service", "/root/private",
                                   "hermes-gateway.service", "/dev/null"])
def test_user_link_rejects_nonexact_alias_and_external_targets(runtime, target):
    _, link = native_unit(runtime, target=target)
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("defect", ["missing", "symlink", "hardlink", "directory", "fifo", "writable", "executable", "oversize"])
def test_user_link_requires_bounded_single_link_regular_private_unit(runtime, defect):
    unit, link = native_unit(runtime)
    if defect in {"missing", "symlink", "directory", "fifo"}:
        unit.unlink()
    if defect == "symlink":
        unit.symlink_to(write(runtime.root / "unrelated", "untouched"))
    elif defect == "hardlink":
        os.link(unit, unit.with_suffix(".copy"))
    elif defect == "directory":
        unit.mkdir()
    elif defect == "fifo":
        os.mkfifo(unit)
    elif defect == "writable":
        unit.chmod(0o666)
    elif defect == "executable":
        unit.chmod(0o755)
    elif defect == "oversize":
        unit.write_text("#" * (64 * 1024 + 1))
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("part", [".config", ".config/systemd", ".config/systemd/user", ".config/systemd/user/default.target.wants"])
@pytest.mark.parametrize("defect", ["writable", "symlink"])
def test_user_link_rejects_unsafe_real_parent_chain(runtime, part, defect):
    _, link = native_unit(runtime)
    directory = runtime.home / part
    if defect == "writable":
        directory.chmod(0o777)
    else:
        moved = directory.with_name(directory.name + "-preserved")
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
    report = runtime.audit()
    assert report["unsafe"] or report["errors"]
    assert link not in report["allowed"]


@pytest.mark.parametrize("old,new", [
    ("WantedBy=default.target", "WantedBy=multi-user.target"),
    ("gateway run", "gateway run --profile other"),
    (" -m hermes_cli.main", " -m untrusted.main"),
    (" -m hermes_cli.main", " -m hermes_cli.main --profile default"),
    ("ExecReload=/bin/kill -USR1 $MAINPID", "ExecReload=/bin/sh -c untrusted"),
    (" -m gateway.cgroup_cleanup", " -m other.cleanup"),
    ('Environment="HERMES_SUPERVISED_CHILD=1"', 'Environment="HERMES_SUPERVISED_CHILD=0"'),
    ("[Install]", "[Service]\n[Install]"),
    ("Type=simple", "Type=simple\nType=notify"),
    ("Type=simple", "Type=simple\nExecStartPre=/bin/sh -c untrusted"),
    ("Type=simple", "Type=simple\nEnvironmentFile=/root/private"),
    ("Type=simple", 'Type=simple\nEnvironment="HERMES_HOME=/other"'),
    ("Type=simple", 'Type=simple\nEnvironment="PRIVATE_SECRET=not-allowed"'),
    ("Type=simple", "Type=simple\\\nignored"),
    ("Type=simple", "Type=simple\x00"),
])
def test_user_unit_malformed_or_changed_scoped_directives_fail_closed(runtime, old, new):
    unit, link = native_unit(runtime)
    unit.write_text(unit.read_text().replace(old, new))
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("field", ["WorkingDirectory", "HERMES_HOME"])
def test_default_unit_never_binds_to_another_zone_or_operator(runtime, field):
    unit, link = native_unit(runtime)
    content = unit.read_text()
    content = content.replace(f"{field}={runtime.state_root / 'hermes'}", f"{field}=/root/.hermes")
    unit.write_text(content)
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("location", ["link", "unit", "parent"])
def test_foreign_owner_cannot_grant_user_service_link_exception(runtime, monkeypatch, location):
    unit, link = native_unit(runtime)
    target = {"link": link, "unit": unit, "parent": link.parent}[location]
    identity = target.lstat()
    original = os.stat if location == "link" else os.fstat

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if (result.st_dev, result.st_ino) == (identity.st_dev, identity.st_ino):
            fields = list(result)
            fields[4] += 10000
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "stat" if location == "link" else "fstat", changed)
    assert_denied(runtime.audit(), link)


def test_systemd_audit_never_executes_or_mutates_unit_or_credentials(runtime, monkeypatch):
    _, link = native_unit(runtime)
    secret = write(runtime.state_root / "hermes/.env", "SYNTHETIC_PRIVATE_ENV=not-for-doctor")
    before = snapshot(runtime.root)
    original_open = os.open

    def bounded_open(path, *args, **kwargs):
        assert str(path) != str(secret) and Path(path).name != ".env"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", bounded_open)
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Link Doctor executed a service"))
    assert runtime.audit()["allowed"] == [link]
    assert snapshot(runtime.root) == before


@pytest.mark.parametrize("race", ["unit", "link", "parent"])
def test_user_unit_link_or_directory_replacement_during_readback_fails_closed(runtime, monkeypatch, race):
    unit, link = native_unit(runtime)
    original = runtime_links._systemd_fields

    def changed(payload):
        result = original(payload)
        if race == "unit":
            unit.write_text(unit.read_text() + "# changed after bounded readback\n")
        elif race == "link":
            link.unlink()
            link.symlink_to("../other.service")
        else:
            unit.parent.rename(unit.parent.with_name("user-preserved"))
            unit.parent.mkdir()
        return result

    monkeypatch.setattr(runtime_links, "_systemd_fields", changed)
    assert_denied(runtime.audit(), link)


def instance_layout(data):
    state = Path(data.zone["state_root"])
    return SimpleNamespace(paths=data.paths, state_root=state, home=state / "home", human=Path(data.zone["human_root"]))


def audit(data):
    return runtime_links.audit_zone_links(data.paths, human=data.human, state_root=data.state_root,
                                         owner=(os.getuid(), os.getgid()))


def test_installed_namespaced_instance_profile_uses_its_exact_native_service(installed_instance):
    record = installed_instance.install()
    data = instance_layout(installed_instance)
    _, link = native_unit(data, profile=record["nano_director"],
                          hermes_home=Path(record["hermes_home"]) / "profiles" / record["nano_director"])
    assert audit(data) == {"unsafe": [], "allowed": [link], "errors": []}


@pytest.mark.parametrize("defect", ["missing-ledger", "symlink-ledger", "partial-team", "replaced-root",
                                     "wrong-profile", "other-instance", "unqualified-profile"])
def test_instance_service_requires_trusted_installed_team_and_runtime_roots(installed_instance, defect):
    record = installed_instance.install()
    data = instance_layout(installed_instance)
    profile = record["nano_director"]
    home = Path(record["hermes_home"])
    if defect == "missing-ledger":
        installed_instance.ledger.unlink()
    elif defect == "symlink-ledger":
        moved = installed_instance.ledger.with_suffix(".preserved")
        installed_instance.ledger.rename(moved)
        installed_instance.ledger.symlink_to(moved)
    elif defect == "partial-team":
        value = json.loads(installed_instance.ledger.read_text())
        value["profile_states"][record["expected_profiles"][-1]]["state"] = "PENDING"
        installed_instance.ledger.write_text(json.dumps(value))
    elif defect == "replaced-root":
        home.rename(home.with_name("hermes-preserved"))
        home.mkdir()
    elif defect == "wrong-profile":
        profile = "i-00000000000000000000-director"
    elif defect == "other-instance":
        home = data.state_root / "os-instances/other/hermes"
    else:
        profile = "director"
    _, link = native_unit(data, profile=profile, hermes_home=home / "profiles" / profile)
    assert_denied(audit(data), link)


def test_instance_ledger_loader_private_errors_are_not_exported(installed_instance, monkeypatch):
    from agentik_station import os_instances

    record = installed_instance.install()
    data = instance_layout(installed_instance)
    _, link = native_unit(data, profile=record["nano_director"],
                          hermes_home=Path(record["hermes_home"]) / "profiles" / record["nano_director"])

    def rejected(*args, **kwargs):
        raise SecurityError("SYNTHETIC_PRIVATE_LEDGER_ERROR")

    monkeypatch.setattr(os_instances, "load_os_instance_record", rejected)
    report = audit(data)
    assert_denied(report, link)
    assert "SYNTHETIC_PRIVATE" not in str(report)


def test_legacy_installed_profile_remains_supported(legacy_runtime):
    record = legacy_runtime.install()
    data = instance_layout(legacy_runtime)
    _, link = native_unit(data, profile=record["nano_director"],
                          hermes_home=data.state_root / "hermes/profiles" / record["nano_director"])
    assert audit(data) == {"unsafe": [], "allowed": [link], "errors": []}


def test_full_doctor_accepts_native_default_link_without_operational_claim(tmp_path):
    from agentik_station.doctor import station_doctor

    data = install_fixture(tmp_path, "op-doctor-native-systemd")
    _, link = native_unit(data)
    result = station_doctor(data.paths, repo_root=Path(__file__).resolve().parents[2], full=True)
    assert result.ok, result.to_dict()
    assert link.exists()
    detail = next(item["detail"] for item in result.checks if item["name"] == "zone:organization-alpha-prod:symlinks")
    assert "No provider or mission readiness implied" in detail
