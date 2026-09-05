"""Personal Workstation routing must never weaken the default HOME boundary."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

COMPONENT = Path(__file__).parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, COMPONENT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scope = load("agk_workstation_test", "hermes/plugins/agentik_os/workstation.py")
agk = load("agk_workstation_controller_test", "scripts/agk_control.py")
package = types.ModuleType("agk_workstation_plugin_test")
package.__path__ = [str(COMPONENT / "hermes/plugins/agentik_os")]
sys.modules[package.__name__] = package
paths = load("agk_workstation_plugin_test.paths", "hermes/plugins/agentik_os/paths.py")


@pytest.fixture
def workstation(tmp_path, monkeypatch):
    root = tmp_path / "station"
    root.mkdir(mode=0o700)
    for child in ("personal", "personal/home", "projects", "bin"):
        (root / child).mkdir(mode=0o700)
    profile = "station-" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    marker = root / ".station-workstation.json"
    marker.write_text(json.dumps({"schema": 1, "mode": "workstation", "root": str(root), "profile": profile, "uid": os.getuid()}))
    marker.chmod(0o600)
    executable = root / "bin/agk"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    monkeypatch.setenv("STATION_WORKSTATION_ROOT", str(root))
    monkeypatch.setenv("HOME", str(root / "personal/home"))
    return root


def test_explicit_marker_selects_owned_launcher_and_sibling_projects(workstation):
    assert scope.workstation_root() == workstation
    assert scope.agk_executable() == str(workstation / "bin/agk")
    assert scope.permitted_cwd(workstation / "projects", Path.home())
    assert not scope.permitted_cwd(workstation / "tools", Path.home())
    assert not scope.permitted_cwd(workstation.parent, Path.home())


def test_unconfigured_environment_keeps_host_launcher_and_home_boundary(tmp_path, monkeypatch):
    monkeypatch.delenv("STATION_WORKSTATION_ROOT", raising=False)
    assert scope.workstation_root() is None
    assert scope.agk_executable() == "/usr/local/bin/agk"
    assert not scope.permitted_cwd(tmp_path / "projects", tmp_path / "home")


def test_raw_environment_cannot_adopt_unmanaged_directory(workstation):
    (workstation / ".station-workstation.json").unlink()
    with pytest.raises(OSError):
        scope.workstation_root()


@pytest.mark.parametrize("field,value", [("root", "/somewhere/else"), ("profile", "default"), ("mode", "host"), ("uid", -1)])
def test_changed_context_is_rejected(workstation, field, value):
    marker = workstation / ".station-workstation.json"
    data = json.loads(marker.read_text())
    data[field] = value
    marker.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="mismatch"):
        scope.workstation_root()


def test_home_mismatch_is_rejected(workstation, monkeypatch):
    monkeypatch.setenv("HOME", str(workstation.parent))
    with pytest.raises(ValueError, match="HOME mismatch"):
        scope.workstation_root()


def test_fifo_marker_fails_without_blocking(workstation):
    marker = workstation / ".station-workstation.json"
    marker.unlink()
    os.mkfifo(marker, 0o600)
    with pytest.raises(ValueError, match="marker"):
        scope.workstation_root()


def test_workstation_object_paths_do_not_write_host_locations(workstation, monkeypatch):
    home = Path.home()
    profile = home / ".hermes/profiles/example"
    monkeypatch.setenv("HERMES_HOME", str(profile))
    resolver = paths.PathResolver("private", home)
    assert resolver.project("demo") == workstation / "projects/demo"
    assert resolver.resolve("workspace") == workstation / "projects"
    assert resolver.resolve("hermes_state") == profile
    assert resolver.resolve("runtime") == home / ".agentik/runtime"
    assert resolver.resolve("logs") == home / ".agentik/logs"
    assert resolver.resolve("backups") == home / ".agentik/backups"
    assert resolver.resolve("os_registry") == workstation / "resources/os-registry"
    monkeypatch.setenv("HERMES_HOME", str(workstation.parent))
    with pytest.raises(ValueError, match="escapes"):
        resolver.resolve("hermes_state")


def test_linked_marker_and_escape_are_rejected(workstation, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    escape = workstation / "projects/escape"
    escape.symlink_to(outside, target_is_directory=True)
    assert not scope.permitted_cwd(escape, Path.home())
    marker = workstation / ".station-workstation.json"
    backup = tmp_path / "marker-copy"
    marker.rename(backup)
    marker.symlink_to(backup)
    with pytest.raises(OSError):
        scope.workstation_root()


def test_linked_launcher_and_writable_namespace_are_rejected(workstation):
    executable = workstation / "bin/agk"
    executable.unlink()
    executable.symlink_to("/bin/sh")
    with pytest.raises(ValueError, match="launcher"):
        scope.agk_executable()
    workstation.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        scope.workstation_root()


def test_actual_controller_accepts_only_validated_workstation_project(workstation, monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1 if "has-session" in args else 0, stdout="", stderr="")
    monkeypatch.setattr(agk, "run", run)
    env = agk.Environment("private", Path.home(), workstation / "projects")
    registry = agk.RuntimeRegistry(env)
    try:
        row = registry.create(name="private-synthetic-test", kind="shell", cwd=workstation / "projects", command=["/bin/cat"])
        assert row["cwd"] == str(workstation / "projects")
        assert any("new-session" in args for args in calls)
        with pytest.raises(ValueError, match="trust boundary"):
            registry.create(name="private-outside-test", kind="shell", cwd=workstation.parent, command=["/bin/cat"])
    finally:
        registry.db.close()
