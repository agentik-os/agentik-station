"""Read-only Agentik OS catalog for the Hermes dashboard plugin.

Hermes loads this file as a standalone module and mounts ``router`` below
``/api/plugins/agentik-os``.  The API intentionally exposes only a small,
allow-listed view of installed OS packages, Hermes agent definitions, and
their matching Agentik runtime sessions.  Prompt contents, commands,
credentials, and filesystem paths never leave this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import yaml

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover - permits dependency-light import checks
    class APIRouter:  # type: ignore[no-redef]
        def get(self, *_args: Any, **_kwargs: Any) -> Callable:
            return lambda function: function


router = APIRouter()

_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_ENVIRONMENTS = {"operator", "agentik", "mission", "private"}
_OS_SCOPES = _ENVIRONMENTS | {"global", "client", "project", "session"}
_OS_LIST_FIELDS = (
    "dependencies",
    "capabilities",
    "skills",
    "workflows",
    "agents",
    "tools",
    "commands",
    "knowledge",
    "evals",
)
_AGENT_SCOPES = _ENVIRONMENTS | {"global"}


def _hermes_home() -> Path:
    """Resolve the active profile's Hermes home without assuming a Linux user."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except (ImportError, OSError, TypeError, ValueError):
        configured = os.environ.get("HERMES_HOME", "").strip()
        return Path(configured) if configured else Path.home() / ".hermes"


def _raw_config(home: Path) -> dict[str, Any]:
    """Read the raw Hermes config, failing closed to an empty mapping."""
    try:
        from hermes_cli.config import read_raw_config

        value = read_raw_config() or {}
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, TypeError, ValueError, yaml.YAMLError):
        try:
            value = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError):
            return {}
        return value if isinstance(value, dict) else {}


def _environment(home: Path) -> str:
    config = _raw_config(home)
    runtime_identity = config.get("runtime_identity")
    candidate = runtime_identity.get("environment_id") if isinstance(runtime_identity, dict) else None
    if candidate not in _ENVIRONMENTS:
        candidate = os.environ.get("AGENTIK_ENVIRONMENT")
    if candidate not in _ENVIRONMENTS:
        candidate = os.environ.get("USER")
    return str(candidate) if candidate in _ENVIRONMENTS else "unknown"


def _text(value: Any, *, limit: int = 500) -> str:
    """Return bounded display text while rejecting structured values."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _string_list(value: Any, *, allowed: set[str] | None = None) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        normalized = item.strip()
        if not normalized or (allowed is not None and normalized not in allowed):
            return None
        if normalized not in result:
            result.append(normalized)
    return result


def _validate_os_package(raw: Any, root: Path) -> dict[str, Any] | None:
    """Validate one canonical registry entry and return only public fields."""
    if not isinstance(raw, dict):
        return None
    package_id = _text(raw.get("id"), limit=80)
    version = _text(raw.get("version"), limit=80)
    name = _text(raw.get("name"), limit=200)
    description = _text(raw.get("description"), limit=1000)
    raw_scopes = raw.get("scope")
    scopes = list(raw_scopes) if isinstance(raw_scopes, list) else None
    if (
        not _ID.fullmatch(package_id)
        or not _SEMVER.fullmatch(version)
        or not name
        or not isinstance(raw.get("description"), str)
        or not scopes
        or any(not isinstance(scope, str) or scope not in _OS_SCOPES for scope in scopes)
        or len(scopes) != len(set(scopes))
    ):
        return None

    lists: dict[str, list[str]] = {}
    for field in _OS_LIST_FIELDS:
        values = raw.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            return None
        lists[field] = [value[:200] for value in values]

    # An index entry is not an installed package until its immutable package
    # directory exists in the canonical registry.  Other rebuild/archive
    # directories are deliberately never scanned.
    package_dir = root / "packages" / package_id / version
    try:
        package_inside_registry = package_dir.resolve().is_relative_to((root / "packages").resolve())
    except (OSError, RuntimeError, ValueError):
        package_inside_registry = False
    if package_dir.is_symlink() or not package_dir.is_dir() or not package_inside_registry:
        return None

    return {
        "id": package_id,
        "name": name,
        "version": version,
        "description": description,
        "scope": scopes,
        **lists,
    }


def _registry(environment: str) -> dict[str, Any]:
    root_value = os.environ.get("AGK_OS_REGISTRY", "").strip()
    root = Path(root_value) if root_value else Path("/opt/agentik/os-registry")
    index_path = root / "state" / "index.json"
    if not index_path.is_file():
        return {
            "available": False,
            "healthy": False,
            "package_count": 0,
            "invalid_count": 0,
            "packages": [],
        }
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {
            "available": True,
            "healthy": False,
            "package_count": 0,
            "invalid_count": 1,
            "packages": [],
        }

    raw_packages = index.get("packages") if isinstance(index, dict) else None
    if not isinstance(raw_packages, list):
        return {
            "available": True,
            "healthy": False,
            "package_count": 0,
            "invalid_count": 1,
            "packages": [],
        }

    packages: list[dict[str, Any]] = []
    invalid_count = 0
    seen: set[tuple[str, str]] = set()
    for raw in raw_packages:
        package = _validate_os_package(raw, root)
        if package is None:
            invalid_count += 1
            continue
        identity = (package["id"], package["version"])
        if identity in seen:
            invalid_count += 1
            continue
        seen.add(identity)
        scopes = set(package["scope"])
        package["allowed_here"] = "global" in scopes or environment in scopes
        packages.append(package)

    packages.sort(key=lambda item: (item["name"].casefold(), item["version"]))
    return {
        "available": True,
        "healthy": invalid_count == 0,
        "package_count": len(packages),
        "invalid_count": invalid_count,
        "packages": packages,
    }


def _agent_definitions(home: Path, environment: str) -> list[dict[str, Any]]:
    root = home / "agents"
    if not root.is_dir():
        return []

    definitions: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/agent.yaml")):
        try:
            if manifest_path.stat().st_size > 1024 * 1024:
                continue
            manifest_bytes = manifest_path.read_bytes()
            raw = yaml.safe_load(manifest_bytes) or {}
        except (OSError, UnicodeError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue

        agent_id = _text(raw.get("id"), limit=80)
        name = _text(raw.get("name"), limit=200)
        version = _text(raw.get("version"), limit=80)
        description = _text(raw.get("description"), limit=1000)
        scopes = _string_list(raw.get("scope"), allowed=_AGENT_SCOPES)
        runtime = _text(raw.get("runtime"), limit=80)
        distribution = _text(raw.get("distribution"), limit=80)
        if (
            not _ID.fullmatch(agent_id)
            or not name
            or not _SEMVER.fullmatch(version)
            or not isinstance(raw.get("description"), str)
            or not scopes
            or not runtime
        ):
            continue

        prompt_value = _text(raw.get("prompt") or "prompt.md", limit=200)
        prompt_path = manifest_path.parent / prompt_value
        try:
            prompt_present = prompt_path.resolve().is_relative_to(manifest_path.parent.resolve()) and prompt_path.is_file()
        except (OSError, RuntimeError, ValueError):
            prompt_present = False

        aliases = _string_list(raw.get("aliases", [])) or []
        scope_set = set(scopes)
        definitions.append(
            {
                "id": agent_id,
                "name": name,
                "version": version,
                "description": description,
                "scope": scopes,
                "runtime": runtime,
                "distribution": distribution,
                "prompt_present": prompt_present,
                "allowed_here": "global" in scope_set or environment in scope_set,
                "definition_hash": hashlib.sha256(manifest_bytes).hexdigest(),
                "_aliases": aliases,
            }
        )

    definitions.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    return definitions


def _runtime_sessions(home: Path, environment: str) -> list[dict[str, Any]]:
    override = os.environ.get("AGK_RUNTIME_DB", "").strip()
    path = Path(override) if override else home.parent / ".agentik" / "runtime.db"
    if not path.is_file():
        return []

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{quote(str(path), safe='/')}?mode=ro",
            uri=True,
            timeout=1,
        )
        connection.row_factory = sqlite3.Row
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(runtime_sessions)")
            if len(row) > 1
        }
        required = {"id", "name", "type", "environment", "status"}
        if not required.issubset(columns):
            return []

        selected = ["id", "name", "type", "environment", "status"]
        selected.extend(field for field in ("last_activity", "exit_code", "archived_at") if field in columns)
        where = " WHERE environment = ?"
        parameters: tuple[Any, ...] = (environment,)
        if "archived_at" in columns:
            where += " AND archived_at IS NULL"
        order = " ORDER BY last_activity DESC" if "last_activity" in columns else " ORDER BY name"
        rows = connection.execute(
            f"SELECT {', '.join(selected)} FROM runtime_sessions{where}{order}",
            parameters,
        ).fetchall()
    except (OSError, sqlite3.Error, ValueError):
        return []
    finally:
        if connection is not None:
            connection.close()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        status = _text(row["status"], limit=80) or "unknown"
        session = {
            "id": _text(row["id"], limit=120),
            "name": _text(row["name"], limit=120),
            "runtime": _text(row["type"], limit=80),
            "status": status,
            "active": status not in {"archived", "completed", "failed", "stopped", "cancelled"},
            "last_activity": None,
            "exit_code": None,
        }
        if "last_activity" in row.keys() and isinstance(row["last_activity"], (int, float)):
            session["last_activity"] = float(row["last_activity"])
        if "exit_code" in row.keys() and isinstance(row["exit_code"], int):
            session["exit_code"] = row["exit_code"]
        if session["id"] and session["name"]:
            sessions.append(session)
    return sessions


def _attach_sessions(
    definitions: list[dict[str, Any]], sessions: list[dict[str, Any]], environment: str
) -> None:
    for definition in definitions:
        agent_id = definition["id"]
        names = {agent_id, f"{environment}-{agent_id}", *definition.pop("_aliases", [])}
        definition["sessions"] = [session for session in sessions if session["name"] in names]


@router.get("/catalog")
async def catalog() -> dict[str, Any]:
    """Return the active profile's sanitized OS and agent catalog."""
    home = _hermes_home()
    environment = _environment(home)
    definitions = _agent_definitions(home, environment)
    sessions = _runtime_sessions(home, environment)
    _attach_sessions(definitions, sessions, environment)
    active_session_count = sum(
        1 for definition in definitions for session in definition["sessions"] if session["active"]
    )
    return {
        "environment": environment,
        "registry": _registry(environment),
        "agents": definitions,
        "sync": {
            "agent_count": len(definitions),
            "active_session_count": active_session_count,
        },
    }
