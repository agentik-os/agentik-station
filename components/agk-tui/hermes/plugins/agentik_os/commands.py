"""Canonical object/action command router for Agentik OS."""

from __future__ import annotations

import json
import hashlib
import os
import shlex
from pathlib import Path
from typing import Callable

import yaml

from hermes_cli.config import read_raw_config

from .paths import (
    PathResolver, create_client_layout, create_mission_layout,
    create_project_layout, normalize_slug,
)
from .store import ControlObject, ControlStore
from .operator import COMMANDS as OPERATOR_COMMANDS, OperatorCommandService
from .domain import DESCRIPTIONS as DOMAIN_DESCRIPTIONS, DOMAIN_COMMANDS, DomainCommandService
from .os_registry import OSRegistry, resolve_assignments


DESCRIPTIONS = {
    "home": "Return to the current Agentik OS environment home context.",
    "active": "Show active context and work.",
    "client": "Create, list, open and inspect clients.",
    "project": "Create, list, open and inspect projects.",
    "mission": "Create, list, open and manage missions.",
    "task": "Create, list, open and manage tasks.",
    "run": "List and inspect execution runs.",
    "os": "Inspect the Operative System registry and active assignments.",
    **OperatorCommandService.descriptions,
    **DOMAIN_DESCRIPTIONS,
}


class AgentikCommandService:
    def __init__(self, environment: str, store: ControlStore, resolver: PathResolver,
                 os_registry_root: Path = Path("/opt/agentik/os-registry"),
                 os_assignment_path: Path | None = None):
        self.environment = environment
        self.data_environment = "mission" if environment == "collective" else environment
        self.store = store
        self.resolver = resolver
        self.os_registry_root = os_registry_root
        self.os_assignment_path = os_assignment_path
        self.operator = OperatorCommandService() if environment == "operator" else None
        self.domain = DomainCommandService(environment, store)
        common = ["home", "active", "os"]
        if environment in {"mission", "collective"}:
            common += ["client", "project", "mission", "task", "run"]
        elif environment in {"agentik", "private"}:
            common += ["project", "mission", "task", "run"]
        elif environment == "operator":
            common += list(OPERATOR_COMMANDS)
        common += list(DOMAIN_COMMANDS.get(environment, ()))
        self.command_names = tuple(common)

    @classmethod
    def from_runtime(cls) -> "AgentikCommandService":
        cfg = read_raw_config() or {}
        environment = str((cfg.get("runtime_identity") or {}).get("environment_id") or "unknown")
        home = Path.home()
        return cls(environment, ControlStore(home / ".agentik" / "control.db"),
                   PathResolver.current(environment))

    def description(self, name: str) -> str:
        return DESCRIPTIONS[name]

    def handler(self, command: str) -> Callable[[str], str]:
        return lambda raw_args="": self.dispatch(command, raw_args)

    @property
    def context_key(self) -> str:
        from hermes_cli.plugins import get_plugin_command_invocation_context

        invocation = get_plugin_command_invocation_context()
        if not invocation:
            return f"environment:{self.environment}:surface:local"
        canonical = json.dumps(invocation, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        surface = str(invocation.get("surface") or "unknown")
        return f"environment:{self.environment}:surface:{surface}:binding:{digest}"

    def context(self) -> dict:
        return self.store.context(self.context_key, self.data_environment)

    def invocation(self) -> dict:
        from hermes_cli.plugins import get_plugin_command_invocation_context
        return get_plugin_command_invocation_context() or {}

    def dispatch(self, command: str, raw_args: str) -> str:
        try:
            argv = shlex.split(raw_args)
        except ValueError as exc:
            return f"Invalid arguments: {exc}"
        try:
            if command == "home":
                self.store.clear_context(self.context_key, self.data_environment)
                return f"Home context restored: {self.environment}."
            if command == "active":
                return self._active()
            if command == "os":
                return self._os(argv)
            if command == "client" and self.data_environment == "mission":
                return self._client(argv)
            if self.operator and command in OPERATOR_COMMANDS:
                return self.operator.dispatch(command, argv)
            if command in DOMAIN_COMMANDS.get(self.environment, ()):
                return self.domain.dispatch(command, argv)
            return self._object(command, argv)
        except (ValueError, PermissionError) as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Agentik OS command failed safely: {exc}"

    def _current_or_target_client(self, target: str | None = None) -> ControlObject | None:
        if target:
            return self.store.get("mission", "client", target)
        object_id = self.context().get("client_id")
        return self.store.get("mission", "client", object_id) if object_id else None

    def _client(self, argv: list[str]) -> str:
        action = argv[0].lower() if argv else "list"
        rest = argv[1:]
        if action in {"new", "list", "open", "current", "status", "info", "archive", "reactivate"}:
            return self._object("client", argv)
        if action in {"project", "mission", "task"}:
            return self._object(action, rest)
        client = self._current_or_target_client(rest[0] if rest and action in {"health"} else None)
        if not client:
            return "No current client. Use `/client open <id-or-slug>` first."
        metadata = client.metadata
        if action == "runtime" and rest and rest[0] == "set":
            mode = rest[1].lower() if len(rest) > 1 else ""
            if mode not in {"local", "vps", "cloud", "hybrid", "external"}:
                return "Usage: /client runtime set local|vps|cloud|hybrid|external"
            updated = self.store.update_metadata(client, {"runtime": mode})
            return f"Client runtime updated: {updated.name} → {mode}."
        if action in {"health", "infrastructure", "integrations", "credentials", "runtime", "activity", "report"}:
            integrations = metadata.get("integrations", {}) if isinstance(metadata.get("integrations"), dict) else {}
            runtime = metadata.get("runtime", "unconfigured")
            if action == "credentials":
                names = metadata.get("secret_names", [])
                return "CLIENT CREDENTIALS · " + client.name + "\n" + (
                    "\n".join(f"• {name}: configured" for name in names)
                    if names else "No credential references configured. Secret values are never displayed."
                )
            lines = [f"CLIENT {action.upper()} · {client.name}", f"Runtime: {runtime}"]
            for name in ("github", "vercel", "convex", "tailscale"):
                lines.append(f"{name.title()}: {integrations.get(name, 'unconfigured')}")
            return "\n".join(lines)
        if action == "provision":
            integrations = metadata.get("integrations", {}) if isinstance(metadata.get("integrations"), dict) else {}
            checks = {
                "identity": bool(client.path and Path(client.path, ".client").is_dir()),
                "workspace": bool(client.path and Path(client.path, "projects").is_dir()),
                "runtime": metadata.get("runtime") in {"local", "vps", "cloud", "hybrid", "external"},
                "github": integrations.get("github") == "configured",
                "vercel": integrations.get("vercel") in {"configured", "not-required"},
                "convex": integrations.get("convex") in {"configured", "not-required"},
                "secrets": bool(metadata.get("secret_names")),
            }
            lines = [f"CLIENT PROVISIONER · {client.name}"]
            lines += [f"{'✓' if ready else '○'} {name}" for name, ready in checks.items()]
            lines.append("READY" if all(checks.values()) else "PARTIAL · configure missing integrations explicitly")
            return "\n".join(lines)
        if action in {"github", "vercel", "convex"}:
            subaction = rest[0].lower() if rest else "status"
            integrations = dict(metadata.get("integrations", {})) if isinstance(metadata.get("integrations"), dict) else {}
            if subaction in {"status", "projects", "repos", "deployments", "logs"}:
                return f"{action.title()} for {client.name}: {integrations.get(action, 'unconfigured')}."
            if subaction == "connect":
                return (f"Use the secure {action.title()} connector flow for {client.name}. "
                        "Credentials are refused in Discord/chat arguments.")
            return f"Usage: /client {action} status|connect"
        if action in {"export", "handoff"}:
            return f"{action.title()} requires an explicit approved workflow; no data was exported."
        return ("Unknown /client action. Supported: new, list, open, current, status, health, "
                "provision, infrastructure, integrations, credentials, runtime, github, vercel, "
                "convex, project, mission, task, report, archive, reactivate, handoff, export.")

    def _active(self) -> str:
        ctx = self.context()
        lines = [f"AGENTIK OS · {self.environment.upper()}", "", "ACTIVE CONTEXT"]
        invocation = self.invocation()
        lines.append(f"Machine: {invocation.get('machine_id') or 'agk-core'}")
        lines.append(f"Surface: {invocation.get('surface') or 'local'}")
        lines.append(f"Session: {invocation.get('session_id') or '—'}")
        for kind in ("client", "project", "mission", "task", "run"):
            object_id = ctx.get(f"{kind}_id")
            obj = self.store.get(self.data_environment, kind, object_id) if object_id else None
            lines.append(f"{kind.title()}: {obj.name} ({obj.id})" if obj else f"{kind.title()}: —")
        active_tasks = [o for o in self.store.list(self.data_environment, "task") if o.status in {"active", "running", "paused"}]
        active_runs = [o for o in self.store.list(self.data_environment, "run") if o.status in {"active", "running", "paused"}]
        lines += ["", f"Active tasks: {len(active_tasks)}", f"Active runs: {len(active_runs)}"]
        stack = self._os(["stack"]).splitlines()[1:]
        lines.append("Active OS: " + (", ".join(item.removeprefix("• ") for item in stack) if stack else "—"))
        return "\n".join(lines)

    def _object(self, kind: str, argv: list[str]) -> str:
        action = argv[0].lower() if argv else "list"
        rest = argv[1:]
        if action == "new":
            if not rest:
                return f"Usage: /{kind} new <name>"
            return self._create(kind, " ".join(rest))
        if action == "list":
            return self._list(kind)
        if action in {"open", "status", "current", "info"}:
            return self._inspect(kind, action, rest)
        transitions = {
            "start": "running", "pause": "paused", "resume": "running",
            "complete": "completed", "cancel": "cancelled", "archive": "archived",
            "reactivate": "active",
        }
        if action in transitions:
            if not rest:
                return f"Usage: /{kind} {action} <id-or-slug>"
            obj = self.store.get(self.data_environment, kind, rest[0], self._scope_parent_id(kind))
            if not obj:
                return f"{kind.title()} not found: {rest[0]}"
            obj = self.store.transition(obj, transitions[action])
            return f"{kind.title()} {obj.id} → {obj.status}."
        return f"Unknown action `{action}` for /{kind}. Supported: new, list, open, current, status."

    def _parent(self, kind: str) -> ControlObject | None:
        parent_kind = {"project": "client", "mission": "project", "task": "mission", "run": "task"}.get(kind)
        if not parent_kind:
            return None
        object_id = self.context().get(f"{parent_kind}_id")
        return self.store.get(self.data_environment, parent_kind, object_id) if object_id else None

    def _create(self, kind: str, name: str) -> str:
        slug = normalize_slug(name)
        parent = self._parent(kind)
        if kind in {"project", "mission", "task", "run"} and not parent:
            required = {"project": "client" if self.data_environment == "mission" else None,
                        "mission": "project", "task": "mission", "run": "task"}[kind]
            if required:
                raise ValueError(f"open a {required} before creating a {kind}")
        path: Path | None = None
        if kind == "client":
            path = self.resolver.client(slug)
        elif kind == "project":
            client = self.store.get(self.data_environment, "client", self.context().get("client_id")) if self.context().get("client_id") else None
            path = self.resolver.project(slug, client_slug=client.slug if client else None)
        elif kind == "mission" and parent and parent.path:
            path = self.resolver.mission(slug, project_path=Path(parent.path))
        if path and path.exists():
            raise ValueError(f"filesystem target already exists: {path}")
        obj = self.store.create(environment=self.data_environment, kind=kind, slug=slug,
                                name=name, parent_id=parent.id if parent else None,
                                status="planned" if kind in {"mission", "task", "run"} else "active",
                                path=str(path) if path else None)
        try:
            if kind == "client" and path:
                create_client_layout(path, object_id=obj.id, name=name, slug=slug)
            elif kind == "project" and path:
                create_project_layout(path, object_id=obj.id, name=name, slug=slug)
            elif kind == "mission" and path:
                create_mission_layout(path, object_id=obj.id, name=name)
        except Exception:
            # The database event makes the failure auditable; mark the object
            # cancelled so it can never masquerade as a successful provision.
            self.store.transition(obj, "cancelled")
            raise
        self._open(obj)
        suffix = f"\nPath: {path}" if path else ""
        return f"{kind.title()} created: {obj.name} ({obj.id}){suffix}"

    def _scope_parent_id(self, kind: str) -> str | None:
        return self._parent(kind).id if self._parent(kind) else None

    def _list(self, kind: str) -> str:
        objects = self.store.list(self.data_environment, kind, self._scope_parent_id(kind))
        if not objects:
            return f"No {kind}s in the current authorized scope."
        lines = [f"{kind.upper()}S"]
        lines += [f"{'●' if o.status in {'active','running'} else '○'} {o.name} · {o.id} · {o.status}" for o in objects]
        return "\n".join(lines)

    def _inspect(self, kind: str, action: str, rest: list[str]) -> str:
        if action == "current" or not rest:
            object_id = self.context().get(f"{kind}_id")
            obj = self.store.get(self.data_environment, kind, object_id) if object_id else None
        else:
            obj = self.store.get(self.data_environment, kind, rest[0], self._scope_parent_id(kind))
        if not obj:
            return f"No current {kind}." if not rest else f"{kind.title()} not found: {rest[0]}"
        if action == "open":
            self._open(obj)
            return f"Opened {kind}: {obj.name} ({obj.id})."
        return "\n".join([
            f"{kind.upper()} · {obj.name}", f"ID: {obj.id}", f"Slug: {obj.slug}",
            f"Status: {obj.status}", f"Parent: {obj.parent_id or '—'}", f"Path: {obj.path or '—'}",
        ])

    def _open(self, obj: ControlObject) -> None:
        clears = {"client": {"project_id": None, "mission_id": None, "task_id": None, "run_id": None},
                  "project": {"mission_id": None, "task_id": None, "run_id": None},
                  "mission": {"task_id": None, "run_id": None},
                  "task": {"run_id": None}, "run": {}}
        updates: dict[str, str | None] = dict(clears.get(obj.kind, {}))
        for ancestor in self.store.lineage(obj):
            if ancestor.kind in {"client", "project", "mission", "task", "run"}:
                updates[f"{ancestor.kind}_id"] = ancestor.id
        self.store.set_context(self.context_key, self.data_environment, **updates)

    def _os(self, argv: list[str]) -> str:
        action = argv[0].lower() if argv else "list"
        registry_api = OSRegistry(self.os_registry_root)
        packages = registry_api.packages()
        assignment_path = self.os_assignment_path or (Path("/etc/agentik/operator-os/assignments.yaml")
                           if self.environment == "operator" else self.resolver.home / ".agentik" / "os-assignments.yaml")
        try:
            assignments = (yaml.safe_load(assignment_path.read_text(encoding="utf-8")) or {}).get("assignments", [])
        except Exception:
            assignments = []
        if action in {"list", "available"}:
            if not packages:
                return "OPERATIVE SYSTEM REGISTRY\nInstalled packages: 0\nNo Operative Systems are installed."
            return "OPERATIVE SYSTEM REGISTRY\n" + "\n".join(
                f"• {p.get('id')}@{p.get('version')}" for p in packages if isinstance(p, dict)
            )
        if action in {"active", "stack"}:
            records = [item for item in assignments if isinstance(item, dict)]
            stack = resolve_assignments(records, {
                "environment_id": self.data_environment,
                "client_id": self.context().get("client_id"),
                "project_id": self.context().get("project_id"),
                "session_id": self.invocation().get("session_id"),
            })
            if not stack:
                return "ACTIVE OS STACK\n(empty)"
            return "ACTIVE OS STACK\n" + "\n".join(f"• {a}" for a in stack)
        if action == "info":
            if len(argv) < 2:
                return "Usage: /os info <id>"
            matches = [p for p in packages if isinstance(p, dict) and p.get("id") == argv[1]]
            return json.dumps(matches, indent=2, sort_keys=True) if matches else f"Operative System not installed: {argv[1]}"
        if action == "doctor":
            healthy, errors = registry_api.doctor([assignment_path])
            if healthy:
                return f"OPERATIVE SYSTEM DOCTOR\n✓ Registry valid\nInstalled packages: {len(packages)}\nAssignments: valid"
            return "OPERATIVE SYSTEM DOCTOR\n✗ " + "\n✗ ".join(errors)
        if action in {"assign", "apply"}:
            if len(argv) < 2:
                return f"Usage: /os {action} <id@version> [environment|client|project|session]"
            reference = argv[1]
            matches = [p for p in packages if isinstance(p, dict) and f"{p.get('id')}@{p.get('version')}" == reference]
            if not matches:
                return f"Operative System not installed: {reference}"
            scope = (argv[2].lower() if len(argv) > 2 else ("session" if action == "apply" else "environment"))
            if scope not in {"environment", "client", "project", "session"}:
                return "OS assignment scope must be environment, client, project, or session."
            context = self.context(); invocation = self.invocation()
            target = self.data_environment if scope == "environment" else (
                invocation.get("session_id") if scope == "session" else context.get(f"{scope}_id")
            )
            if not target:
                return f"No active {scope} context; OS was not assigned."
            allowed = set(matches[0].get("scope") or [])
            if self.data_environment not in allowed and scope not in allowed and "global" not in allowed:
                return f"OS {reference} is not allowed in {self.data_environment}."
            record = {"os": reference, "scope": scope, "target": str(target)}
            records = [item for item in assignments if isinstance(item, dict)]
            if record not in records:
                records.append(record); self._write_assignments(assignment_path, records)
            return f"OS assigned: {reference} → {scope}:{target}."
        if action in {"unassign", "unload"}:
            if len(argv) < 2:
                return f"Usage: /os {action} <id@version>"
            reference = argv[1]; context = self.context(); invocation = self.invocation()
            requested_scope = "session" if action == "unload" else (argv[2].lower() if len(argv) > 2 else None)
            targets = {self.data_environment, context.get("client_id"), context.get("project_id"), invocation.get("session_id")}
            before = [item for item in assignments if isinstance(item, dict)]
            after = [item for item in before if not (
                item.get("os") == reference and item.get("target") in targets
                and (requested_scope is None or item.get("scope") == requested_scope)
            )]
            if len(after) == len(before):
                return f"No matching active assignment for {reference}."
            self._write_assignments(assignment_path, after)
            return f"OS unassigned: {reference}."
        return ("OS mutation commands are intentionally unavailable until the signed package "
                "installer and validator are deployed. No OS was changed.")

    @staticmethod
    def _write_assignments(path: Path, records: list[dict]) -> None:
        """Atomically persist references only; package contents remain immutable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(yaml.safe_dump({"schema_version": 1, "assignments": records}, sort_keys=False), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            try: temporary.unlink()
            except FileNotFoundError: pass
