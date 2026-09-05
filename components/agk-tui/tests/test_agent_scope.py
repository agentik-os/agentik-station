"""Legacy specialist policy must agree with real Station identities."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


COMPONENT = Path(__file__).resolve().parents[1]
PLUGIN = COMPONENT / "hermes/plugins/agentik_os"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runtime(monkeypatch):
    package = ModuleType("station_agent_scope_test")
    package.__path__ = [str(PLUGIN)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    tools = ModuleType("tools")
    registry = ModuleType("tools.registry")
    registry.tool_error = lambda message: json.dumps({"error": message})
    registry.tool_result = json.dumps
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setitem(sys.modules, "tools.registry", registry)
    scope = load(package.__name__ + ".workstation", PLUGIN / "workstation.py")
    agents = load(package.__name__ + ".agent_registry", PLUGIN / "agent_registry.py")
    controller = load("station_agent_scope_controller_test", COMPONENT / "scripts/agk_control.py")
    monkeypatch.delenv("STATION_WORKSTATION_ROOT", raising=False)
    monkeypatch.setenv("AGK_AGENT_CATALOG", str(COMPONENT / "hermes/agents"))
    monkeypatch.setenv("AGENTIK_ENVIRONMENT", "agk-station")
    monkeypatch.setenv("USER", "agk-station")
    monkeypatch.setenv("HOME", "/home/agk-station")
    monkeypatch.setattr(scope.os, "getuid", lambda: 1001)
    monkeypatch.setattr(scope.os, "geteuid", lambda: 1001)
    account = SimpleNamespace(pw_uid=1001, pw_name="agk-station", pw_dir="/home/agk-station")
    monkeypatch.setattr(scope.pwd, "getpwuid", lambda _uid: account)
    calls = []
    monkeypatch.setattr(agents, "_runtime_row", lambda name: calls.append(name) or {"name": name})
    def no_native(*_args, **_kwargs):
        raise AssertionError("Selection must not run a process or prepare a workspace")
    monkeypatch.setattr(agents, "_run", no_native)
    monkeypatch.setattr(agents, "_prepare_workspace", no_native)
    return SimpleNamespace(scope=scope, agents=agents, controller=controller, account=account, calls=calls)


@pytest.mark.parametrize("alias", ["operator", "agk-station"])
def test_explicit_legacy_builder_preserves_operator_session_namespace(runtime, monkeypatch, alias):
    monkeypatch.setenv("AGENTIK_ENVIRONMENT", alias)
    result = json.loads(runtime.agents.handle_agent({"action": "status", "agent": "legacy-master-os-builder"}))
    assert result["success"] is True
    assert result["runtime"]["name"] == "agk-station-master-os-builder"
    assert runtime.calls == ["agk-station-master-os-builder"]
    env = runtime.controller.Environment("agk-station", Path.home(), Path.home() / "workspace/projects")
    assert runtime.controller.specialist_definition(env, "legacy-master-os-builder")["id"] == "master-os-builder"


def test_real_operator_without_user_environment_uses_actual_identity(runtime, monkeypatch):
    monkeypatch.delenv("USER")
    monkeypatch.delenv("AGENTIK_ENVIRONMENT")
    assert runtime.agents._environment() == ("agk-station", "operator")


@pytest.mark.parametrize("environment", ["station", "unknown", "private", "mission", "acme-dev", "../operator"])
def test_operator_mislabeled_environment_is_denied_before_runtime_lookup(runtime, monkeypatch, environment):
    monkeypatch.setenv("AGENTIK_ENVIRONMENT", environment)
    result = json.loads(runtime.agents.handle_agent({"action": "status", "agent": "legacy-master-os-builder"}))
    assert "error" in result and runtime.calls == []
    env = runtime.controller.Environment(environment, Path.home(), Path.home() / "workspace/projects")
    with pytest.raises(ValueError, match="environment"):
        runtime.controller.specialist_definition(env, "legacy-master-os-builder")


@pytest.mark.parametrize("change", ["account", "home", "account-home", "root", "setuid"])
def test_operator_alias_cannot_be_claimed_by_wrong_identity(runtime, monkeypatch, change):
    if change == "account":
        runtime.account.pw_name = "zone-acme-dev"
        runtime.account.pw_dir = "/home/zone-acme-dev"
        monkeypatch.setenv("HOME", runtime.account.pw_dir)
    elif change == "home":
        monkeypatch.setenv("HOME", "/home/other")
    elif change == "account-home":
        runtime.account.pw_dir = "/other/agk-station"
    elif change == "root":
        monkeypatch.setattr(runtime.scope.os, "geteuid", lambda: 0)
    else:
        monkeypatch.setattr(runtime.scope.os, "getuid", lambda: 1002)
    result = json.loads(runtime.agents.handle_agent({"action": "status", "agent": "legacy-master-os-builder"}))
    assert "error" in result and runtime.calls == []


@pytest.mark.parametrize("scope", [["operator"], ["agk-station"], ["operator", "agk-station"]])
def test_intended_operator_agents_share_identity_alias_policy(runtime, monkeypatch, scope):
    monkeypatch.setattr(runtime.agents, "_definition", lambda _id: {"id": "other-agent", "scope": scope})
    result = json.loads(runtime.agents.handle_agent({"action": "status", "agent": "other-agent"}))
    assert result["success"] is True
    assert runtime.calls == ["agk-station-other-agent"]


@pytest.mark.parametrize("scope", [["private"], ["mission"], ["global"], ["*"], [], "operator", [None]])
def test_operator_has_no_universal_agent_scope_bypass(runtime, monkeypatch, scope):
    monkeypatch.setattr(runtime.agents, "_definition", lambda _id: {"id": "other-agent", "scope": scope})
    result = json.loads(runtime.agents.handle_agent({"action": "status", "agent": "other-agent"}))
    assert "error" in result and runtime.calls == []


@pytest.mark.parametrize("name", ["operator", "agentik", "mission", "private"])
def test_legacy_account_requires_its_exact_home_and_scope(runtime, monkeypatch, name):
    runtime.account.pw_name = name
    runtime.account.pw_dir = f"/home/{name}"
    monkeypatch.setenv("HOME", runtime.account.pw_dir)
    assert runtime.scope.agent_environment(name, Path.home()) == (name, name)
    with pytest.raises(ValueError, match="environment"):
        runtime.scope.agent_environment("agk-station", Path.home())


def test_validated_personal_workstation_retains_private_agent_scope(runtime, monkeypatch, tmp_path):
    root = tmp_path / "station"
    root.mkdir(mode=0o700)
    for relative in ("personal", "personal/home", "projects", "bin"):
        (root / relative).mkdir(mode=0o700)
    monkeypatch.setattr(runtime.scope.os, "getuid", lambda: root.stat().st_uid)
    monkeypatch.setattr(runtime.scope.os, "geteuid", lambda: root.stat().st_uid)
    marker = root / ".station-workstation.json"
    marker.write_text(json.dumps({"schema": 1, "mode": "workstation", "root": str(root),
                                 "uid": root.stat().st_uid,
                                 "profile": "station-" + hashlib.sha256(str(root).encode()).hexdigest()[:12]}))
    marker.chmod(0o600)
    monkeypatch.setenv("HOME", str(root / "personal/home"))
    monkeypatch.setenv("STATION_WORKSTATION_ROOT", str(root))
    monkeypatch.setenv("AGENTIK_ENVIRONMENT", "private")
    result = json.loads(runtime.agents.handle_agent({"action": "status", "agent": "legacy-master-os-builder"}))
    assert result["success"] is True
    assert runtime.calls == ["private-master-os-builder"]
    with pytest.raises(ValueError, match="private"):
        runtime.scope.agent_environment("operator", Path.home())
    marker.unlink()
    with pytest.raises(OSError):
        runtime.scope.agent_environment("private", Path.home())


def test_explicit_legacy_builder_retains_its_original_scope_without_bypass():
    import yaml
    definition = yaml.safe_load((COMPONENT / "hermes/agents/master-os-builder/agent.yaml").read_text())
    assert definition["scope"] == ["operator", "agk-station", "agentik", "mission", "private"]


@pytest.mark.parametrize("agent,os_id", [
    ("BuilderOS", "builder-os"), ("builder", "builder-os"),
    ("builder-os", "builder-os"), ("master-os-builder", "builder-os"),
    ("build-os", "builder-os"), ("Stepper", "stepper-os"),
    ("steper", "stepper-os"), ("steper-os", "stepper-os"),
    ("stepper-os", "stepper-os"), ("Librarian", "librarian-os"),
    ("librarian-os", "librarian-os"),
])
@pytest.mark.parametrize("action", ["start", "status", "message", "logs"])
def test_canonical_natural_language_tool_route_never_touches_legacy_runtime(runtime, agent, os_id, action):
    result = json.loads(runtime.agents.handle_agent({
        "action": action, "agent": agent, "instruction": "Use this OS to build my new system",
    }))
    assert result["agent"] == os_id
    assert result["success"] is False and result["executed"] is False
    assert result["status"] == "STATION_HANDOFF_REQUIRED"
    assert result["installed_version"] is None and result["director_profile"] is None
    assert result["scope"] == {"zone": None, "instance": None}
    assert result["commands_are_templates"] is True
    assert result["resolve_argv"] == [
        "sudo", "station", "os", "resolve", "--name", os_id,
        "--zone", "<zone>", "--instance", "<instance>",
    ]
    assert runtime.calls == []


def test_explicit_scope_renders_exact_plan_but_never_claims_authority(runtime):
    result = json.loads(runtime.agents.handle_agent({
        "action": "start", "agent": "BuilderOS", "zone": "os", "instance": "builder",
    }))
    assert result["chat_plan_argv"] == [
        "sudo", "station", "os", "instance", "chat", "--zone", "os",
        "--instance", "builder", "--plan",
    ]
    assert result["commands_are_templates"] is False
    assert result["executed"] is False and result["success"] is False
    assert "not run" in result["next_action"]
    assert runtime.calls == []


@pytest.mark.parametrize("scope", [
    {"zone": "os"}, {"instance": "builder"}, {"zone": "../other", "instance": "builder"},
    {"zone": "os", "instance": "--help"}, {"zone": "os", "instance": "bad\nvalue"},
    {"zone": "os", "instance": 42}, {"zone": "", "instance": "builder"},
])
def test_canonical_handoff_rejects_ambiguous_or_unsafe_selectors(runtime, scope):
    result = json.loads(runtime.agents.handle_agent({"action": "start", "agent": "builder", **scope}))
    assert "error" in result
    assert runtime.calls == []


def test_router_prompt_and_slash_command_distinguish_canonical_and_legacy(runtime):
    prompt = runtime.agents.agent_router_prompt()
    assert "Station's canonical builder-os" in prompt
    assert "legacy-master-os-builder" in prompt
    assert "not a launched session" in prompt
    service = runtime.agents.AgentCommandService()
    listing = service.dispatch("list")
    assert "builder-os · canonical Station OS" in listing
    assert "stepper-os · canonical Station OS" in listing
    assert "librarian-os · canonical Station OS" in listing
    assert "legacy-master-os-builder" in listing
    result = json.loads(service.dispatch('start BuilderOS "build a new OS"'))
    assert result["status"] == "STATION_HANDOFF_REQUIRED" and not result["executed"]
    assert runtime.calls == []


@pytest.mark.parametrize("agent", ["builder", "builder-os", "master-os-builder", "stepper", "librarian-os"])
def test_controller_canonical_start_stops_before_workspace_and_rmux(runtime, monkeypatch, agent):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Canonical handoff must not prepare a legacy workspace or launch")
    monkeypatch.setattr(runtime.controller, "prepare_specialist_workspace", forbidden)
    env = runtime.controller.Environment("agk-station", Path.home(), Path.home() / "workspace/projects")
    with pytest.raises(ValueError, match="sudo station os resolve"):
        runtime.controller.start_specialist(env, SimpleNamespace(ensure_specialist=forbidden), agent)


def test_plugin_listing_never_advertises_legacy_as_canonical_builder(runtime):
    listing = json.loads(runtime.agents.handle_agent({"action": "list"}))
    assert "master-os-builder" not in {agent["id"] for agent in listing["agents"]}
    assert "legacy-master-os-builder" in {agent["id"] for agent in listing["agents"]}
    assert {os["agent"] for os in listing["station_os"]} == {"builder-os", "stepper-os", "librarian-os"}
    assert all(not os["executed"] and os["installed_version"] is None for os in listing["station_os"])
