"""First-class Agentik agent definitions and durable AGK/RMUX launches."""

from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import yaml

from tools.registry import tool_error, tool_result
from .workstation import agent_environment, agk_executable


_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
AGENT_TOOL_SCHEMA = {
    "name": "agentik_agent",
    "description": (
        "List, start, inspect, message, or read a specialized Agentik agent. "
        "Every started agent receives a persistent Hermes session inside its own AGK/RMUX runtime."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "start", "status", "message", "logs"]},
            "agent": {"type": "string", "description": "Canonical agent id."},
            "instruction": {"type": "string", "description": "Objective or follow-up instruction."},
        },
        "required": ["action"],
    },
}


def _catalog_root() -> Path:
    override = os.environ.get("AGK_AGENT_CATALOG")
    return Path(override) if override else Path(__file__).resolve().parents[2] / "agents"


def _definitions() -> list[dict]:
    definitions: list[dict] = []
    root = _catalog_root()
    if not root.is_dir():
        return definitions
    for manifest in sorted(root.glob("*/agent.yaml")):
        try:
            raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        agent_id = str(raw.get("id") or "")
        prompt = manifest.parent / str(raw.get("prompt") or "prompt.md")
        if _ID.fullmatch(agent_id) and prompt.is_file():
            raw["path"] = str(manifest.parent)
            raw["prompt_path"] = str(prompt)
            definitions.append(raw)
    return definitions


def _definition(agent_id: str) -> dict | None:
    return next((item for item in _definitions() if item["id"] == agent_id), None)


def agent_router_prompt(_session_info: dict | None = None) -> str:
    available = ", ".join(item["id"] for item in _definitions()) or "none"
    return (
        "Agentik specialized-agent routing:\n"
        f"Installed agent ids: {available}.\n"
        "When the user explicitly asks to start, call, use, or continue an installed specialized agent, "
        "use the agentik_agent tool. Start creates or resumes its durable Hermes + AGK/RMUX runtime; "
        "message sends a follow-up; logs reads its bounded output. Never pretend to have launched an agent, "
        "never create a second ad-hoc session system, and never cross the current Linux environment boundary."
    )


def _environment() -> tuple[str, str]:
    selected = os.environ.get("AGENTIK_ENVIRONMENT") or os.environ.get("USER") or pwd.getpwuid(os.geteuid()).pw_name
    return agent_environment(selected, Path.home())


def _runtime_row(name: str) -> dict | None:
    path = Path.home() / ".agentik/runtime.db"
    if not path.is_file():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("SELECT * FROM runtime_sessions WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def _run(argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)


def _pane(session: str) -> str:
    result = _run(["rmux", "list-panes", "-t", session, "-F", "#{pane_id}"])
    if result.returncode:
        return ""
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")


def _send(session: str, instruction: str) -> None:
    pane = _pane(session)
    if not pane:
        raise RuntimeError("agent runtime has no live RMUX pane")
    literal = _run(["rmux", "send-keys", "-t", pane, "-l", instruction])
    enter = _run(["rmux", "send-keys", "-t", pane, "Enter"])
    if literal.returncode or enter.returncode:
        raise RuntimeError("could not deliver instruction to agent runtime")


def _prepare_workspace(definition: dict) -> Path:
    target = Path.home() / ".agentik/agents" / definition["id"] / "workspace"
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A copy freezes the exact identity used by this installed release and
    # prevents a moving /opt/current symlink from mutating a running agent.
    shutil.copyfile(definition["prompt_path"], target / "AGENTS.md")
    (target / ".agentik-agent.json").write_text(
        json.dumps({"id": definition["id"], "version": definition["version"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def handle_agent(args: dict, **_kwargs) -> str:
    action = str(args.get("action") or "").lower().strip()
    agent_id = str(args.get("agent") or "").lower().strip()
    instruction = str(args.get("instruction") or "").strip()
    try:
        if action == "list":
            return tool_result({"success": True, "agents": [
                {key: item.get(key) for key in ("id", "name", "version", "description", "scope")}
                for item in _definitions()
            ]})
        definition = _definition(agent_id)
        if not definition:
            return tool_error(f"unknown Agentik agent: {agent_id}")
        environment, policy_scope = _environment()
        scope = definition.get("scope")
        if not isinstance(scope, list) or any(not isinstance(item, str) for item in scope):
            return tool_error(f"agent {agent_id} has an invalid scope")
        if not {environment, policy_scope}.intersection(scope):
            return tool_error(f"agent {agent_id} is not allowed in {environment}")
        session = f"{environment}-{agent_id}"
        row = _runtime_row(session)
        if action == "start":
            if not row:
                workspace = _prepare_workspace(definition)
                result = _run([agk_executable(), "new", "hermes", session, "--cwd", str(workspace)])
                if result.returncode:
                    return tool_error((result.stderr or result.stdout or "agent launch failed")[:2000])
            if instruction:
                _send(session, instruction)
            return tool_result({"success": True, "agent": agent_id, "session": session, "created": row is None})
        if not row:
            return tool_error(f"agent {agent_id} has not been started")
        if action == "status":
            return tool_result({"success": True, "agent": agent_id, "runtime": row})
        if action == "message":
            if not instruction or len(instruction) > 12000:
                return tool_error("instruction must contain 1-12000 characters")
            _send(session, instruction)
            return tool_result({"success": True, "agent": agent_id, "session": session})
        if action == "logs":
            result = _run(["rmux", "capture-pane", "-p", "-t", session, "-S", "-500"])
            if result.returncode:
                return tool_error("could not capture agent output")
            return tool_result({"success": True, "agent": agent_id, "output": result.stdout[-40000:]})
        return tool_error("unknown agent action")
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        return tool_error(f"Agentik agent operation failed safely: {exc}")


class AgentCommandService:
    """Shared slash-command surface for CLI, Discord, Telegram and Web."""

    def dispatch(self, raw_args: str) -> str:
        import shlex

        try:
            argv = shlex.split(raw_args)
        except ValueError as exc:
            return f"Invalid arguments: {exc}"
        action = argv[0].lower() if argv else "list"
        if action == "list":
            data = json.loads(handle_agent({"action": "list"}))
            agents = data.get("agents") or []
            return "AGENTS\n" + ("\n".join(
                f"• {item['id']} · {item.get('description') or item.get('name')}" for item in agents
            ) if agents else "No specialized agents installed.")
        if action in {"start", "status", "logs"} and len(argv) >= 2:
            payload = {"action": action, "agent": argv[1]}
            if action == "start" and len(argv) > 2:
                payload["instruction"] = " ".join(argv[2:])
            return handle_agent(payload)
        if action in {"message", "send"} and len(argv) >= 3:
            return handle_agent({"action": "message", "agent": argv[1], "instruction": " ".join(argv[2:])})
        return "Usage: /agent list | start <id> [objective] | status <id> | message <id> <text> | logs <id>"
