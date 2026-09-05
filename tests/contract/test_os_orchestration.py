from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from agentik_station.errors import ValidationError
from agentik_station.os_discovery import bind_instance, resolve_package
from agentik_station.os_runtime import compile_os_to_hermes
from agentik_station.os_contract import doctor_os_source
from agentik_station.cli import build_parser
from agentik_station.hermes_platforms import build_gateway_argv

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["builder", "BuilderOS", "build-os", "master-os-builder", "builder-os"])
def test_builder_alias_resolves_capability_not_authority(name):
    result = resolve_package(ROOT, name)
    assert result["os_id"] == "builder-os"
    assert result["director_role"] == "master-os-builder"
    assert result["access"]["execution_authorized"] is False
    assert result["runtime_state"] == "NOT_SELECTED"


def test_instance_chat_is_an_explicit_native_cli_not_a_gateway_start():
    args = build_parser().parse_args(["os", "instance", "chat", "--zone", "os", "--instance", "stepper", "--plan"])
    assert args.instance_command == "chat" and args.plan
    argv = build_gateway_argv({"unix_user": "z-factory-os", "state_root": "/var/lib/station/zones/os",
                               "hermes_home": "/var/lib/station/zones/os/hermes"}, "chat", runtime_uid=1200,
                              hermes_binary=Path("/usr/local/bin/hermes"), director_profile="i-reviewed-director", instance_id="stepper")
    assert argv[-3:] == ["--profile", "i-reviewed-director", "chat"]
    assert "HERMES_HOME=/var/lib/station/zones/os/os-instances/stepper/hermes" in argv
    assert "HOME=/var/lib/station/zones/os/home" in argv
    assert not {"gateway", "install", "start", "sudo"}.intersection(argv)


@pytest.mark.parametrize("name", ["stepper", "steper", "stepper-os"])
def test_stepper_is_discoverable_by_user_names(name):
    result = resolve_package(ROOT, name)
    assert result["os_id"] == "stepper-os"
    assert set(result["roles"]) == {"map-steward", "shaper", "sequencer"}


@pytest.mark.parametrize("name", ["../../builder", "unknown-os", "builder;sudo", ""])
def test_bad_or_unknown_selection_is_actionable_not_fallback(name):
    with pytest.raises(ValidationError):
        resolve_package(ROOT, name)


def test_resolver_never_selects_another_os_instance():
    with pytest.raises(ValidationError, match="another OS"):
        bind_instance(resolve_package(ROOT, "builder"), {"os_id": "devops-os"})


@pytest.mark.parametrize("cases", [[1, 2, 3, 4], [{"valid": False}] * 4,
                                    [{"valid": True}] * 4, [{"valid": 1}] * 4])
def test_stepper_doctor_handles_bad_evaluation_declarations_without_executing_them(tmp_path, cases):
    source = tmp_path / "stepper"
    shutil.copytree(ROOT / "os/stepper", source)
    (source / "evals/CASES.json").write_text(json.dumps({"cases": cases}))
    result = doctor_os_source(source)
    assert not result.ok
    assert any(issue["name"] == "semantic:stepper" for issue in result.issues)


def test_every_devops_profile_receives_audit_system_prompt_and_native_defaults(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    output = tmp_path / "compiled"
    compiled = compile_os_to_hermes(ROOT / "os/devops", output, project_root=workspace)
    assert len(compiled["profiles"]) == 6
    for profile in compiled["profiles"]:
        directory = output / "profiles" / profile
        soul = (directory / "SOUL.md").read_text()
        for text in ("Cartographie du produit", "Accessibilité", "doubles clics", "compilation réussie", "partiellement vérifié", "sans autorisation"):
            assert text in soul
        assert (directory / "skills/station-orchestration/SKILL.md").is_file()
        config = yaml.safe_load((directory / "config.yaml").read_text())
        assert config["agent"]["max_turns"] == 64
        assert config["delegation"]["max_spawn_depth"] == 2
        assert config["delegation"]["max_concurrent_children"] == 3
        assert config["delegation"]["subagent_auto_approve"] is False
        assert config["tools"]["tool_search"]["enabled"] == "on"
        assert config["kanban"]["dispatch_in_gateway"] is False
        assert config["kanban"]["review_dispatch"] is False
        assert config["platforms"]["api_server"]["enabled"] is False
        assert "budget" not in config
        assert json.loads((directory / "OS_ROUTING.json").read_text())["os_id"] == "devops-os"


def _personal_helper():
    spec = importlib.util.spec_from_file_location("personal_os", ROOT / "scripts/station_workstation_os.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_instance_prompt_distinguishes_transient_children_from_persistent_roles(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "compiled"
    result = compile_os_to_hermes(ROOT / "os/stepper", output, workspace_root=workspace,
                                  zone_id="os", instance_id="stepper")
    for profile in result["profiles"]:
        soul = (output / "profiles" / profile / "SOUL.md").read_text()
        assert "delegate_task creates transient children" in soul
        assert "it has no profile selector" in soul
        assert "For every delegation use the exact native profile" not in soul
        skill = (output / "profiles" / profile / "skills/station-orchestration/SKILL.md").read_text()
        assert "--oneshot" in skill and "--query-file" in skill
        assert "role=leaf" not in skill and "role=orchestrator" not in skill


@pytest.mark.skipif(os.geteuid() == 0, reason="Personal deployment deliberately requires a non-root UID")
def test_personal_compiler_namespaces_complete_team_and_readback_detects_drift(tmp_path):
    root = tmp_path / "station"
    root.mkdir(mode=0o700)
    helper = _personal_helper()
    previous = os.umask(0o077)
    try:
        output = root / "resources/os-distributions/builder-os"
        result = helper.compile_personal(root, "station-test", "builder-os", output)
        assert result["boundary"] == "personal-same-uid"
        assert all(name.startswith("w-") for name in result["profiles"])
        assert result == helper.compile_personal(root, "station-test", "builder-os", output, check=True)
        director = output / "profiles" / result["nano_director"]
        personal = json.loads((director / "PERSONAL.json").read_text())
        assert personal["zone_isolation"] is False
        assert personal["role_profile_map"] == result["role_profile_map"]
        (director / "SOUL.md").write_text("changed")
        with pytest.raises(ValidationError, match="differs"):
            helper.compile_personal(root, "station-test", "builder-os", output, check=True)
    finally:
        os.umask(previous)


def test_personal_compiler_refuses_escape_and_unknown_bundle(tmp_path, monkeypatch):
    helper = _personal_helper()
    monkeypatch.setattr(helper.os, "geteuid", lambda: 501)
    root = tmp_path / "station"
    root.mkdir(mode=0o700)
    with pytest.raises(ValidationError, match="destination"):
        helper.compile_personal(root, "station-test", "builder-os", tmp_path / "escape")
    with pytest.raises(ValidationError, match="canonical bundled"):
        helper.compile_personal(root, "station-test", "devops-os", root / "resources/os-distributions/devops-os")
