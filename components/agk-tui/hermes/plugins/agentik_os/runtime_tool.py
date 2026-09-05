"""Hermes tool adapter for durable, per-user AGK/RMUX runtimes."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

from tools.registry import tool_error, tool_result
from .workstation import agk_executable, permitted_cwd


_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_TYPES = {"hermes", "claude", "codex"}

RUNTIME_TOOL_SCHEMA = {
    "name": "agentik_runtime",
    "description": "Manage persistent AGK/RMUX agent runtimes inside the current Linux environment.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "snapshot", "spawn", "send"]},
            "session": {"type": "string", "description": "Managed AGK runtime name or ID."},
            "agent_type": {"type": "string", "enum": sorted(_TYPES)},
            "cwd": {"type": "string", "description": "Absolute project path inside the current Linux home."},
            "instruction": {"type": "string", "description": "Instruction sent literally to the managed pane."},
        },
        "required": ["action"],
    },
}


def runtime_available() -> bool:
    return shutil.which("rmux") is not None and shutil.which("agk") is not None


def _bounded_run(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)


def _home() -> Path:
    return Path.home().resolve()


def _registry_rows() -> list[dict]:
    path = _home() / ".agentik/runtime.db"
    if not path.is_file():
        return []
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in db.execute(
            "SELECT id,name,type,environment,client,project,mission,rmux_session,cwd,status,last_activity "
            "FROM runtime_sessions WHERE archived_at IS NULL ORDER BY last_activity DESC"
        )]
    finally:
        db.close()


def _managed(target: str) -> dict | None:
    return next((row for row in _registry_rows() if target in {row["id"], row["name"]}), None)


def _pane(session: str) -> str:
    result = _bounded_run(["rmux", "list-panes", "-t", session, "-F", "#{pane_id}"])
    pane = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
    if result.returncode or not pane:
        raise RuntimeError("managed RMUX runtime has no live pane")
    return pane


def handle_runtime(args: dict, **_kwargs) -> str:
    action = str(args.get("action") or "").strip().lower()
    try:
        if action == "list":
            return tool_result({"success": True, "runtimes": _registry_rows()})
        if action == "spawn":
            kind = str(args.get("agent_type") or "").strip().lower()
            name = str(args.get("session") or "").strip().lower()
            if kind not in _TYPES or not _NAME.fullmatch(name):
                return tool_error("spawn requires agent_type hermes|claude|codex and a canonical session name")
            cwd = Path(str(args.get("cwd") or _home())).expanduser().resolve()
            home = _home()
            if not permitted_cwd(cwd, home):
                return tool_error("cwd escapes the current Linux environment")
            result = _bounded_run([agk_executable(), "new", kind, name, "--cwd", str(cwd)], timeout=30)
            if result.returncode:
                return tool_error((result.stderr or result.stdout or "AGK spawn failed").strip()[:2000])
            return tool_result({"success": True, "action": "spawn", "session": name, "agent_type": kind})
        target = str(args.get("session") or "").strip()
        row = _managed(target)
        if not row:
            return tool_error("runtime is not managed by the current Agentik environment")
        if action == "snapshot":
            result = _bounded_run(["rmux", "capture-pane", "-p", "-t", row["rmux_session"], "-S", "-500"])
            if result.returncode:
                return tool_error("RMUX snapshot failed")
            return tool_result({"success": True, "session": row["name"], "output": result.stdout[-40000:]})
        if action == "send":
            instruction = str(args.get("instruction") or "")
            if not instruction.strip() or len(instruction) > 12000:
                return tool_error("instruction must contain 1-12000 characters")
            pane = _pane(row["rmux_session"])
            first = _bounded_run(["rmux", "send-keys", "-t", pane, "-l", instruction])
            second = _bounded_run(["rmux", "send-keys", "-t", pane, "Enter"])
            if first.returncode or second.returncode:
                return tool_error("RMUX send failed")
            return tool_result({"success": True, "action": "send", "session": row["name"]})
        return tool_error("unknown runtime action")
    except (OSError, sqlite3.Error, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
        return tool_error(f"Agentik runtime operation failed safely: {exc}")
