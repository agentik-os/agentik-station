from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "agk_control.py"
SPEC = importlib.util.spec_from_file_location("agk_control_tested", MODULE_PATH)
assert SPEC and SPEC.loader
agk = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agk
SPEC.loader.exec_module(agk)


def completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_session_types_and_filter_language():
    assert {"hermes", "claude", "codex", "opencode", "openrouter"} <= agk.TYPES
    rows = [{"type": "hermes", "environment": "mission", "client": "moonbase",
             "project": "growth", "status": "running", "name": "mission-moonbase-growth"}]
    assert agk.filtered(rows, "type:hermes env:mission client:moonbase") == rows
    assert agk.filtered(rows, "status:failed") == []


def test_create_persists_runtime_metadata_and_rmux_marker(tmp_path, monkeypatch):
    calls = []
    def fake_run(*args, check=True):
        calls.append(args)
        return completed(returncode=1 if args[1:3] == ("has-session", "-t") else 0)
    monkeypatch.setattr(agk, "run", fake_run)
    env = agk.Environment("agentik", tmp_path, tmp_path / "workspace" / "projects")
    registry = agk.RuntimeRegistry(env)
    row = registry.create(name="agentik-hermes-dev", kind="hermes", cwd=tmp_path,
                          project="PRJ-1", native_session="S-1",
                          command=["hermes", "--resume", "S-1"])
    assert row["type"] == "hermes"
    assert row["native_session"] == "S-1"
    assert row["project"] == "PRJ-1"
    create_call = next(call for call in calls if call[1] == "new-session")
    assert "AGENTIK_RMUX=1" in create_call
    assert "AGENTIK_ENVIRONMENT=agentik" in create_call
    assert any(value.startswith("PATH=") for value in create_call)


def test_create_rejects_cwd_outside_linux_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(agk, "run", lambda *args, **kwargs: completed(returncode=1))
    registry = agk.RuntimeRegistry(agk.Environment("private", tmp_path / "private", tmp_path / "private" / "projects"))
    registry.env.home.mkdir(parents=True, exist_ok=True)
    try:
        registry.create(name="private-invalid-work", kind="shell", cwd=tmp_path / "mission")
    except ValueError as exc:
        assert "trust boundary" in str(exc)
    else:
        raise AssertionError("cross-environment cwd was accepted")


def test_reconcile_marks_missing_runtime_interrupted(tmp_path, monkeypatch):
    monkeypatch.setattr(agk, "run", lambda *args, **kwargs: completed(returncode=1))
    registry = agk.RuntimeRegistry(agk.Environment("operator", tmp_path, tmp_path))
    now = 1.0
    registry.db.execute("""
      INSERT INTO runtime_sessions(
        id,name,type,environment,rmux_session,cwd,status,created_at,last_activity,
        native_session,command_json
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, ("RT-1", "operator-maintenance", "shell", "operator",
           "operator-maintenance", str(tmp_path), "running", now, now, None, "[]"))
    registry.db.commit()
    changed, unmanaged = registry.reconcile()
    assert changed == 1 and unmanaged == []
    assert registry.get("RT-1")["status"] == "interrupted"


def test_default_resume_commands_use_documented_cli(monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")
    assert agk.default_command("hermes", "S-1") == ["/verified/hermes", "--resume", "S-1"]
    assert agk.default_command("hermes", "S-2", "research") == [
        "/verified/hermes", "--profile", "research", "--resume", "S-2"
    ]
    assert agk.default_command("claude", "C-1") == [
        "/verified/env", "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1",
        "/verified/claude", "--dangerously-skip-permissions", "--resume", "C-1"
    ]
    assert agk.default_command("codex", "X-1") == ["/verified/codex", "resume", "X-1"]


def test_openrouter_sessions_pin_the_supported_model(monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")
    monkeypatch.delenv("AGK_OPENROUTER_MODEL", raising=False)
    assert agk.default_command("openrouter") == [
        "/verified/hermes", "--provider", "openrouter", "--model", "stealth/ox-alpha"
    ]


def test_specialist_start_binds_catalog_profile_and_durable_rmux(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    definition = catalog / "kitchen-agent"
    definition.mkdir(parents=True)
    (definition / "agent.yaml").write_text(
        "id: kitchen-agent\n"
        "name: Kitchen Agent\n"
        "version: 1.2.3\n"
        "scope: [mission]\n"
        "profile: kitchen\n"
        "os: [kitchen-os@1.0.0]\n"
        "prompt: prompt.md\n",
        encoding="utf-8",
    )
    (definition / "prompt.md").write_text("Run the kitchen OS.\n", encoding="utf-8")
    (tmp_path / ".hermes/profiles/kitchen").mkdir(parents=True)
    monkeypatch.setenv("AGK_AGENT_CATALOG", str(catalog))
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")

    class Runtime:
        def __init__(self):
            self.created = []

        def has_session(self, _name):
            return False

        def create(self, name, kind, cwd, environment, command):
            self.created.append((name, kind, cwd, environment, command))

    runtime = Runtime()
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace/clients")
    registry = agk.RuntimeRegistry(env, runtime=runtime)

    row, created = agk.start_specialist(env, registry, "kitchen-agent")

    workspace = tmp_path / ".agentik/agents/kitchen-agent/workspace"
    assert created is True
    assert row["name"] == "mission-kitchen-agent"
    assert row["hermes_profile"] == "kitchen"
    assert agk.json.loads(row["command_json"]) == [
        "/verified/hermes", "-p", "kitchen", "--in", str(workspace)
    ]
    assert runtime.created[0][0] == "mission-kitchen-agent"
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "Run the kitchen OS.\n"
    assert agk.json.loads(
        (workspace / ".agentik-agent.json").read_text(encoding="utf-8")
    )["os"] == ["kitchen-os@1.0.0"]


def test_specialist_scope_is_enforced_outside_operator(tmp_path, monkeypatch):
    definition = tmp_path / "catalog/operator-agent"
    definition.mkdir(parents=True)
    (definition / "agent.yaml").write_text(
        "id: operator-agent\nscope: [operator]\nprompt: prompt.md\n",
        encoding="utf-8",
    )
    (definition / "prompt.md").write_text("Operate.\n", encoding="utf-8")
    monkeypatch.setenv("AGK_AGENT_CATALOG", str(tmp_path / "catalog"))
    env = agk.Environment("private", tmp_path, tmp_path / "workspace/projects")

    try:
        agk.specialist_definition(env, "operator-agent")
    except PermissionError as error:
        assert "not allowed in private" in str(error)
    else:
        raise AssertionError("cross-profile specialist launch was accepted")


def test_claude_workspace_trust_is_persisted_without_losing_existing_state(tmp_path):
    config = tmp_path / ".claude.json"
    config.write_text(
        '{"theme":"dark","projects":{"/existing":{"custom":true}}}\n',
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    agk.trust_claude_workspace(tmp_path, workspace)

    document = agk.json.loads(config.read_text(encoding="utf-8"))
    assert document["theme"] == "dark"
    assert document["projects"]["/existing"] == {"custom": True}
    assert document["projects"][str(workspace)]["hasTrustDialogAccepted"] is True
    assert config.stat().st_mode & 0o777 == 0o600


def test_kill_yes_uses_the_confirmed_noninteractive_path(monkeypatch):
    row = {"name": "agk-test-session"}

    class Registry:
        def __init__(self):
            self.terminated = []

        def reconcile(self):
            return 0, []

        def get(self, target):
            return row if target == row["name"] else None

        def terminate(self, target):
            self.terminated.append(target)
            return target

    registry = Registry()
    monkeypatch.setattr(
        agk.Environment,
        "current",
        lambda: agk.Environment("operator", Path("/tmp"), Path("/tmp")),
    )
    monkeypatch.setattr(agk, "RuntimeRegistry", lambda _env: registry)
    monkeypatch.setattr(sys, "argv", ["agk", "kill", "--yes", row["name"]])

    assert agk.main() == 0
    assert registry.terminated == [row]


def test_close_yes_terminates_then_archives_without_a_second_prompt(monkeypatch):
    row = {"name": "agk-close-session"}

    class Registry:
        def __init__(self):
            self.actions = []

        def reconcile(self):
            return 0, []

        def get(self, target):
            return row if target == row["name"] else None

        def terminate(self, target):
            self.actions.append(("terminate", target))
            return target

        def archive(self, target):
            self.actions.append(("archive", target))
            return target

    registry = Registry()
    monkeypatch.setattr(
        agk.Environment,
        "current",
        lambda: agk.Environment("operator", Path("/tmp"), Path("/tmp")),
    )
    monkeypatch.setattr(agk, "RuntimeRegistry", lambda _env: registry)
    monkeypatch.setattr(sys, "argv", ["agk", "close", "--yes", row["name"]])

    assert agk.main() == 0
    assert registry.actions == [("terminate", row), ("archive", row)]


def test_rmux_terminate_retries_and_fails_if_session_survives(monkeypatch):
    calls = []

    def fake_run(*args, check=True):
        calls.append(args)
        if args[1] == "has-session":
            return completed(returncode=0)
        return completed(stdout="still busy", returncode=1)

    monkeypatch.setattr(agk, "run", fake_run)
    try:
        agk.RmuxRuntime().terminate("agk-stuck-session")
    except RuntimeError as exc:
        assert "still alive" in str(exc)
    else:
        raise AssertionError("a surviving RMUX session was reported as closed")
    assert sum(call[1] == "kill-session" for call in calls) == 2


def test_purge_yes_removes_the_exact_runtime_without_prompt(monkeypatch):
    row = {"name": "agk-obsolete-session"}

    class Registry:
        def __init__(self):
            self.purged = []

        def reconcile(self):
            return 0, []

        def get(self, target):
            return row if target == row["name"] else None

        def purge(self, target):
            self.purged.append(target)
            return target["name"]

    registry = Registry()
    monkeypatch.setattr(
        agk.Environment,
        "current",
        lambda: agk.Environment("operator", Path("/tmp"), Path("/tmp")),
    )
    monkeypatch.setattr(agk, "RuntimeRegistry", lambda _env: registry)
    monkeypatch.setattr(sys, "argv", ["agk", "purge", "--yes", row["name"]])

    assert agk.main() == 0
    assert registry.purged == [row]


def test_responsive_layout_and_navigation_model():
    assert agk.layout_mode(60, 30) == "compact"
    assert agk.layout_mode(90, 24) == "standard"
    assert agk.layout_mode(140, 40) == "wide"
    left, right = agk.pane_widths(140, "wide")
    assert left >= 38 and right > left
    assert agk.pane_widths(80, "standard") == (80, 0)
    assert agk.cycle_view("sessions") == "projects"
    assert agk.cycle_view("sessions", reverse=True) == "settings"


def test_public_single_user_environment_config(tmp_path, monkeypatch):
    config = tmp_path / ".config/agk/environment.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"environment: mission\nprojects_root: {tmp_path}/work/clients\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USER", "public-user")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(config))
    env = agk.Environment.current()
    assert env.name == "mission"
    assert env.home == tmp_path
    assert env.projects == tmp_path / "work/clients"


def test_station_operator_uses_real_identity_and_matches_native_tui(tmp_path, monkeypatch):
    monkeypatch.setattr(agk.pwd, "getpwuid", lambda _: SimpleNamespace(pw_name="agk-station", pw_dir=str(tmp_path)))
    monkeypatch.setenv("USER", "moonbase")
    monkeypatch.setenv("HOME", "/other/account")
    monkeypatch.setenv("AGK_ENVIRONMENT", "foreign")
    env = agk.Environment.current()
    assert env.name == "agk-station"
    assert env.home == tmp_path
    assert env.projects == tmp_path / "workspace/projects"


def test_public_environment_rejects_unknown_scope(tmp_path, monkeypatch):
    config = tmp_path / "environment.yaml"
    config.write_text("environment: super-root\n", encoding="utf-8")
    monkeypatch.setenv("USER", "public-user")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(config))
    try:
        agk.Environment.current()
    except SystemExit as exc:
        assert "Unsupported AGK environment" in str(exc)
    else:
        raise AssertionError("unknown public environment was accepted")


def test_os_registry_prefers_explicit_path(tmp_path, monkeypatch):
    target = tmp_path / "registry"
    monkeypatch.setenv("AGK_OS_REGISTRY", str(target))
    assert agk.os_registry_path() == target


def test_session_sections_prioritize_attention_then_active_then_recent():
    rows = [
        {"status": "idle", "name": "recent"},
        {"status": "working", "name": "active"},
        {"status": "failed", "name": "failed"},
    ]
    sections = agk.session_sections(rows)
    assert [name for name, _ in sections] == ["ATTENTION", "ACTIVE", "RECENT"]
    assert [values[0]["name"] for _, values in sections] == ["failed", "active", "recent"]


def test_age_format_is_compact_and_stable():
    assert agk.format_age(990, now=1000) == "10s"
    assert agk.format_age(700, now=1000) == "5m"
    assert agk.format_age(1000 - 7200, now=1000) == "2h"


def test_mcp_inventory_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda _name: None)
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace/clients")
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes/config.yaml").write_text(
        "mcp_servers:\n  github:\n    command: secret-command\n    env:\n      TOKEN: secret\n  browser:\n    url: https://example.invalid\n",
        encoding="utf-8",
    )
    assert agk.mcp_inventory(env) == [
        {"name": "browser", "transport": "http", "status": "configured", "toolkits": []},
        {"name": "github", "transport": "stdio", "status": "configured", "toolkits": []},
    ]
    assert "secret" not in repr(agk.mcp_inventory(env))


def test_mcp_inventory_includes_composio_connection_without_credentials(tmp_path, monkeypatch):
    env = agk.Environment("operator", tmp_path, tmp_path / "workspace")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key","token":"never-read"}', encoding="utf-8")
    inventory = tmp_path / ".agentik/composio-connections.json"
    inventory.parent.mkdir()
    inventory.write_text(
        '{"schema_version":1,"toolkits":['
        '{"name":"github","status":"active","connections":1}]}',
        encoding="utf-8",
    )
    assert agk.mcp_inventory(env) == [{
        "name": "Composio",
        "transport": "CLI · link/tools list",
        "status": "connected",
        "toolkits": [{"name": "github", "status": "active", "connections": 1}],
    }]
    assert "never-read" not in repr(agk.mcp_inventory(env))


def test_mcp_inventory_rejects_composio_placeholder_auth(tmp_path, monkeypatch):
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":null,"org_id":null}', encoding="utf-8")
    assert agk.mcp_inventory(env) == [{
        "name": "Composio",
        "transport": "CLI · link/tools list",
        "status": "setup-required",
        "toolkits": [],
    }]


def test_refresh_mcp_inventory_uses_current_profile_and_flattens_toolkits(tmp_path, monkeypatch):
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace/clients")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key"}', encoding="utf-8")
    cache = tmp_path / ".agentik/composio-connections.json"
    cache.parent.mkdir()
    cache.write_text(
        '{"schema_version":1,"toolkits":['
        '{"name":"gmail","status":"active","connections":1}]}',
        encoding="utf-8",
    )
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return completed(stdout='{"authenticated":true}')

    monkeypatch.setattr(agk.subprocess, "run", fake_run)

    items = agk.refresh_mcp_inventory(env)

    assert calls[0][0][-2:] == ["refresh", "--json"]
    assert calls[0][1]["env"]["HOME"] == str(tmp_path)
    assert calls[0][1]["env"]["USER"] == "mission"
    assert agk.mcp_display_rows(items) == [
        {
            "name": "Composio",
            "transport": "CLI · link/tools list",
            "status": "connected",
            "toolkits": [{"name": "gmail", "status": "active", "connections": 1}],
        },
        {
            "name": "Composio / gmail",
            "transport": "connected toolkit",
            "status": "active",
            "toolkits": [],
        },
    ]


def test_refresh_mcp_inventory_redacts_subprocess_failure(tmp_path, monkeypatch):
    env = agk.Environment("operator", tmp_path, tmp_path / "workspace")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        agk.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=9, stdout="", stderr="api_key=never-expose"
        ),
    )

    try:
        agk.refresh_mcp_inventory(env)
    except RuntimeError as error:
        assert str(error) == "Composio inventory refresh failed with exit code 9"
        assert "never-expose" not in str(error)
    else:
        raise AssertionError("a failed inventory refresh was accepted")


def test_mcp_inventory_surfaces_invalid_hermes_config_in_strict_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda _name: None)
    env = agk.Environment("private", tmp_path, tmp_path / "workspace/projects")
    config = tmp_path / ".hermes/config.yaml"
    config.parent.mkdir()
    config.write_text("mcp_servers: [not, an, object]\n", encoding="utf-8")

    try:
        agk.mcp_inventory(env, strict=True)
    except RuntimeError as error:
        assert "mcp_servers must be an object" in str(error)
    else:
        raise AssertionError("an invalid Hermes MCP config was accepted")


def test_skill_inventory_reports_identity_and_source_only(tmp_path):
    env = agk.Environment("private", tmp_path, tmp_path / "workspace/projects")
    skill = tmp_path / ".hermes/skills/research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("private instructions", encoding="utf-8")
    assert agk.skill_inventory(env) == [
        {"name": "research", "source": "hermes", "status": "installed"},
    ]


def test_rmux_adapter_uses_stable_pane_id_for_respawn(monkeypatch):
    calls = []
    def fake_run(*args, check=True):
        calls.append(args)
        if args[1] == "list-panes":
            return completed("%42\n")
        return completed()
    monkeypatch.setattr(agk, "run", fake_run)
    runtime = agk.RmuxRuntime()
    runtime.respawn("mission-moonbase", "/home/mission/workspace", ["hermes", "--resume", "S-1"])
    command = calls[-1]
    assert command[1:5] == ("respawn-pane", "-k", "-t", "%42")
    assert ":1.1" not in command
    runtime.send_input("mission-moonbase", "continue safely")
    assert calls[-2][1:] == ("send-keys", "-t", "%42", "-l", "continue safely")
    assert calls[-1][1:] == ("send-keys", "-t", "%42", "Enter")


@pytest.fixture
def controlled_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")
    class Runtime:
        def __init__(self):
            self.live = set()
            self.calls = []
        def has_session(self, name):
            return name in self.live
        def create(self, name, kind, cwd, environment, command):
            self.calls.append(("create", name, list(command)))
            self.live.add(name)
        def rename(self, old, new):
            self.calls.append(("rename", old, new))
            self.live.remove(old)
            self.live.add(new)
        def terminate(self, name):
            self.calls.append(("terminate", name))
            self.live.discard(name)
        def respawn(self, name, cwd, command):
            self.calls.append(("respawn", name, list(command)))
        def panes(self):
            return completed("\n".join(f"{name}|0|1|synthetic" for name in self.live))
    runtime = Runtime()
    registry = agk.RuntimeRegistry(agk.Environment("mission", tmp_path, tmp_path / "workspace"), runtime)
    yield registry, runtime
    registry.db.close()


def test_fork_without_native_id_preserves_named_hermes_profile(controlled_registry):
    registry, runtime = controlled_registry
    source = registry.create(name="mission-source", kind="hermes", cwd=registry.env.home,
                             command=["/verified/hermes", "--profile", "research"], hermes_profile="research")
    fork = registry.fork(source, "mission-fork")
    assert fork["hermes_profile"] == "research"
    assert runtime.calls[-1][2] == ["/verified/hermes", "--profile", "research"]


def test_restart_of_archived_session_restores_visible_record(controlled_registry):
    registry, runtime = controlled_registry
    row = registry.create(name="mission-closed", kind="shell", cwd=registry.env.home, command=["/bin/sh"])
    registry.terminate(row)
    row = registry.archive(row)
    assert registry.rows() == []
    restarted = registry.restart_frontend(row)
    assert restarted["archived_at"] is None
    assert restarted["status"] == "running"
    assert registry.rows()[0]["id"] == row["id"]


def test_rename_rejects_archived_name_collision_before_touching_rmux(controlled_registry):
    registry, runtime = controlled_registry
    first = registry.create(name="mission-first", kind="shell", cwd=registry.env.home, command=["/bin/sh"])
    second = registry.create(name="mission-second", kind="shell", cwd=registry.env.home, command=["/bin/sh"])
    registry.terminate(second)
    registry.archive(second)
    before = list(runtime.calls)
    with pytest.raises(ValueError, match="registered"):
        registry.rename(first, "mission-second")
    assert runtime.calls == before
    assert "mission-first" in runtime.live


def test_registry_reads_and_reconcile_respect_selected_logical_environment(controlled_registry):
    registry, runtime = controlled_registry
    selected = registry.create(name="mission-selected", kind="shell", cwd=registry.env.home, command=["/bin/sh"])
    other = agk.RuntimeRegistry(agk.Environment("private", registry.env.home, registry.env.home), runtime)
    try:
        foreign = other.create(name="private-unrelated", kind="shell", cwd=other.env.home, command=["/bin/sh"])
        assert [row["id"] for row in registry.rows()] == [selected["id"]]
        assert registry.get(foreign["id"]) is None
        assert registry.get(foreign["name"]) is None
        runtime.live.discard(foreign["rmux_session"])
        registry.reconcile()
        assert other.get(foreign["id"])["status"] == "running"
        with pytest.raises(ValueError, match="registered"):
            registry.create(name=foreign["name"], kind="shell", cwd=registry.env.home, command=["/bin/sh"])
    finally:
        other.db.close()


@pytest.mark.parametrize("action", ["rename", "terminate", "purge", "restart_frontend", "fork", "archive", "update"])
def test_foreign_registry_row_cannot_trigger_runtime_mutation(controlled_registry, action):
    registry, runtime = controlled_registry
    other = agk.RuntimeRegistry(agk.Environment("private", registry.env.home, registry.env.home), runtime)
    try:
        foreign = other.create(name="private-foreign", kind="shell", cwd=other.env.home, command=["/bin/cat"])
        before = list(runtime.calls)
        args = (foreign, "mission-other") if action in {"rename", "fork"} else (foreign,)
        with pytest.raises(ValueError, match="environment"):
            getattr(registry, action)(*args)
        assert runtime.calls == before
        assert other.get(foreign["id"])["status"] == "running"
    finally:
        other.db.close()


def test_rmux_stable_pane_input_is_literal_not_shell(monkeypatch):
    calls = []
    def fake_run(*args, **kwargs):
        calls.append(args)
        return completed("%73\n")
    monkeypatch.setattr(agk, "run", fake_run)
    agk.RmuxRuntime().send_input("mission-synthetic", "$(never-run); --literal")
    assert calls == [
        ("rmux", "list-panes", "-t", "mission-synthetic", "-F", "#{pane_id}"),
        ("rmux", "send-keys", "-t", "%73", "-l", "$(never-run); --literal"),
        ("rmux", "send-keys", "-t", "%73", "Enter"),
    ]


@pytest.mark.parametrize("text", ["[broken, config]", "environment: [\nsecret-value"])
def test_invalid_environment_config_is_rejected_without_source_disclosure(tmp_path, monkeypatch, text):
    config = tmp_path / "environment.yaml"
    config.write_text(text, encoding="utf-8")
    monkeypatch.setattr(agk.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="audit", pw_dir=str(tmp_path)))
    monkeypatch.setenv("USER", "audit")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(config))
    with pytest.raises(SystemExit, match="Invalid AGK environment config") as error:
        agk.Environment.current()
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("document", ["[broken]", "mcp_servers:\n  1: {}\n  github: {}\n", "mcp_servers:\n  github: [broken]\n"])
def test_malformed_mcp_config_is_reported_as_error_without_crashing(tmp_path, monkeypatch, document):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "config.yaml").write_text(document, encoding="utf-8")
    monkeypatch.setattr(agk.shutil, "which", lambda name: None)
    env = agk.Environment("mission", tmp_path, tmp_path)
    assert agk.mcp_inventory(env)[0]["status"] == "error"
    with pytest.raises(RuntimeError, match="MCP config|mcp_servers"):
        agk.mcp_inventory(env, strict=True)


@pytest.mark.parametrize("count", ["invalid", -1, 1.5, True, float("inf"), None])
def test_invalid_composio_cache_entries_do_not_crash_or_claim_connections(tmp_path, count):
    path = tmp_path / "cache.json"
    path.write_text(agk.json.dumps({"schema_version": 1, "toolkits": [
        {"name": "bad", "connections": count, "status": "connected"},
        {"name": "good", "connections": 1, "status": "connected"},
    ]}), encoding="utf-8")
    assert agk.composio_toolkits(path) == [{"name": "good", "connections": 1, "status": "connected"}]


@pytest.mark.parametrize("kind", ["agent", "workflow", "monitor"])
def test_cli_new_rejects_orchestrator_only_types_before_runtime_initialization(monkeypatch, kind):
    monkeypatch.setattr(sys, "argv", ["agk", "new", kind, "mission-test"])
    monkeypatch.setattr(agk.Environment, "current", lambda: pytest.fail("must reject before runtime initialization"))
    with pytest.raises(SystemExit) as error:
        agk.main()
    assert error.value.code == 2


def test_create_requires_existing_directory_before_native_mutation(controlled_registry):
    registry, runtime = controlled_registry
    before = list(runtime.calls)
    with pytest.raises(ValueError, match="directory"):
        registry.create(name="mission-missing", kind="shell", cwd=registry.env.home / "missing", command=["/bin/cat"])
    assert runtime.calls == before
