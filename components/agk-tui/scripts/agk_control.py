#!/usr/bin/env python3
"""AGK Control Shell: persistent Agentik runtime control backed by RMUX."""

from __future__ import annotations

import argparse
import curses
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
import pwd


CANONICAL_USERS = {
    "operator": ("operator", Path("/home/operator"), Path("/home/operator/src")),
    "agentik": ("agentik", Path("/home/agentik"), Path("/home/agentik/workspace/projects")),
    "mission": ("mission", Path("/home/mission"), Path("/home/mission/workspace/clients")),
    "private": ("private", Path("/home/private"), Path("/home/private/workspace/projects")),
}
TYPES = {"hermes", "claude", "codex", "openrouter", "opencode", "shell", "agent", "workflow", "monitor"}
LAUNCHABLE_TYPES = TYPES - {"agent", "workflow", "monitor"}
STATES = {"running", "working", "idle", "waiting", "attention", "failed", "complete", "interrupted", "archived"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
VIEWS = ("sessions", "projects", "agents", "os", "mcp", "skills", "rules", "settings")
TAB_DOUBLE_MS = 420
ACTIVE_STATES = {"running", "working", "waiting", "attention"}
STATUS_GLYPHS = {
    "running": "●", "working": "◉", "idle": "○", "waiting": "◌",
    "attention": "!", "failed": "×", "complete": "✓",
    "interrupted": "!", "archived": "·",
}


def layout_mode(width: int, height: int) -> str:
    if width < 72 or height < 18:
        return "compact"
    if width < 120 or height < 28:
        return "standard"
    return "wide"


def pane_widths(width: int, mode: str, fullscreen: bool = False) -> tuple[int, int]:
    if fullscreen:
        return 0, max(0, width)
    if mode != "wide":
        return max(0, width), 0
    left = max(38, min(54, width * 2 // 5))
    return left, max(0, width - left - 1)


def cycle_view(view: str, reverse: bool = False) -> str:
    index = VIEWS.index(view) if view in VIEWS else 0
    return VIEWS[(index + (-1 if reverse else 1)) % len(VIEWS)]


def rules_inventory(home: Path) -> list[dict[str, object]]:
    configured = os.environ.get("AGK_RULES_CONFIG")
    candidates = [
        Path(configured).expanduser() if configured else None,
        home / ".agentik/rules.yaml",
        Path("/etc/agk-terminal/rules.yaml"),
        Path(os.environ.get("AGK_TERMINAL_ROOT", "/usr/local/lib/agk-terminal")) / "config/rules.yaml",
    ]
    path = next((candidate for candidate in candidates if candidate and candidate.is_file()), None)
    if path is None:
        return []
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [rule for rule in document.get("rules", []) if isinstance(rule, dict)]


def format_age(timestamp: float, now: float | None = None) -> str:
    seconds = max(0, int((now or time.time()) - timestamp))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def session_sections(rows: list[sqlite3.Row]) -> list[tuple[str, list[sqlite3.Row]]]:
    active = [row for row in rows if row["status"] in ACTIVE_STATES]
    attention = [row for row in rows if row["status"] in {"failed", "interrupted"}]
    recent = [row for row in rows if row not in active and row not in attention]
    return [(name, values) for name, values in (
        ("ATTENTION", attention), ("ACTIVE", active), ("RECENT", recent)
    ) if values]


def trust_claude_workspace(home: Path, cwd: Path) -> None:
    """Persist trust for an AGK-managed Claude workspace owned by this profile."""
    config = home / ".claude.json"
    if config.is_symlink():
        raise RuntimeError(f"refusing symlinked Claude configuration: {config}")
    try:
        document = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    except (OSError, ValueError) as error:
        raise RuntimeError(f"cannot load Claude workspace trust: {error}") from error
    if not isinstance(document, dict):
        raise RuntimeError("Claude configuration root must be an object")
    projects = document.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise RuntimeError("Claude projects configuration must be an object")
    workspace = projects.setdefault(str(cwd.resolve()), {})
    if not isinstance(workspace, dict):
        raise RuntimeError("Claude workspace configuration must be an object")
    if workspace.get("hasTrustDialogAccepted") is True:
        return
    workspace["hasTrustDialogAccepted"] = True
    temporary = config.with_name(f".{config.name}.agk-{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, config)
    finally:
        temporary.unlink(missing_ok=True)


def session_detail_lines(row: sqlite3.Row) -> list[str]:
    return [
        f"Type          {str(row['type']).upper()}",
        f"Status        {str(row['status']).upper()}",
        f"Environment   {str(row['environment']).upper()}",
        f"Client        {row['client'] or '—'}",
        f"Project       {row['project'] or '—'}",
        f"Mission       {row['mission'] or '—'}",
        "",
        f"Hermes        {row['hermes_session'] or '—'}",
        f"Native        {row['native_session'] or '—'}",
        f"RMUX          {row['rmux_session']}",
        f"Runtime ID    {row['id']}",
        "",
        f"CWD           {row['cwd']}",
        f"Age           {format_age(float(row['created_at']))}",
        f"Last activity {format_age(float(row['last_activity']))}",
        f"Parent        {row['parent_session_id'] or '—'}",
    ]


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


@dataclass(frozen=True)
class Environment:
    name: str
    home: Path
    projects: Path

    @classmethod
    def current(cls) -> "Environment":
        # Station's native TUI and Python session controller share the same
        # operator namespace. Resolve the real identity, not caller USER/HOME.
        account = pwd.getpwuid(os.geteuid())
        if account.pw_name == "agk-station":
            home = Path(account.pw_dir)
            return cls("agk-station", home, home / "workspace/projects")
        user = os.environ.get("USER") or run("id", "-un").stdout.strip()
        if user in CANONICAL_USERS:
            return cls(*CANONICAL_USERS[user])
        home = Path.home()
        config_path = Path(os.environ.get(
            "AGK_ENV_CONFIG", home / ".config/agk/environment.yaml"
        ))
        config: dict[str, object] = {}
        try:
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config = {} if document is None else document
            if not isinstance(config, dict):
                raise ValueError("configuration must be an object")
        except FileNotFoundError:
            pass
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise SystemExit(f"Invalid AGK environment config: {config_path}") from None
        name = str(os.environ.get("AGK_ENVIRONMENT") or config.get("environment") or "agentik")
        if name not in {"operator", "agentik", "mission", "private"}:
            raise SystemExit(f"Unsupported AGK environment: {name}")
        default_projects = home / "workspace" / ("clients" if name == "mission" else "projects")
        projects = Path(str(config.get("projects_root") or default_projects)).expanduser()
        return cls(name, home, projects)


def os_registry_path() -> Path:
    """Resolve the system or user registry without fabricating OS packages."""
    override = os.environ.get("AGK_OS_REGISTRY")
    if override:
        return Path(override).expanduser()
    system = Path("/opt/agentik/os-registry")
    if system.is_dir():
        return system
    return Path.home() / ".local/share/agk/os-registry"


def agent_catalog_path(home: Path) -> Path:
    """Resolve the catalog used by both the native TUI and specialist starts."""
    override = os.environ.get("AGK_AGENT_CATALOG")
    if override:
        return Path(override).expanduser()
    install_root = Path(os.environ.get(
        "AGK_TERMINAL_ROOT", Path(__file__).resolve().parents[1]
    ))
    candidates = [
        home / ".hermes" / "agents",
        home / ".local" / "share" / "agk" / "agents",
        install_root / "agents",
        install_root / "hermes" / "agents",
    ]
    return next(
        (candidate for candidate in candidates if candidate.is_dir()),
        candidates[0],
    )


def specialist_definition(env: Environment, agent_id: str) -> dict[str, object]:
    if not NAME_RE.fullmatch(agent_id):
        raise ValueError("specialist id must use the canonical name grammar")
    root = agent_catalog_path(env.home).resolve()
    manifest = (root / agent_id / "agent.yaml").resolve()
    if root not in manifest.parents or not manifest.is_file():
        raise ValueError(f"unknown specialist agent: {agent_id}")
    try:
        document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise RuntimeError(f"specialist manifest is unreadable: {agent_id}") from error
    if not isinstance(document, dict) or document.get("id") != agent_id:
        raise RuntimeError(f"specialist manifest identity mismatch: {agent_id}")
    scope = document.get("scope") or []
    if not isinstance(scope, list) or any(not isinstance(item, str) for item in scope):
        raise RuntimeError(f"specialist scope is invalid: {agent_id}")
    if env.name != "operator" and env.name not in scope:
        raise PermissionError(f"specialist {agent_id} is not allowed in {env.name}")
    prompt_value = str(document.get("prompt") or "prompt.md")
    prompt = (manifest.parent / prompt_value).resolve()
    if manifest.parent not in prompt.parents or not prompt.is_file():
        raise RuntimeError(f"specialist prompt is missing: {agent_id}")
    document["manifest_path"] = manifest
    document["prompt_path"] = prompt
    return document


def prepare_specialist_workspace(env: Environment, definition: dict[str, object]) -> Path:
    agent_id = str(definition["id"])
    workspace = env.home / ".agentik" / "agents" / agent_id / "workspace"
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copyfile(Path(definition["prompt_path"]), workspace / "AGENTS.md")
    metadata = {
        "id": agent_id,
        "version": str(definition.get("version") or ""),
        "profile": definition.get("profile"),
        "os": definition.get("os") or [],
    }
    (workspace / ".agentik-agent.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return workspace


def specialist_command(
    env: Environment, definition: dict[str, object], workspace: Path
) -> list[str]:
    profile = str(definition.get("profile") or "").strip()
    launcher_value = str(definition.get("launcher") or "").strip()
    if launcher_value:
        launcher = Path(launcher_value).expanduser().resolve()
        home = env.home.resolve()
        if home not in launcher.parents or not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise RuntimeError(
                "specialist launcher must be executable inside the current profile home"
            )
        return [str(launcher), "--in", str(workspace)]
    hermes = shutil.which("hermes") or "hermes"
    if profile:
        if not NAME_RE.fullmatch(profile):
            raise RuntimeError("specialist Hermes profile id is invalid")
        profile_home = env.home / ".hermes" / "profiles" / profile
        if not profile_home.is_dir():
            raise RuntimeError(f"specialist Hermes profile is not installed: {profile}")
        return [hermes, "-p", profile, "--in", str(workspace)]
    return [hermes, "--in", str(workspace)]


class RmuxRuntime:
    """Typed Agentik adapter over the installed RMUX public CLI contract."""

    def has_session(self, name: str) -> bool:
        return run("rmux", "has-session", "-t", name, check=False).returncode == 0

    def create(self, name: str, kind: str, cwd: Path, environment: str,
               command: list[str]) -> None:
        run("rmux", "new-session", "-d", "-s", name, "-n", kind.upper(),
            "-c", str(cwd), "-e", "AGENTIK_RMUX=1",
            "-e", f"AGENTIK_ENVIRONMENT={environment}",
            "-e", f"PATH={os.environ.get('PATH', '')}", *command)

    def primary_pane(self, session: str) -> str:
        result = run("rmux", "list-panes", "-t", session, "-F", "#{pane_id}", check=False)
        pane = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
        if result.returncode or not pane:
            raise RuntimeError(f"RMUX session has no live pane: {session}")
        return pane

    def rename(self, session: str, name: str) -> None:
        run("rmux", "rename-session", "-t", session, name)

    def terminate(self, session: str) -> None:
        if not self.has_session(session):
            return
        last_error = ""
        for _ in range(2):
            result = run("rmux", "kill-session", "-t", session, check=False)
            last_error = (result.stderr or result.stdout).strip()
            if not self.has_session(session):
                return
        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(f"RMUX session is still alive after close: {session}{detail}")

    def respawn(self, session: str, cwd: str, command: list[str]) -> None:
        run("rmux", "respawn-pane", "-k", "-t", self.primary_pane(session), "-c", cwd, *command)

    def send_input(self, session: str, text: str, *, enter: bool = True) -> None:
        pane = self.primary_pane(session)
        run("rmux", "send-keys", "-t", pane, "-l", text)
        if enter:
            run("rmux", "send-keys", "-t", pane, "Enter")

    def wait_for(self, channel: str) -> None:
        if not NAME_RE.fullmatch(channel):
            raise ValueError("RMUX wait channel must use the canonical name grammar")
        run("rmux", "wait-for", channel)

    def panes(self) -> subprocess.CompletedProcess[str]:
        return run("rmux", "list-panes", "-a", "-F",
                   "#{session_name}|#{pane_dead}|#{pane_activity}|#{pane_current_command}", check=False)

    def snapshot(self, session: str, lines: int) -> list[str]:
        result = run("rmux", "capture-pane", "-p", "-t", session,
                     "-S", f"-{max(20, lines * 3)}", check=False)
        if result.returncode:
            return ["Runtime unavailable", "", "Press R to restart the frontend."]
        return result.stdout.rstrip().splitlines() or ["(no terminal output yet)"]


class RuntimeRegistry:
    def __init__(self, env: Environment, runtime: RmuxRuntime | None = None):
        self.env = env
        self.runtime = runtime or RmuxRuntime()
        root = env.home / ".agentik"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = root / "runtime.db"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runtime_sessions (
          id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
          environment TEXT NOT NULL, client TEXT, project TEXT, mission TEXT,
          hermes_session TEXT, rmux_session TEXT NOT NULL UNIQUE, cwd TEXT NOT NULL,
          status TEXT NOT NULL, parent_session_id TEXT,
          created_at REAL NOT NULL, last_activity REAL NOT NULL, archived_at REAL
        );
        CREATE TABLE IF NOT EXISTS ui_state (
          environment TEXT PRIMARY KEY, view TEXT NOT NULL DEFAULT 'sessions',
          selected TEXT, filter TEXT, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_events (
          id INTEGER PRIMARY KEY, runtime_id TEXT, event TEXT NOT NULL,
          payload TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
        );
        """)
        self._migrate()

    def _migrate(self) -> None:
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(runtime_sessions)")}
        additions = {
            "native_session": "TEXT",
            "hermes_profile": "TEXT",
            "command_json": "TEXT NOT NULL DEFAULT '[]'",
            "exit_code": "INTEGER",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                self.db.execute(f"ALTER TABLE runtime_sessions ADD COLUMN {name} {sql_type}")
        self.db.commit()

    def rows(self, include_archived: bool = False) -> list[sqlite3.Row]:
        where = " WHERE environment=?"
        if not include_archived:
            where += " AND archived_at IS NULL"
        return list(self.db.execute(
            "SELECT * FROM runtime_sessions" + where + " ORDER BY last_activity DESC",
            (self.env.name,),
        ))

    def get(self, target: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM runtime_sessions WHERE environment=? AND (id=? OR name=?)",
            (self.env.name, target, target),
        ).fetchone()

    def _registered_name(self, name: str) -> bool:
        # The RMUX namespace is shared by logical environments under one UID.
        # Reserve names globally while exposing only this environment's rows.
        return self.db.execute(
            "SELECT 1 FROM runtime_sessions WHERE name=? OR rmux_session=?",
            (name, name),
        ).fetchone() is not None

    def _require_owned_row(self, row: sqlite3.Row) -> None:
        if row["environment"] != self.env.name or self.get(row["id"]) is None:
            raise ValueError("runtime does not belong to the selected environment")

    def create(self, *, name: str, kind: str, cwd: Path, client: str | None = None,
               project: str | None = None, mission: str | None = None,
               parent: str | None = None, command: list[str] | None = None,
               native_session: str | None = None,
               hermes_profile: str | None = None) -> sqlite3.Row:
        if kind not in TYPES:
            raise ValueError(f"unsupported session type: {kind}")
        if not NAME_RE.fullmatch(name):
            raise ValueError("name must be 3-80 lowercase letters, digits or hyphens")
        if hermes_profile is not None and (
            kind != "hermes" or not NAME_RE.fullmatch(hermes_profile)
        ):
            raise ValueError("Hermes profile must be a safe lowercase profile id")
        cwd = cwd.expanduser().resolve()
        allowed = self.env.home.resolve()
        if cwd != allowed and allowed not in cwd.parents:
            raise ValueError(f"cwd escapes the {self.env.name} trust boundary")
        if not cwd.is_dir():
            raise ValueError("cwd must be an existing directory")
        if self._registered_name(name):
            raise ValueError(f"session already registered: {name}")
        if self.runtime.has_session(name):
            raise ValueError(f"unmanaged RMUX session already exists: {name}")
        if kind == "claude":
            trust_claude_workspace(self.env.home, cwd)
        launch = command or [os.environ.get("SHELL", "/bin/bash"), "-l"]
        self.runtime.create(name, kind, cwd, self.env.name, launch)
        now = time.time()
        runtime_id = "RT-" + uuid.uuid4().hex[:12].upper()
        self.db.execute("""
            INSERT INTO runtime_sessions(
              id,name,type,environment,client,project,mission,hermes_session,
              rmux_session,cwd,status,parent_session_id,created_at,last_activity,
              archived_at,native_session,hermes_profile,command_json,exit_code
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (runtime_id, name, kind, self.env.name, client, project, mission,
               native_session if kind == "hermes" else None, name, str(cwd),
               "running", parent, now, now, None, native_session, hermes_profile,
               json.dumps(launch), None))
        self.db.execute(
            "INSERT INTO runtime_events(runtime_id,event,created_at) VALUES(?,?,?)",
            (runtime_id, "runtime.created", now),
        )
        self.db.commit()
        return self.get(runtime_id)  # type: ignore[return-value]

    def update(self, row: sqlite3.Row, **values: object) -> sqlite3.Row:
        self._require_owned_row(row)
        allowed = {"name", "status", "rmux_session", "last_activity", "archived_at", "exit_code"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported runtime update: {sorted(unknown)}")
        values.setdefault("last_activity", time.time())
        fields = ",".join(f"{key}=?" for key in values)
        self.db.execute(f"UPDATE runtime_sessions SET {fields} WHERE id=?", (*values.values(), row["id"]))
        self.db.commit()
        return self.get(row["id"])  # type: ignore[return-value]

    def event(self, row: sqlite3.Row, event: str, payload: dict[str, object] | None = None) -> None:
        self._require_owned_row(row)
        self.db.execute(
            "INSERT INTO runtime_events(runtime_id,event,payload,created_at) VALUES(?,?,?,?)",
            (row["id"], event, json.dumps(payload or {}, sort_keys=True), time.time()),
        )
        self.db.commit()

    def load_ui(self) -> dict[str, object]:
        row = self.db.execute("SELECT * FROM ui_state WHERE environment=?", (self.env.name,)).fetchone()
        return dict(row) if row else {"view": "sessions", "selected": None, "filter": ""}

    def save_ui(self, view: str, selected: str | None, query: str) -> None:
        self.db.execute("""
          INSERT INTO ui_state(environment,view,selected,filter,updated_at)
          VALUES(?,?,?,?,?) ON CONFLICT(environment) DO UPDATE SET
          view=excluded.view,selected=excluded.selected,filter=excluded.filter,updated_at=excluded.updated_at
        """, (self.env.name, view, selected, query, time.time()))
        self.db.commit()

    def rename(self, row: sqlite3.Row, name: str) -> sqlite3.Row:
        self._require_owned_row(row)
        if not NAME_RE.fullmatch(name):
            raise ValueError("name must be 3-80 lowercase letters, digits or hyphens")
        if name == row["name"]:
            return self.get(row["id"])  # type: ignore[return-value]
        if self._registered_name(name):
            raise ValueError(f"session already registered: {name}")
        if self.runtime.has_session(name):
            raise ValueError(f"unmanaged RMUX session already exists: {name}")
        self.runtime.rename(row["rmux_session"], name)
        updated = self.update(row, name=name, rmux_session=name)
        self.event(updated, "runtime.renamed", {"previous": row["name"]})
        return updated

    def archive(self, row: sqlite3.Row) -> sqlite3.Row:
        updated = self.update(row, status="archived", archived_at=time.time())
        self.event(updated, "runtime.archived")
        return updated

    def terminate(self, row: sqlite3.Row) -> sqlite3.Row:
        self._require_owned_row(row)
        self.runtime.terminate(row["rmux_session"])
        updated = self.update(row, status="interrupted", exit_code=-15)
        self.event(updated, "runtime.terminated")
        return updated

    def purge(self, row: sqlite3.Row) -> str:
        """Stop a runtime and remove only its AGK registry metadata."""
        self._require_owned_row(row)
        self.runtime.terminate(row["rmux_session"])
        runtime_id = str(row["id"])
        name = str(row["name"])
        self.db.execute("DELETE FROM runtime_events WHERE runtime_id=?", (runtime_id,))
        self.db.execute("DELETE FROM runtime_sessions WHERE id=?", (runtime_id,))
        self.db.commit()
        return name

    def restart_frontend(self, row: sqlite3.Row) -> sqlite3.Row:
        self._require_owned_row(row)
        command = json.loads(row["command_json"] or "[]")
        if not command:
            command = default_command(
                row["type"], row["native_session"], row["hermes_profile"]
            )
        if self.runtime.has_session(row["rmux_session"]):
            self.runtime.respawn(row["rmux_session"], row["cwd"], command)
        else:
            self.runtime.create(row["rmux_session"], row["type"], Path(row["cwd"]), self.env.name, command)
        updated = self.update(row, status="running", exit_code=None, archived_at=None)
        self.event(updated, "runtime.frontend_restarted", {"native_session": row["native_session"]})
        return updated

    def ensure_specialist(
        self, *, name: str, cwd: Path, command: list[str],
        hermes_profile: str | None = None,
    ) -> tuple[sqlite3.Row, bool]:
        """Create or repair the one canonical runtime for a catalog agent."""
        row = self.get(name)
        if row is None:
            return (
                self.create(
                    name=name,
                    kind="hermes",
                    cwd=cwd,
                    command=command,
                    hermes_profile=hermes_profile,
                ),
                True,
            )
        try:
            current_command = json.loads(row["command_json"] or "[]")
        except (TypeError, ValueError):
            current_command = []
        current_cwd = str(Path(row["cwd"]).resolve())
        desired_cwd = str(cwd.resolve())
        if self.runtime.has_session(row["rmux_session"]):
            if current_command != command or current_cwd != desired_cwd:
                self.runtime.respawn(row["rmux_session"], desired_cwd, command)
        else:
            self.runtime.create(
                row["rmux_session"], "hermes", cwd, self.env.name, command
            )
        now = time.time()
        self.db.execute(
            """
            UPDATE runtime_sessions
               SET type='hermes', cwd=?, status='running', archived_at=NULL,
                   hermes_profile=?, command_json=?, exit_code=NULL, last_activity=?
             WHERE id=?
            """,
            (desired_cwd, hermes_profile, json.dumps(command), now, row["id"]),
        )
        self.db.commit()
        updated = self.get(row["id"])
        assert updated is not None
        self.event(
            updated,
            "runtime.specialist_opened",
            {"command_changed": current_command != command},
        )
        return updated, False

    def fork(self, row: sqlite3.Row, name: str) -> sqlite3.Row:
        self._require_owned_row(row)
        native = row["native_session"]
        if row["type"] == "codex" and native:
            command = ["codex", "fork", native]
        elif row["type"] == "claude" and native:
            command = ["claude", "--resume", native, "--fork-session"]
        elif row["type"] == "hermes" and native:
            # Hermes has resume but no documented fork flag. Start a new lineage
            # while retaining the parent link in Agentik metadata.
            command = ["hermes"]
            if row["hermes_profile"]:
                command.extend(["--profile", row["hermes_profile"]])
            command.extend(["--in", row["cwd"]])
            native = None
        else:
            command = default_command(row["type"], hermes_profile=row["hermes_profile"])
            native = None
        return self.create(name=name, kind=row["type"], cwd=Path(row["cwd"]),
                           client=row["client"], project=row["project"],
                           mission=row["mission"], parent=row["id"],
                           command=command, native_session=native,
                           hermes_profile=row["hermes_profile"])

    def reconcile(self) -> tuple[int, list[str]]:
        proc = self.runtime.panes()
        live_info: dict[str, list[tuple[bool, float, str]]] = {}
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                parts = line.split("|", 3)
                if len(parts) != 4:
                    continue
                try:
                    activity = float(parts[2] or 0)
                except ValueError:
                    activity = 0
                live_info.setdefault(parts[0], []).append((parts[1] == "1", activity, parts[3]))
        live = set(live_info)
        managed = {row[0] for row in self.db.execute(
            "SELECT rmux_session FROM runtime_sessions"
        )}
        changed = 0
        now = time.time()
        for row in self.rows():
            desired = row["status"]
            if row["rmux_session"] not in live and desired not in {"complete", "failed", "archived"}:
                desired = "interrupted"
            elif row["rmux_session"] in live and desired not in {"complete", "archived"}:
                panes = live_info[row["rmux_session"]]
                if panes and all(dead for dead, _, _ in panes):
                    desired = "failed"
                else:
                    last = max((activity for _, activity, _ in panes), default=0)
                    age = now - last if last else 999999
                    desired = "working" if age < 15 else "running" if age < 300 else "idle"
            if desired != row["status"]:
                self.db.execute("UPDATE runtime_sessions SET status=?,last_activity=? WHERE id=?", (desired, now, row["id"]))
                changed += 1
        self.db.commit()
        return changed, sorted(live - managed)


def default_command(
    kind: str,
    native_session: str | None = None,
    hermes_profile: str | None = None,
) -> list[str]:
    executable = lambda name: shutil.which(name) or name
    openrouter_model = os.environ.get("AGK_OPENROUTER_MODEL", "stealth/ox-alpha")
    claude = [executable("env"), "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1", executable("claude"), "--dangerously-skip-permissions"]
    if native_session:
        claude.extend(["--resume", native_session])
    hermes = [executable("hermes")]
    if hermes_profile:
        hermes.extend(["--profile", hermes_profile])
    if native_session:
        hermes.extend(["--resume", native_session])
    commands = {
        "hermes": hermes,
        "claude": claude,
        "codex": [executable("codex"), "resume", native_session] if native_session else [executable("codex")],
        "openrouter": [executable("hermes"), "--provider", "openrouter", "--model", openrouter_model],
        "opencode": [executable("opencode")],
        "shell": [os.environ.get("SHELL", "/bin/bash"), "-l"],
    }
    if kind not in commands:
        raise ValueError(f"{kind} requires an explicit orchestrator command")
    return commands[kind]


def start_specialist(
    env: Environment,
    registry: RuntimeRegistry,
    agent_id: str,
    session_name: str | None = None,
) -> tuple[sqlite3.Row, bool]:
    definition = specialist_definition(env, agent_id)
    workspace = prepare_specialist_workspace(env, definition)
    command = specialist_command(env, definition, workspace)
    canonical = f"{env.name}-{agent_id}"
    session = session_name or canonical
    if session != canonical and (
        not NAME_RE.fullmatch(session) or not session.startswith(f"{canonical}-")
    ):
        raise ValueError(f"specialist conversation must start with {canonical}-")
    return registry.ensure_specialist(
        name=session,
        cwd=workspace,
        command=command,
        hermes_profile=definition.get("profile"),
    )


def filtered(rows: list[sqlite3.Row], query: str) -> list[sqlite3.Row]:
    terms = query.lower().split()
    out = []
    for row in rows:
        values = dict(row)
        text = " ".join(str(v or "") for v in values.values()).lower()
        ok = True
        for term in terms:
            if ":" in term:
                key, value = term.split(":", 1)
                key = "environment" if key == "env" else key
                ok &= key in values and value in str(values[key] or "").lower()
            else:
                ok &= term in text
        if ok:
            out.append(row)
    return out


def mcp_inventory(env: Environment, *, strict: bool = False) -> list[dict[str, object]]:
    """Return redacted MCP identity/state from Hermes config."""
    path = env.home / ".hermes" / "config.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = {} if document is None else document
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError, yaml.YAMLError) as error:
        if strict:
            raise RuntimeError(f"Hermes MCP config is unreadable: {path}") from error
        return [{"name": "Hermes MCP config", "transport": "config",
                 "status": "error", "toolkits": []}]
    servers = config.get("mcp_servers", {}) if isinstance(config, dict) else None
    if (not isinstance(servers, dict)
            or any(not isinstance(name, str) or not isinstance(raw, dict)
                   for name, raw in servers.items())):
        if strict:
            raise RuntimeError(f"Hermes mcp_servers must be an object: {path}")
        return [{"name": "Hermes MCP config", "transport": "config",
                 "status": "error", "toolkits": []}]
    result: list[dict[str, object]] = []
    for name, raw in sorted(servers.items()):
        entry = raw if isinstance(raw, dict) else {}
        transport = "http" if entry.get("url") else "stdio" if entry.get("command") else "unknown"
        result.append({"name": str(name), "transport": transport,
                       "status": "disabled" if entry.get("enabled") is False else "configured",
                       "toolkits": []})
    if shutil.which("composio"):
        connected = composio_authenticated(env.home / ".composio/user_data.json")
        result.append({
            "name": "Composio",
            "transport": "CLI · link/tools list",
            "status": "connected" if connected else "setup-required",
            "toolkits": composio_toolkits(
                env.home / ".agentik/composio-connections.json"
            ) if connected else [],
        })
    result.sort(key=lambda item: item["name"].lower())
    return result


def refresh_mcp_inventory(env: Environment) -> list[dict[str, object]]:
    """Refresh profile-local SaaS state, then return the redacted MCP roster."""
    if shutil.which("composio"):
        inventory_script = Path(__file__).with_name("composio_inventory.py")
        if not inventory_script.is_file():
            raise RuntimeError(f"Composio inventory helper is missing: {inventory_script}")
        child_env = os.environ.copy()
        child_env.update({"HOME": str(env.home), "USER": env.name})
        try:
            result = subprocess.run(
                [sys.executable, str(inventory_script), "refresh", "--json"],
                text=True,
                capture_output=True,
                check=False,
                env=child_env,
                timeout=30,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Composio inventory refresh timed out after 30 seconds") from error
        if result.returncode:
            # composio_inventory.py owns error redaction; do not relay arbitrary
            # subprocess stderr through the control plane.
            raise RuntimeError(
                f"Composio inventory refresh failed with exit code {result.returncode}"
            )
    return mcp_inventory(env, strict=True)


def mcp_display_rows(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Flatten connected Composio toolkits so every entry is visible in AGK."""
    rows: list[dict[str, object]] = []
    for item in items:
        rows.append(item)
        for toolkit in item.get("toolkits", []):
            if not isinstance(toolkit, dict):
                continue
            name = str(toolkit.get("name") or "").strip()
            if not name:
                continue
            rows.append({
                "name": f"Composio / {name}",
                "transport": "connected toolkit",
                "status": str(toolkit.get("status") or "unknown"),
                "toolkits": [],
            })
    return rows


def composio_authenticated(path: Path) -> bool:
    """Validate Composio identity without exposing its API key."""
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("api_key")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(value, str) and bool(value.strip())


def composio_toolkits(path: Path) -> list[dict[str, object]]:
    """Read only the redacted AGK cache produced by composio_inventory.py."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        raw = document.get("toolkits") if document.get("schema_version") == 1 else []
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        connections = item.get("connections")
        if type(connections) is not int or connections < 0:
            continue
        result.append({
            "name": str(item["name"]),
            "status": str(item.get("status") or "unknown"),
            "connections": connections,
        })
    return sorted(result, key=lambda item: str(item["name"]).lower())


def skill_inventory(env: Environment) -> list[dict[str, str]]:
    """List skill identities and sources without reading skill contents."""
    roots = ((env.home / ".hermes/skills", "hermes"), (env.home / ".claude/skills", "claude"),
             (env.home / ".codex/skills", "codex"))
    found: dict[tuple[str, str], dict[str, str]] = {}
    for root, source in roots:
        if not root.is_dir():
            continue
        manifests = list(root.glob("*/DESCRIPTION.md")) + list(root.glob("*/SKILL.md"))
        # Codex system/plugin skills may be namespaced one level deeper.
        if source == "codex":
            manifests += list(root.glob("*/*/SKILL.md"))
        for manifest in manifests[:500]:
            found[(manifest.parent.name, source)] = {
                "name": manifest.parent.name, "source": source, "status": "installed",
            }
    return sorted(found.values(), key=lambda item: (item["name"], item["source"]))


def _prompt(stdscr: "curses._CursesWindow", label: str) -> str:
    height, width = stdscr.getmaxyx()
    curses.echo(); curses.curs_set(1)
    stdscr.move(height - 1, 0); stdscr.clrtoeol(); stdscr.addnstr(height - 1, 0, label, width - 1)
    value = stdscr.getstr(height - 1, len(label), max(1, width - len(label) - 1)).decode(errors="replace").strip()
    curses.noecho(); curses.curs_set(0)
    return value


def _notice(stdscr: "curses._CursesWindow", message: str) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.move(height - 1, 0); stdscr.clrtoeol(); stdscr.addnstr(height - 1, 0, message, width - 1)
    stdscr.getch()


def _create_from_tui(stdscr: "curses._CursesWindow", registry: RuntimeRegistry,
                     kind: str, cwd: Path | None = None, project: str | None = None) -> None:
    client = _prompt(stdscr, f"NEW {kind.upper()} · client (optional): ") if registry.env.name == "mission" else ""
    if project is None:
        project = _prompt(stdscr, "Project id/slug (optional): ") or None
        if project:
            match = next((item for item in canonical_projects(registry.env)
                          if project in {str(item["id"]), str(item["slug"])}), None)
            if match and match.get("path"):
                cwd = Path(str(match["path"]))
                project = str(match["id"])
    mission = _prompt(stdscr, "Mission id (optional): ") or None
    name = _prompt(stdscr, f"Session name ({registry.env.name}-scope-purpose): ")
    if not name:
        return
    try:
        registry.create(name=name, kind=kind, cwd=cwd or registry.env.home,
                        client=client or None, project=project, mission=mission,
                        command=default_command(kind))
    except Exception as exc:
        _notice(stdscr, f"Error: {exc}")


def _safe_add(stdscr: "curses._CursesWindow", y: int, x: int, value: object,
              limit: int, attr: int = 0) -> None:
    height, width = stdscr.getmaxyx()
    if 0 <= y < height and 0 <= x < width and limit > 0:
        try:
            stdscr.addnstr(y, x, str(value), min(limit, width - x - 1), attr)
        except curses.error:
            pass


def tui(stdscr: "curses._CursesWindow", registry: RuntimeRegistry) -> None:
    curses.curs_set(0)
    selected, query, view = 0, "", "sessions"
    views = {ord(str(index + 1)): view for index, view in enumerate(VIEWS)}
    while True:
        registry.reconcile()
        session_rows = filtered(registry.rows(), query)
        if view == "projects":
            rows: list[dict[str, object] | sqlite3.Row] = canonical_projects(registry.env)
        elif view == "agents":
            rows = [row for row in session_rows if row["type"] in {"hermes", "claude", "codex", "agent", "workflow"}]
        elif view == "sessions":
            rows = session_rows
        elif view in {"mcp", "skills"}:
            rows = mcp_inventory(registry.env) if view == "mcp" else skill_inventory(registry.env)
        elif view == "rules":
            rows = rules_inventory(registry.env.home)
        else:
            rows = []
        selected = max(0, min(selected, max(0, len(rows) - 1)))
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        header = f" AGK · {registry.env.name.upper()} · CONTROL MODE "
        stdscr.addnstr(0, 0, header + " " * max(1, width - len(header) - 10) + "● ONLINE", width - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, " 1 SESSIONS  2 PROJECTS  3 AGENTS  4 OS  5 MCP  6 SKILLS  7 RULES  8 SETTINGS ", width - 1)
        stdscr.addnstr(3, 0, view.upper() + (f"  / {query}" if query else ""), width - 1, curses.A_BOLD)
        if view in {"sessions", "agents"}:
            for idx, row in enumerate(rows[: max(0, height - 9)]):
                marker = "▶" if idx == selected else " "
                state = {"running": "●", "working": "◉", "idle": "○", "waiting": "◌", "failed": "×", "complete": "✓"}.get(str(row["status"]), "!")
                context = row["project"] or row["client"] or registry.env.name
                label = f"{marker} {state} {str(row['name']):<38} {str(row['type']).upper():<9} {str(context):<18} {str(row['status']).upper()}"
                stdscr.addnstr(5 + idx, 0, label, width - 1, curses.A_REVERSE if idx == selected else 0)
        elif view == "projects":
            for idx, row in enumerate(rows[: max(0, height - 9)]):
                linked = sum(1 for item in registry.rows() if item["project"] in {row["id"], row["slug"]})
                label = f"{'▶' if idx == selected else ' '} {'●' if row['status']=='active' else '○'} {str(row['name']):<42} {linked} sessions · {row['status']}"
                stdscr.addnstr(5 + idx, 0, label, width - 1, curses.A_REVERSE if idx == selected else 0)
        elif view == "os":
            stdscr.addnstr(5, 0, "No Operative Systems installed. Registry is ready; packages are never invented.", width - 1)
        elif view in {"mcp", "skills"}:
            visible = max(0, height - 9)
            for idx, item in enumerate(rows[:visible]):
                detail = item.get("transport") or item.get("source") or ""
                stdscr.addnstr(
                    5 + idx,
                    0,
                    f"● {item['name']:<32} {detail:<10} {item['status']}",
                    width - 1,
                )
            if not rows:
                stdscr.addnstr(
                    5,
                    0,
                    f"No {view.upper()} entries configured in this environment",
                    width - 1,
                )
        elif view == "rules":
            for idx, rule in enumerate(rows[: max(0, height - 9)]):
                stdscr.addnstr(5 + idx, 0, f"● {rule.get('title') or rule.get('id')} · ALL PROVIDERS", width - 1)
        footer = "↑↓/jk Navigate  Enter Open  n New  / Search  Ctrl-p Palette  R Restart  f Fork  A Archive  K Kill  q Quit"
        stdscr.addnstr(height - 2, 0, footer, width - 1)
        stdscr.refresh()
        key = stdscr.getch()
        if key == ord("q"):
            return
        if key == 27:
            view, query, selected = "sessions", "", 0
        elif key in views:
            view, selected = views[key], 0
        elif key in (curses.KEY_DOWN, ord("j")) and rows:
            selected = min(len(rows) - 1, selected + 1)
        elif key in (curses.KEY_UP, ord("k")) and rows:
            selected = max(0, selected - 1)
        elif key in (10, 13) and rows:
            row = rows[selected]
            if view in {"sessions", "agents"}:
                curses.endwin(); subprocess.run(["rmux", "attach-session", "-t", str(row["rmux_session"])]); stdscr.refresh()
            elif view == "projects":
                related = [item for item in registry.rows() if item["project"] in {row["id"], row["slug"]}]
                if related:
                    curses.endwin(); subprocess.run(["rmux", "attach-session", "-t", related[0]["rmux_session"]]); stdscr.refresh()
        elif key == ord("/"):
            query, selected = _prompt(stdscr, "Search/filter: "), 0
        elif key == 16:  # Ctrl-p command palette / quick switcher
            palette = _prompt(stdscr, "> ")
            if palette.startswith("open "):
                query, view, selected = palette[5:].strip(), "sessions", 0
            elif palette.startswith("new ") and palette[4:].strip() in {"hermes", "claude", "codex", "shell"}:
                _create_from_tui(stdscr, registry, palette[4:].strip())
            else:
                query, view, selected = palette, "sessions", 0
        elif key in (ord("h"), ord("c"), ord("x"), ord("t")) and view in {"sessions", "projects"}:
            kind = {ord("h"): "hermes", ord("c"): "claude", ord("x"): "codex", ord("t"): "shell"}[key]
            project = rows[selected] if view == "projects" and rows else None
            _create_from_tui(stdscr, registry, kind,
                             Path(str(project["path"])) if project and project["path"] else None,
                             str(project["id"]) if project else None)
        elif key == ord("n"):
            choice = _prompt(stdscr, "New [h]ermes [c]laude code[x] [t]erminal: ").lower()[:1]
            kind = {"h": "hermes", "c": "claude", "x": "codex", "t": "shell"}.get(choice)
            if kind: _create_from_tui(stdscr, registry, kind)
        elif view in {"sessions", "agents"} and rows and key == ord("i"):
            stdscr.erase(); stdscr.addnstr(0, 0, json.dumps(dict(rows[selected]), indent=2), max(1, height * width - 2)); _notice(stdscr, "Press any key")
        elif view in {"sessions", "agents"} and rows and key == ord("R"):
            registry.restart_frontend(rows[selected])
        elif view == "sessions" and rows and key == ord("f"):
            name = _prompt(stdscr, "Fork name: ")
            if name:
                try: registry.fork(rows[selected], name)
                except Exception as exc: _notice(stdscr, f"Error: {exc}")
        elif view in {"sessions", "agents"} and rows and key == ord("A"):
            registry.archive(rows[selected])
        elif view in {"sessions", "agents"} and rows and key == ord("K"):
            if _prompt(stdscr, f"Kill {rows[selected]['name']}? type YES: ") == "YES": registry.terminate(rows[selected])
        elif key == ord("?"):
            _notice(stdscr, "CONTROL MODE. Enter attaches; Ctrl-b d detaches. q exits UI only. Uppercase K kills after confirmation.")


def tui_v2(stdscr: "curses._CursesWindow", registry: RuntimeRegistry) -> None:
    """AGK V2 control surface."""
    curses.curs_set(0); curses.mousemask(curses.ALL_MOUSE_EVENTS); stdscr.keypad(True)
    # Event-driven enough for a local control surface: redraw/reconcile once per
    # second while still reacting immediately to keyboard and mouse input.
    stdscr.timeout(1000)
    saved = registry.load_ui()
    view, query = str(saved.get("view") or "sessions"), str(saved.get("filter") or "")
    selected, wanted = 0, saved.get("selected")
    focus, fullscreen, scroll, follow, last_tab = "list", False, 0, True, 0.0
    split_enabled, selected_ids = True, set()
    mcp_refresh_needed, mcp_error = True, ""
    hotkeys = {ord(str(index + 1)): view for index, view in enumerate(VIEWS)}
    while True:
        registry.reconcile(); sessions = filtered(registry.rows(), query)
        if view == "projects": rows: list[dict[str, object] | sqlite3.Row] = canonical_projects(registry.env)
        elif view == "agents": rows = [r for r in sessions if r["type"] in {"hermes", "claude", "codex", "agent", "workflow"}]
        elif view == "sessions": rows = sessions
        elif view == "mcp":
            if mcp_refresh_needed:
                try:
                    mcp_items = refresh_mcp_inventory(registry.env)
                    mcp_error = ""
                except RuntimeError as error:
                    mcp_items = mcp_inventory(registry.env)
                    mcp_error = str(error)
                mcp_refresh_needed = False
            else:
                mcp_items = mcp_inventory(registry.env)
            rows = mcp_display_rows(mcp_items)
        elif view == "skills": rows = skill_inventory(registry.env)
        elif view == "rules": rows = rules_inventory(registry.env.home)
        else: rows = []
        if wanted and rows:
            selected = next((i for i, r in enumerate(rows) if str(r.get("id") if isinstance(r, dict) else r["id"]) == wanted), selected); wanted = None
        selected = min(max(0, selected), max(0, len(rows) - 1)); current = rows[selected] if rows else None
        current_id = str(current.get("id") if isinstance(current, dict) else current["id"]) if current else None
        registry.save_ui(view, current_id, query)
        stdscr.erase(); height, width = stdscr.getmaxyx(); mode = layout_mode(width, height)
        left, right = pane_widths(width, mode, fullscreen and focus == "detail")
        if not split_enabled:
            left, right = width, 0
        if fullscreen and focus == "list": left, right = width, 0
        _safe_add(stdscr, 0, 0, f" AGK · {registry.env.name.upper()} · CONTROL", width - 1, curses.A_BOLD)
        _safe_add(stdscr, 0, max(30, width - 11), "● ONLINE", 10, curses.A_BOLD)
        nav = " 1 SESSIONS  2 PROJECTS  3 AGENTS  4 OS  5 MCP  6 SKILLS  7 RULES  8 SETTINGS"
        _safe_add(stdscr, 1, 0, nav, width - 1)
        crumb = registry.env.name.upper()
        if current is not None and not isinstance(current, dict): crumb += f" › {current['client'] or '—'} › {current['project'] or '—'} › {current['name']}"
        _safe_add(stdscr, 2, 0, crumb, width - 1, curses.A_DIM); _safe_add(stdscr, 4, 0, view.upper() + (f"  / {query}" if query else ""), max(1, left - 1), curses.A_BOLD)
        if view == "mcp" and mcp_error:
            _safe_add(stdscr, 3, 0, f"Refresh error: {mcp_error}", width - 1, curses.A_BOLD)
        list_limit, visible = (max(1, left - 2) if right else width - 1), max(1, height - 9)
        start = max(0, selected - visible + 1)
        if view in {"sessions", "agents"}:
            previous_section = None
            for screen_i, row in enumerate(rows[start:start + visible]):
                idx = start + screen_i; icon = STATUS_GLYPHS.get(str(row["status"]), "!")
                marker = "◆" if row["id"] in selected_ids else "▶" if idx == selected else " "
                context = row["project"] or row["client"] or registry.env.name
                section = "ACTIVE" if row["status"] in ACTIVE_STATES else "ATTENTION" if row["status"] in {"failed", "interrupted"} else "RECENT"
                prefix = f"{section} · " if section != previous_section else ""
                previous_section = section
                age = format_age(float(row["last_activity"]))
                label = f"{marker} {icon} {prefix}{row['name']} · {str(row['type']).upper()}" if mode == "compact" else f"{marker} {icon} {prefix}{str(row['name']):<28} {str(row['type']).upper():<8} {str(context):<12} {age:>5}"
                _safe_add(stdscr, 5 + screen_i, 0, label, list_limit, curses.A_REVERSE if idx == selected and focus == "list" else 0)
        elif view == "projects":
            for screen_i, row in enumerate(rows[:visible]):
                linked = sum(1 for item in registry.rows() if item["project"] in {row["id"], row["slug"]})
                _safe_add(stdscr, 5 + screen_i, 0, f"{'▶' if screen_i == selected else ' '} {row['name']} · {linked} sessions · {row['status']}", list_limit, curses.A_REVERSE if screen_i == selected and focus == "list" else 0)
        elif view in {"mcp", "skills"}:
            for screen_i, row in enumerate(rows[start:start + visible]):
                idx = start + screen_i
                detail = row.get("transport") or row.get("source") or ""
                _safe_add(stdscr, 5 + screen_i, 0,
                          f"{'▶' if idx == selected else ' '} ● {row['name']:<30} {detail:<10} {row['status']}",
                          list_limit, curses.A_REVERSE if idx == selected and focus == "list" else 0)
            if not rows:
                _safe_add(stdscr, 5, 0, f"No {view.upper()} capabilities configured", width - 1)
        elif view == "rules":
            for screen_i, row in enumerate(rows[start:start + visible]):
                idx = start + screen_i
                scope = "ALL PROVIDERS" if "*" in (row.get("providers") or ["*"]) else ", ".join(row.get("providers") or [])
                _safe_add(
                    stdscr, 5 + screen_i, 0,
                    f"{'▶' if idx == selected else ' '} {'●' if row.get('enabled', True) else '○'} {row.get('title') or row.get('id')} · {scope}",
                    list_limit, curses.A_REVERSE if idx == selected and focus == "list" else 0,
                )
        else:
            messages = {"os": "Zero Operative Systems installed · registry ready · no package is invented", "mcp": "MCP inventory is scoped to this Hermes environment", "skills": "Skills are capabilities; OS remain separate methodologies", "settings": f"Appearance · Providers · Sessions · Runtime · System ({run('rmux','-V').stdout.strip()}) · Help · About"}
            _safe_add(stdscr, 5, 0, messages.get(view, ""), width - 1)
        max_scroll = 0
        if right and current is not None and not isinstance(current, dict) and view in {"sessions", "agents"}:
            x = left + 1; _safe_add(stdscr, 4, x, f"{str(current['name']).upper()} · DETAILS + LIVE", right - 1, curses.A_BOLD)
            details = session_detail_lines(current)
            detail_height = min(8, max(4, visible // 3))
            for n, line in enumerate(details[:detail_height]):
                _safe_add(stdscr, 5 + n, x, line, right - 1, curses.A_DIM)
            output_y = 5 + detail_height
            output_visible = max(1, visible - detail_height)
            content = registry.runtime.snapshot(str(current["rmux_session"]), max(20, output_visible * 4)); max_scroll = max(0, len(content) - output_visible)
            if follow: scroll = max_scroll
            scroll = min(max(0, scroll), max_scroll)
            for n, line in enumerate(content[scroll:scroll + output_visible]): _safe_add(stdscr, output_y + n, x, line, right - 1)
            _safe_add(stdscr, height - 3, x, "LIVE ↓" if follow else f"↑ SCROLLBACK · {max_scroll-scroll} lines from live", right - 1, curses.A_BOLD)
        context = f"AGK CORE │ {registry.env.name.upper()}"
        if current is not None and not isinstance(current, dict):
            context += f" │ {current['client'] or '—'} │ {current['project'] or '—'} │ rmux:{current['rmux_session']}"
        _safe_add(stdscr, height - 3, 0, context, max(1, left - 1), curses.A_DIM)
        footer = "↑↓ Navigate  Enter Open  Tab Focus  Ctrl-r Refresh  n New  / Search  Ctrl-p Palette  v Split  q Quit"
        _safe_add(stdscr, height - 2, 0, footer if mode != "compact" else "↑↓ Enter  n New  / Search  ? Help  q Quit", width - 1); stdscr.refresh(); key = stdscr.getch()
        if key == -1:
            continue
        if key == ord("q"): return
        if key == 27: view, query, selected, focus, fullscreen = "sessions", "", 0, "list", False
        elif key in hotkeys:
            view, selected, focus, fullscreen = hotkeys[key], 0, "list", False
            if view == "mcp":
                mcp_refresh_needed = True
        elif key in (18, ord("r")):  # Ctrl-r / r refresh the active AGK view.
            if view == "mcp":
                mcp_refresh_needed = True
            registry.reconcile()
        elif key in (9, curses.KEY_BTAB):
            now = time.monotonic()
            if key == 9 and (now - last_tab) * 1000 < TAB_DOUBLE_MS: fullscreen, last_tab = not fullscreen, 0.0
            else: focus, last_tab = ("detail" if focus == "list" else "list"), now
        elif key in (curses.KEY_DOWN, ord("j")) and rows:
            if focus == "detail" and right: scroll, follow = min(max_scroll, scroll + 1), scroll + 1 >= max_scroll
            else: selected = min(len(rows) - 1, selected + 1)
        elif key in (curses.KEY_UP, ord("k")) and rows:
            if focus == "detail" and right: scroll, follow = max(0, scroll - 1), False
            else: selected = max(0, selected - 1)
        elif key == curses.KEY_PPAGE and right: scroll, follow = max(0, scroll - visible), False
        elif key == curses.KEY_NPAGE and right: scroll, follow = min(max_scroll, scroll + visible), scroll + visible >= max_scroll
        elif key == ord("g") and focus == "detail": scroll, follow = 0, False
        elif key == ord("G") and focus == "detail": scroll, follow = max_scroll, True
        elif key == curses.KEY_MOUSE:
            try:
                _, mouse_x, mouse_y, _, mouse_state = curses.getmouse()
                if mouse_state & curses.BUTTON4_PRESSED:
                    if right and mouse_x > left: focus, scroll, follow = "detail", max(0, scroll - 3), False
                    elif rows: focus, selected = "list", max(0, selected - 1)
                elif mouse_state & curses.BUTTON5_PRESSED:
                    if right and mouse_x > left: focus, scroll, follow = "detail", min(max_scroll, scroll + 3), scroll + 3 >= max_scroll
                    elif rows: focus, selected = "list", min(len(rows) - 1, selected + 1)
                elif mouse_state & curses.BUTTON1_CLICKED and 5 <= mouse_y < 5 + visible:
                    if right and mouse_x > left: focus = "detail"
                    elif rows:
                        focus = "list"; selected = min(len(rows) - 1, start + mouse_y - 5)
            except curses.error:
                pass
        elif key == ord("v") and view in {"sessions", "agents"}:
            split_enabled, fullscreen = not split_enabled, False
        elif key == ord(" ") and current is not None and not isinstance(current, dict) and view in {"sessions", "agents"}:
            if current["id"] in selected_ids:
                selected_ids.remove(current["id"])
            else:
                selected_ids.add(current["id"])
        elif key in (10, 13) and current is not None and view in {"sessions", "agents"}:
            curses.def_prog_mode(); curses.endwin()
            subprocess.run(["rmux", "attach-session", "-t", str(current["rmux_session"])])
            curses.reset_prog_mode(); stdscr.clear(); stdscr.refresh()
        elif key == ord("/"): query, selected = _prompt(stdscr, "Search/filter: "), 0
        elif key == 16:
            palette = _prompt(stdscr, "> ")
            if palette.startswith("open "): query, view, selected = palette[5:].strip(), "sessions", 0
            elif palette.startswith("new ") and palette[4:].strip() in {"hermes", "claude", "codex", "shell"}: _create_from_tui(stdscr, registry, palette[4:].strip())
            else: query, view, selected = palette, "sessions", 0
        elif key in (ord("h"), ord("c"), ord("x"), ord("t")) and view in {"sessions", "projects"}:
            kind = {ord("h"): "hermes", ord("c"): "claude", ord("x"): "codex", ord("t"): "shell"}[key]; project = current if view == "projects" and isinstance(current, dict) else None
            _create_from_tui(stdscr, registry, kind, Path(str(project["path"])) if project and project["path"] else None, str(project["id"]) if project else None)
        elif key == ord("n"):
            choice = _prompt(stdscr, "New [h]ermes [c]laude code[x] [t]erminal: ").lower()[:1]; kind = {"h": "hermes", "c": "claude", "x": "codex", "t": "shell"}.get(choice)
            if kind: _create_from_tui(stdscr, registry, kind)
        elif view in {"sessions", "agents"} and current is not None and key == ord("R"): registry.restart_frontend(current)
        elif view == "agents" and current is not None and key == ord("f"):
            curses.def_prog_mode(); curses.endwin()
            subprocess.run(["rmux", "attach-session", "-r", "-t", str(current["rmux_session"])])
            curses.reset_prog_mode(); stdscr.clear(); stdscr.refresh()
        elif view == "sessions" and current is not None and key == ord("f"):
            name = _prompt(stdscr, "Fork name: ")
            if name:
                try: registry.fork(current, name)
                except Exception as exc: _notice(stdscr, f"Error: {exc}")
        elif view in {"sessions", "agents"} and current is not None and key == ord("A"): registry.archive(current)
        elif view in {"sessions", "agents"} and current is not None and key == ord("K") and _prompt(stdscr, f"Kill {current['name']}? type YES: ") == "YES": registry.terminate(current)
        elif view in {"sessions", "agents"} and current is not None and key == ord("i"):
            lines = session_detail_lines(current)
            stdscr.erase()
            for n, line in enumerate(lines[:max(1, height - 3)]):
                _safe_add(stdscr, n, 0, line, width - 1)
            _notice(stdscr, "Session info · press any key")


def doctor(env: Environment, registry: RuntimeRegistry) -> int:
    checks = []
    for label, command in (("RMUX", ["rmux", "-V"]), ("RMUX health", ["rmux", "diagnose", "--human"]),
                           ("Hermes", ["hermes", "--help"]), ("Claude", ["claude", "--version"]),
                           ("Codex", ["codex", "--version"]), ("Tailscale", ["tailscale", "status"])):
        result = run(*command, check=False)
        checks.append((label, result.returncode == 0))
    _, unmanaged = registry.reconcile()
    checks += [("Runtime registry", True), ("OS Registry", os_registry_path().is_dir()),
               ("Isolated home", env.home.stat().st_mode & 0o077 == 0)]
    print(f"AGK-TUI DOCTOR · {env.name.upper()}")
    for label, ok in checks:
        print(f"{'✓' if ok else '✗'} {label}")
    print(f"{'!' if unmanaged else '✓'} Unmanaged RMUX sessions: {', '.join(unmanaged) if unmanaged else 'none'}")
    return 0 if all(ok for _, ok in checks) else 1


def canonical_projects(env: Environment) -> list[dict[str, object]]:
    db_path = env.home / ".agentik" / "control.db"
    if not db_path.exists():
        return []
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in db.execute(
            "SELECT id,slug,name,status,path,parent_id FROM objects "
            "WHERE environment=? AND kind='project' ORDER BY updated_at DESC",
            (env.name,),
        )]
    finally:
        db.close()


def require_runtime(registry: RuntimeRegistry, target: str) -> sqlite3.Row:
    row = registry.get(target)
    if row is None:
        raise SystemExit(f"Runtime session not found: {target}")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(prog="agk")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status"); sub.add_parser("doctor"); sub.add_parser("sessions")
    new = sub.add_parser("new")
    new.add_argument("type", choices=sorted(LAUNCHABLE_TYPES)); new.add_argument("name")
    new.add_argument("--cwd", type=Path); new.add_argument("--client"); new.add_argument("--project"); new.add_argument("--mission"); new.add_argument("--native-session"); new.add_argument("--profile")
    resume = sub.add_parser("resume"); resume.add_argument("target", nargs="?")
    open_p = sub.add_parser("open"); open_p.add_argument("target")
    agent = sub.add_parser("agent"); agent.add_argument("type", choices=("hermes", "claude", "codex")); agent.add_argument("name", nargs="?")
    specialist = sub.add_parser("specialist")
    specialist.add_argument("action", choices=("start",))
    specialist.add_argument("id")
    specialist.add_argument("--session")
    for action in ("info", "archive", "restart"):
        item = sub.add_parser(action); item.add_argument("target")
    for action in ("kill", "close"):
        destructive = sub.add_parser(action)
        destructive.add_argument("target")
        destructive.add_argument("--yes", action="store_true")
    purge = sub.add_parser("purge")
    purge.add_argument("target")
    purge.add_argument("--yes", action="store_true")
    rename = sub.add_parser("rename"); rename.add_argument("target"); rename.add_argument("name")
    fork = sub.add_parser("fork"); fork.add_argument("target"); fork.add_argument("name")
    sub.add_parser("reconcile")
    sub.add_parser("projects"); sub.add_parser("agents"); sub.add_parser("os"); sub.add_parser("mcp"); sub.add_parser("skills"); sub.add_parser("rules"); sub.add_parser("system")
    args = parser.parse_args()
    env = Environment.current(); registry = RuntimeRegistry(env); registry.reconcile()
    if args.command is None:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("agk Control Shell requires a TTY; use `agk status` for non-interactive use.", file=sys.stderr); return 2
        curses.wrapper(tui_v2, registry); return 0
    if args.command in {"status", "sessions"}:
        print(f"AGK-TUI · {env.name.upper()}\nRMUX {run('rmux','-V').stdout.strip()}")
        for row in registry.rows(): print(f"{row['status']:<12} {row['type']:<9} {row['name']}  {row['project'] or '—'}")
        return 0
    if args.command == "doctor": return doctor(env, registry)
    if args.command == "new":
        row = registry.create(name=args.name, kind=args.type, cwd=args.cwd or env.home,
                              client=args.client, project=args.project, mission=args.mission,
                              command=default_command(args.type, args.native_session, args.profile),
                              native_session=args.native_session,
                              hermes_profile=args.profile)
        print(f"Created {row['id']} · {row['name']} · {row['type'].upper()}"); return 0
    if args.command == "agent":
        name = args.name or f"{env.name}-{args.type}-{time.strftime('%Y%m%d-%H%M%S')}"
        row = registry.create(name=name, kind=args.type, cwd=env.projects if env.projects.exists() else env.home, command=default_command(args.type))
        print(f"Started {row['id']} · {row['name']}"); return 0
    if args.command == "specialist":
        try:
            row, created = start_specialist(env, registry, args.id, args.session)
        except (OSError, RuntimeError, ValueError, PermissionError) as error:
            print(f"Specialist start failed: {error}", file=sys.stderr)
            return 1
        verb = "Started" if created else "Opened"
        print(f"{verb} {args.id} · {row['name']}")
        return 0
    if args.command in {"resume", "open"}:
        target = getattr(args, "target", None)
        row = registry.get(target) if target else (registry.rows()[0] if registry.rows() else None)
        if not row: print("No resumable session.", file=sys.stderr); return 1
        os.execvp("rmux", ["rmux", "attach-session", "-t", row["rmux_session"]])
    if args.command == "info":
        print(json.dumps(dict(require_runtime(registry, args.target)), indent=2, sort_keys=True)); return 0
    if args.command == "archive":
        row = registry.archive(require_runtime(registry, args.target)); print(f"Archived {row['name']}"); return 0
    if args.command in {"kill", "close"}:
        confirmed = args.yes or (
            sys.stdin.isatty()
            and input(f"Close runtime {args.target}? History remains. [y/N] ").lower() == "y"
        )
        if not confirmed:
            print("Cancelled."); return 1
        row = registry.terminate(require_runtime(registry, args.target))
        if args.command == "close":
            row = registry.archive(row)
            print(f"Closed {row['name']}")
        else:
            print(f"Stopped {row['name']}")
        return 0
    if args.command == "purge":
        confirmed = args.yes or (
            sys.stdin.isatty()
            and input(f"Purge runtime {args.target} and AGK metadata? [y/N] ").lower() == "y"
        )
        if not confirmed:
            print("Cancelled."); return 1
        name = registry.purge(require_runtime(registry, args.target))
        print(f"Purged {name}")
        return 0
    if args.command == "restart":
        row = registry.restart_frontend(require_runtime(registry, args.target)); print(f"Restarted frontend {row['name']}"); return 0
    if args.command == "rename":
        row = registry.rename(require_runtime(registry, args.target), args.name); print(f"Renamed to {row['name']}"); return 0
    if args.command == "fork":
        row = registry.fork(require_runtime(registry, args.target), args.name); print(f"Forked {row['name']} from {row['parent_session_id']}"); return 0
    if args.command == "reconcile":
        changed, unmanaged = registry.reconcile(); print(f"Updated: {changed}\nUnmanaged: {', '.join(unmanaged) if unmanaged else 'none'}"); return 0
    if args.command == "projects":
        projects = canonical_projects(env)
        if projects:
            for row in projects: print(f"{row['status']:<10} {row['name']} · {row['id']} · {row['path'] or '—'}")
        else:
            for row in sorted(env.projects.glob("*")) if env.projects.exists() else []: print(row.name)
        return 0
    if args.command == "agents":
        for row in registry.rows():
            if row["type"] in {"hermes", "claude", "codex", "agent"}: print(f"{row['status']:<12} {row['type']:<8} {row['name']}")
        return 0
    if args.command == "os":
        index = os_registry_path() / "state/index.json"
        data = json.loads(index.read_text(encoding="utf-8")) if index.exists() else {"packages": []}
        print(f"Installed Operative Systems: {len(data.get('packages', []))}"); return 0
    if args.command == "mcp":
        try:
            items = refresh_mcp_inventory(env)
        except RuntimeError as error:
            print(f"MCP refresh failed for {env.name.upper()}: {error}", file=sys.stderr)
            return 1
        print(f"MCP · {env.name.upper()} · {len(items)} configured")
        for item in items:
            print(f"{item['status']:<14} {item['name']} · {item['transport']}")
            for toolkit in item.get("toolkits", []):
                print(
                    f"  {toolkit['status']:<12} {toolkit['name']} · "
                    f"{toolkit['connections']} connection(s)"
                )
        return 0
    if args.command == "skills":
        items = skill_inventory(env); print(f"SKILLS · {env.name.upper()} · {len(items)} installed")
        for item in items: print(f"{item['status']:<10} {item['name']} · {item['source']}")
        return 0
    if args.command == "rules":
        items = rules_inventory(env.home); print(f"RULES · {env.name.upper()} · {len(items)} installed")
        for item in items:
            scope = "ALL PROVIDERS" if "*" in (item.get("providers") or ["*"]) else ", ".join(item.get("providers") or [])
            print(f"{'ON' if item.get('enabled', True) else 'OFF':<4} {item.get('title') or item.get('id')} · {scope}")
        return 0
    if args.command == "system":
        print(f"SYSTEM · {env.name.upper()} · {run('rmux','-V').stdout.strip()}"); return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
