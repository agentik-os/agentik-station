"""Personal entrypoints may not silently call legacy installers or gateways."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

COMPONENT = Path(__file__).parents[1]


@pytest.fixture
def context(tmp_path):
    root = tmp_path / "station"
    root.mkdir(mode=0o700)
    for directory in ("personal", "personal/home", "projects", "bin"):
        (root / directory).mkdir(mode=0o700)
    profile = "station-" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    marker = root / ".station-workstation.json"
    marker.write_text(json.dumps({"schema": 1, "mode": "workstation", "root": str(root), "profile": profile, "uid": os.getuid()}))
    marker.chmod(0o600)
    installed = root / "tools/agk-terminal"
    helper = installed / "hermes/plugins/agentik_os/workstation.py"
    helper.parent.mkdir(parents=True)
    shutil.copyfile(COMPONENT / "hermes/plugins/agentik_os/workstation.py", helper)
    (installed / "scripts").mkdir()
    trace = root / "trace"
    stub = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$STATION_GUARD_TRACE"\n'
    for filename in (root / "bin/hermes", root / "bin/composio", installed / "scripts/sync-hermes.sh", installed / "scripts/install-shared-hermes.sh", installed / "scripts/topology.py", installed / "scripts/client_control.py"):
        filename.write_text(stub)
        filename.chmod(0o700)
    env = {
        "PATH": f"{root}/bin:/usr/bin:/bin", "HOME": str(root / "personal/home"),
        "USER": "station-workstation", "AGK_ENVIRONMENT": "private",
        "AGK_TERMINAL_ROOT": str(installed), "STATION_WORKSTATION_ROOT": str(root),
        "STATION_GUARD_TRACE": str(trace),
    }
    return root, env, trace


def run(script, args, env):
    return subprocess.run(["/bin/bash", str(COMPONENT / script), *args], env=env, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("args", [
    ["hermes", "sync"], ["hermes", "install-shared"],
    ["hermes", "gateway"], ["hermes", "gateway", "setup"],
    ["hermes", "gateway", "install"], ["hermes", "gateway", "start"],
    ["hermes", "gateway", "restart"], ["hermes", "gateway", "run"],
    ["topology", "apply", "--yes"], ["topology", "refresh", "--yes"],
])
def test_workstation_blocks_legacy_mutations_before_dispatch(context, args):
    _root, env, trace = context
    result = run("bin/agk-terminal", args, env)
    assert result.returncode == 2
    assert "agentik-station" in result.stderr
    assert not trace.exists()


@pytest.mark.parametrize("provider", ["hermes", "openrouter", "claude", "codex", "opencode"])
@pytest.mark.parametrize("flags", [[], ["--no-login"]])
def test_workstation_provider_install_never_downloads_or_syncs(context, provider, flags):
    _root, env, trace = context
    result = run("scripts/provider.sh", ["install", provider, *flags], env)
    assert result.returncode == 2
    assert "repair" in result.stderr and "model" in result.stderr
    assert not trace.exists()


def test_exact_scoped_gateway_status_is_preserved(context):
    _root, env, trace = context
    result = run("bin/agk-terminal", ["hermes", "gateway", "status"], env)
    assert result.returncode == 0
    assert trace.read_text() == "gateway status\n"


def test_gateway_status_cannot_smuggle_another_action_or_profile(context):
    _root, env, trace = context
    result = run("bin/agk-terminal", ["hermes", "gateway", "status", "--profile", "other"], env)
    assert result.returncode == 2
    assert not trace.exists()


def test_provider_list_stays_available_without_installing(context):
    _root, env, trace = context
    result = run("scripts/provider.sh", ["list"], env)
    assert result.returncode == 0
    assert "PROVIDER" in result.stdout
    assert not trace.exists()


def test_invalid_workstation_marker_never_falls_through_to_legacy(context):
    root, env, trace = context
    (root / ".station-workstation.json").unlink()
    result = run("bin/agk-terminal", ["hermes", "gateway", "start"], env)
    assert result.returncode == 2
    assert "Invalid Station Workstation scope" in result.stderr
    assert not trace.exists()


@pytest.mark.parametrize("args", [["client", "bootstrap"], ["client", "activate", "example"], ["client", "--help"]])
def test_personal_route_does_not_create_legacy_client_profiles(context, args):
    _root, env, trace = context
    result = run("bin/agk", args, env)
    assert result.returncode == 2
    assert "independent-UID Zones" in result.stderr
    assert not trace.exists()


def test_host_gateway_and_topology_dispatch_are_unchanged(context):
    _root, env, trace = context
    env.pop("STATION_WORKSTATION_ROOT")
    result = run("bin/agk-terminal", ["hermes", "gateway", "start"], env)
    assert result.returncode == 0
    assert trace.read_text() == "gateway start\n"
    result = run("bin/agk-terminal", ["topology", "apply", "--yes"], env)
    assert result.returncode == 0
    assert trace.read_text().endswith("apply --yes\n")
