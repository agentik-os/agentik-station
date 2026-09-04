#!/usr/bin/env python3
"""Transactional AGK client organizations and delivery governance."""

from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
CANONICAL_QA_VIEWPORTS = (
    ("mobile", 390, 844),
    ("ipad", 820, 1180),
    ("desktop", 1440, 900),
    ("large_desktop", 1920, 1080),
)
CLIENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
SESSION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}-[1-9][0-9]*$")
LINEAR_ATTACHMENT_REQUIRED_STATES = {
    "security_review",
    "staging",
    "business_review",
    "ready_for_cto",
    "cto_approved",
    "ready_to_deploy",
    "production",
    "verified",
    "done",
}
REQUIRED_DIRS = (
    "repos",
    "knowledge",
    "projects",
    "artifacts",
    "deployments",
    "infrastructure",
    "automation",
    "scripts",
    "logs",
    "state/work",
    "state/reviews",
    "state/runs",
    "tmp",
)
REQUIRED_CONFIG = (
    "manifest.yaml",
    "runtime.yaml",
    "integrations.yaml",
    "permissions.yaml",
    "workflow.yaml",
    "team.yaml",
    "operations.yaml",
)
DISCORD_CHANNELS = (
    "dev-requests",
    "cto-inbox",
    "reviews",
    "releases",
    "incidents",
    "client-status",
    "agent-activity",
)


class ClientError(RuntimeError):
    """A safe, user-facing client control failure."""


@dataclass(frozen=True)
class Layout:
    home: Path
    workspace: Path
    clients: Path
    system: Path
    registry: Path
    secrets: Path
    source: Path

    @classmethod
    def current(cls) -> "Layout":
        home = Path(
            os.environ.get("AGK_CONTROL_HOME")
            or os.environ.get("HOME")
            or Path.home()
        ).expanduser().resolve()
        workspace = (
            Path(os.environ.get("AGK_CLIENT_WORKSPACE", home / "workspace"))
            .expanduser()
            .resolve()
        )
        install_root = (
            Path(
                os.environ.get("AGK_TERMINAL_ROOT", Path(__file__).resolve().parents[1])
            )
            .expanduser()
            .resolve()
        )
        source = install_root / "client"
        return cls(
            home=home,
            workspace=workspace,
            clients=workspace / "clients",
            system=workspace / "system",
            registry=workspace / "system" / "registry.yaml",
            secrets=home / ".config" / "agk" / "clients",
            source=source,
        )

    def client(self, slug: str) -> Path:
        validate_slug(slug)
        return self.clients / slug

    def secret_file(self, slug: str) -> Path:
        validate_slug(slug)
        return self.secrets / slug / "env"


def validate_slug(value: str) -> str:
    if not CLIENT_RE.fullmatch(value):
        raise ClientError("client id must be 3-50 lowercase letters, digits or hyphens")
    return value


def validate_name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 100 or any(ord(char) < 32 for char in value):
        raise ClientError("client name must be 1-100 printable characters")
    return value


def validate_issue(value: str) -> str:
    value = value.strip().upper()
    if not ISSUE_RE.fullmatch(value):
        raise ClientError("work requires a canonical Linear issue such as FOU-142")
    return value


def hermes_profile_id(slug: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", slug)[:24]
    digest = hashlib.sha256(slug.encode()).hexdigest()[:6]
    return f"client{compact}{digest}"


def canonical_team_identity(team: dict[str, Any], role: str) -> str:
    identities = team.get("canonical_identities", {})
    aliases = team.get("role_aliases", {})
    if isinstance(identities, dict) and role in identities:
        return role
    canonical = aliases.get(role) if isinstance(aliases, dict) else None
    if not isinstance(canonical, str) or not isinstance(identities, dict) or canonical not in identities:
        raise ClientError(f"unknown client team role: {role}")
    return canonical


def branch_component(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (value or "work")[:42].rstrip("-")


def normalize_owner_batch_phrase(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())


def is_owner_go_intent(value: str) -> bool:
    phrase = normalize_owner_batch_phrase(value)
    negative = {
        "do not", "dont", "stop", "cancel", "ne pas", "n execute pas",
        "annule", "arrete", "pas maintenant",
    }
    if any(token in phrase for token in negative):
        return False
    return phrase in {
        "start all ready work",
        "start all eligible work",
        "start all ready linear work",
        "lance tout le travail pret",
        "lance toutes les taches pretes",
        "demarre tout le travail pret",
    }


def is_owner_linear_batch_intent(value: str) -> bool:
    phrase = normalize_owner_batch_phrase(value)
    return is_owner_go_intent(value) and (
        "linear" in phrase or "travail" in phrase or "taches" in phrase or "work" in phrase
    )


def yaml_document(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as error:
        raise ClientError(f"required file is missing: {path}") from error
    except (OSError, yaml.YAMLError, ValueError) as error:
        raise ClientError(f"YAML is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise ClientError(f"YAML root must be an object: {path}")
    return value


def atomic_text(path: Path, value: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_yaml(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    atomic_text(
        path,
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        mode,
    )


@contextlib.contextmanager
def registry_lock(layout: Layout) -> Iterator[None]:
    layout.system.mkdir(parents=True, exist_ok=True)
    lock_path = layout.system / ".client-registry.lock"
    with lock_path.open("a+", encoding="utf-8") as stream:
        os.chmod(lock_path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def client_lock(layout: Layout, slug: str, operation: str) -> Iterator[None]:
    slug = validate_slug(slug)
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,80}", operation):
        raise ClientError("invalid client operation lock")
    directory = layout.client(slug) / "state" / ".locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{operation}.lock"
    with path.open("a+", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def work_lock(layout: Layout, slug: str, work_id: str) -> Iterator[None]:
    if not re.fullmatch(r"WORK-[A-F0-9]{12}", work_id):
        raise ClientError("invalid AGK work id")
    with client_lock(layout, slug, work_id):
        yield


def load_registry(layout: Layout) -> dict[str, Any]:
    if not layout.registry.exists():
        return {"schema_version": SCHEMA_VERSION, "clients": []}
    value = yaml_document(layout.registry)
    clients = value.get("clients", [])
    if not isinstance(clients, list):
        raise ClientError("client registry 'clients' must be a list")
    value.setdefault("schema_version", SCHEMA_VERSION)
    return value


def registry_id(entry: object) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("id") or entry.get("slug") or "")


def default_file(layout: Layout, name: str) -> dict[str, Any]:
    return yaml_document(layout.source / "defaults" / name)


def merge_client_upgrade(default: object, current: object) -> object:
    default_is_container = isinstance(default, (dict, list))
    current_is_container = isinstance(current, (dict, list))
    if default_is_container != current_is_container:
        raise ClientError("client config upgrade has an incompatible type")
    if isinstance(default, dict) and not isinstance(current, dict):
        raise ClientError("client config upgrade has an incompatible type")
    if isinstance(default, list) and not isinstance(current, list):
        raise ClientError("client config upgrade has an incompatible type")
    if isinstance(default, dict) and isinstance(current, dict):
        merged = copy.deepcopy(current)
        for key, default_value in default.items():
            if key in current:
                merged[key] = merge_client_upgrade(default_value, current[key])
            else:
                merged[key] = copy.deepcopy(default_value)
        return merged
    if isinstance(default, list) and isinstance(current, list):
        merged = copy.deepcopy(default)
        for value in current:
            if value not in merged:
                merged.append(copy.deepcopy(value))
        return merged
    if default is not None and type(default) is not type(current):
        raise ClientError("client config upgrade has an incompatible type")
    return copy.deepcopy(current)


def migrate_existing_client_configs(layout: Layout, registry: dict[str, Any]) -> None:
    for entry in registry.get("clients", []):
        slug = registry_id(entry)
        if not slug:
            continue
        slug = validate_slug(slug)
        config = layout.client(slug) / ".client"
        if not config.is_dir():
            raise ClientError(f"registered client config is missing: {slug}")
        manifest = yaml_document(config / "manifest.yaml")
        profile = manifest.get("profile", {}) if isinstance(manifest, dict) else {}
        profile_id = (
            str(profile.get("hermes_profile") or hermes_profile_id(slug))
            if isinstance(profile, dict)
            else hermes_profile_id(slug)
        )
        replacements = {
            "workflow.yaml": default_file(layout, "workflow.yaml"),
            "team.yaml": default_file(layout, "team.yaml"),
            "operations.yaml": default_file(layout, "operations.yaml"),
        }
        replacements["team.yaml"]["client_id"] = slug
        replacements["team.yaml"]["hermes_profile"] = profile_id
        for filename, replacement in replacements.items():
            path = config / filename
            if path.is_symlink():
                raise ClientError(f"client config upgrade target is unsafe: {slug}/{filename}")
            current = yaml_document(path) if path.is_file() else {}
            current_schema = int(current.get("schema_version") or 0)
            target_schema = int(replacement.get("schema_version") or 0)
            if current_schema >= target_schema:
                continue
            backup = (
                layout.system
                / "audit"
                / "client-config-migrations"
                / slug
                / f"{filename.removesuffix('.yaml')}.schema-{current_schema}.yaml"
            )
            if current_schema and not backup.exists():
                atomic_yaml(backup, current, 0o400)
            merged = merge_client_upgrade(replacement, current)
            if not isinstance(merged, dict):
                raise ClientError(f"client config upgrade is invalid: {slug}/{filename}")
            merged["schema_version"] = target_schema
            if filename == "team.yaml":
                merged["client_id"] = slug
                merged["hermes_profile"] = profile_id
            atomic_yaml(path, merged, 0o600)


def bootstrap(layout: Layout, *, upgrade: bool) -> None:
    standard_source = layout.source / "CLIENT-STANDARD.md"
    delivery_master_source = layout.source / "AGK_CLIENT_DELIVERY_SYSTEM_MASTER.md"
    if not standard_source.is_file():
        raise ClientError(f"installed client standard is missing: {standard_source}")
    if not delivery_master_source.is_file():
        raise ClientError(
            f"installed client delivery master is missing: {delivery_master_source}"
        )
    layout.clients.mkdir(parents=True, exist_ok=True)
    layout.system.mkdir(parents=True, exist_ok=True)
    layout.secrets.mkdir(parents=True, exist_ok=True)
    os.chmod(layout.secrets, 0o700)
    standard_target = layout.system / "CLIENT-STANDARD.md"
    if upgrade or not standard_target.exists():
        atomic_text(standard_target, standard_source.read_text(encoding="utf-8"), 0o600)
    delivery_master_target = layout.system / "AGK_CLIENT_DELIVERY_SYSTEM_MASTER.md"
    if upgrade or not delivery_master_target.exists():
        atomic_text(
            delivery_master_target,
            delivery_master_source.read_text(encoding="utf-8"),
            0o600,
        )
    if not layout.registry.exists():
        atomic_yaml(
            layout.registry,
            {"schema_version": SCHEMA_VERSION, "clients": []},
            0o600,
        )
    elif upgrade:
        with registry_lock(layout):
            registry = load_registry(layout)
            registry["schema_version"] = SCHEMA_VERSION
            atomic_yaml(layout.registry, registry, 0o600)
        migrate_existing_client_configs(layout, registry)


def render_template(source: Path, replacements: dict[str, str]) -> str:
    value = source.read_text(encoding="utf-8")
    for key, replacement in replacements.items():
        value = value.replace("{{" + key + "}}", replacement)
    leftovers = re.findall(r"\{\{[A-Z0-9_]+\}\}", value)
    if leftovers:
        raise ClientError(f"unresolved template markers in {source}: {leftovers}")
    return value


def integration_document(slug: str, args: argparse.Namespace) -> dict[str, Any]:
    prefix = f"client-{slug}"
    return {
        "schema_version": SCHEMA_VERSION,
        "composio": {
            "entity_id": prefix,
            "strict_account_selection": True,
        },
        "linear": {
            "enabled": bool(args.linear_workspace or args.linear_team),
            "account_alias": f"{prefix}-linear",
            "workspace_id": args.linear_workspace or None,
            "team_id": args.linear_team or None,
            "delivery_project_id": None,
            "workflow_state_ids": {
                "triage": None,
                "backlog": None,
                "product_definition": None,
                "todo": None,
                "ready_for_engineering": None,
                "in_progress": None,
                "blocked": None,
                "agent_review": None,
                "engineering_review": None,
                "automated_qa": None,
                "qa": None,
                "failed_qa": None,
                "security_review": None,
                "failed_security": None,
                "staging": None,
                "business_review": None,
                "ready_for_cto": None,
                "cto_review": None,
                "changes_requested": None,
                "cto_approved": None,
                "approved_for_prod": None,
                "ready_to_deploy": None,
                "release_queued": None,
                "production": None,
                "deploying": None,
                "failed_deploy": None,
                "rollback": None,
                "verified": None,
                "production_verify": None,
                "done": None,
            },
            "release_controller": {
                "enabled": False,
                "operational_acceptance_verified": False,
                "mode": "dry_run_until_acceptance_test",
                "fail_closed": True,
                "dedupe_key": "linear_issue+approval_id+pr_head_sha",
                "merge_method": "github_api_or_merge_queue",
            },
            "webhook_id": None,
            "webhook_secret_set": False,
            "webhook_replay_window_seconds": 60,
        },
        "github": {
            "enabled": args.github_mode != "none",
            "account_alias": f"{prefix}-github",
            "access_mode": args.github_mode,
            "organization": args.github_org or None,
            "repositories": [],
            "ssh_host_alias": f"github-{slug}",
        },
        "vercel": {
            "enabled": bool(getattr(args, "vercel", False)),
            "account_alias": f"{prefix}-vercel",
            "team_id": None,
            "project_ids": [],
        },
        "convex": {
            "enabled": bool(getattr(args, "convex", False)),
            "credential_backend": "client-secret-store",
            "deployment_ids": {
                "development": None,
                "staging": None,
                "production": None,
            },
            "token_set": False,
        },
        "google_drive": {
            "enabled": bool(getattr(args, "google_drive", False)),
            "account_alias": f"{prefix}-googledrive",
            "account_selector": None,
            "meeting_summary_folder_ids": [],
            "shared_drive_id": None,
            "supports_all_drives": True,
            "processed_state": "state/meeting-intake/processed.json",
            "intake_policy": {
                "destination": "linear",
                "apply_mode": "candidate_backlog_only",
                "dedupe_key": "drive_file_id+content_hash",
                "agent_statuses": ["backlog"],
                "human_start_status": "todo",
                "human_review_states": ["business_review", "ready_for_cto"],
                "human_only_decisions": [
                    "business_review_result", "approved_for_prod", "done",
                ],
                "human_only_statuses": ["cto_approved", "done"],
                "system_only_statuses": [
                    "ready_to_deploy", "production", "verified",
                ],
                "human_gate_mode": "proposal_only",
            },
        },
        "discord": {
            "enabled": bool(args.discord_guild),
            "mode": args.discord_mode,
            "account_alias": f"{prefix}-discordbot",
            "guild_id": args.discord_guild or None,
            "category_id": None,
            "channels": {name.replace("-", "_"): None for name in DISCORD_CHANNELS},
        },
        "figma": {
            "enabled": False,
            "account_alias": f"{prefix}-figma",
            "team_id": None,
            "project_ids": [],
        },
    }


def manifest_document(slug: str, name: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "client": {
            "id": slug,
            "name": name,
            "status": "active",
            "created": dt.date.today().isoformat(),
        },
        "profile": {
            "id": "mission",
            "hermes_profile": hermes_profile_id(slug),
            "session_prefix": f"client-{slug}",
        },
        "providers": {
            "primary": "hermes",
            "allowed": ["hermes", "codex", "claude", "opencode", "openrouter"],
        },
        "isolation": {
            "credentials": "client-scoped",
            "memory": "client-scoped",
            "repositories": "client-scoped",
            "runtime": "client-scoped",
            "cross_client_access": False,
        },
    }


def runtime_document(slug: str, runtime_type: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "client_id": slug,
        "type": runtime_type,
        "local": {"workspace": f"~/workspace/clients/{slug}", "containers": []},
        "vps": {"hosts": []},
        "cloud": {"providers": []},
        "environments": {
            "development": {"target": "local"},
            "staging": {"target": None},
            "production": {"target": None},
        },
        "browser_qa": {
            "enabled": False,
            "authenticated_session_required": True,
            "profiles": [],
            "selection_policy": "exact_client_environment_and_role",
            "forbid_personal_or_cross_client_profile": True,
            "require_live_authentication_probe": True,
            "require_real_navigation": True,
            "require_screenshots_and_linear_attachment": True,
            "require_reverification_after_browser_restart": True,
            "viewports": [
                {"id": name, "width": width, "height": height}
                for name, width, height in CANONICAL_QA_VIEWPORTS
            ],
            "capture_policy": "full_page_unobstructed_after_dismissing_overlays",
        },
    }


def validate_client_init(layout: Layout, args: argparse.Namespace) -> None:
    if bool(args.linear_workspace) != bool(args.linear_team):
        raise ClientError("Linear onboarding requires both workspace_id and team_id")
    if args.github_mode == "org" and not args.github_org:
        raise ClientError("GitHub org mode requires --github-org")
    if args.discord_guild and not str(args.discord_guild).isdigit():
        raise ClientError("Discord guild_id must contain digits only")
    for path in (
        layout.source / "CLIENT-STANDARD.md",
        layout.source / "AGK_CLIENT_DELIVERY_SYSTEM_MASTER.md",
        *(layout.source / "defaults" / name for name in REQUIRED_CONFIG[3:]),
        *(
            layout.source / "templates" / name
            for name in ("README.md", "CLIENT.md", "AGENTS.md", "MEETING-INTAKE-SKILL.md")
        ),
    ):
        if not path.is_file():
            raise ClientError(f"installed client template is missing: {path}")


def create_client(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    name = validate_name(args.name)
    validate_client_init(layout, args)
    destination = layout.client(slug)
    secret_destination = layout.secret_file(slug).parent
    if destination.exists() or secret_destination.exists():
        raise ClientError(f"client already exists or has state: {slug}")
    if args.dry_run:
        return {
            "dry_run": True,
            "client_id": slug,
            "workspace": str(destination),
            "secret_store": str(layout.secret_file(slug)),
            "external_actions": [],
        }

    bootstrap(layout, upgrade=False)
    stage = layout.clients / f".{slug}.stage-{uuid.uuid4().hex}"
    secret_stage = layout.secrets / f".{slug}.stage-{uuid.uuid4().hex}"
    registered = False
    destination_created = False
    secret_created = False
    try:
        stage.mkdir(mode=0o700)
        for relative in REQUIRED_DIRS:
            (stage / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
        replacements = {
            "CLIENT_ID": slug,
            "CLIENT_NAME": name,
            "CREATED_DATE": dt.date.today().isoformat(),
            "RUNTIME_TYPE": args.runtime,
            "HERMES_PROFILE": hermes_profile_id(slug),
        }
        template_root = layout.source / "templates"
        for filename in ("README.md", "CLIENT.md", "AGENTS.md"):
            atomic_text(
                stage / filename,
                render_template(template_root / filename, replacements),
                0o600,
            )
        shutil.copyfile(stage / "AGENTS.md", stage / "CLAUDE.md")
        os.chmod(stage / "CLAUDE.md", 0o600)
        config = stage / ".client"
        config.mkdir(mode=0o700)
        team = default_file(layout, "team.yaml")
        team["client_id"] = slug
        team["hermes_profile"] = hermes_profile_id(slug)
        atomic_yaml(config / "manifest.yaml", manifest_document(slug, name, args))
        atomic_yaml(config / "runtime.yaml", runtime_document(slug, args.runtime))
        atomic_yaml(config / "integrations.yaml", integration_document(slug, args))
        atomic_yaml(
            config / "permissions.yaml", default_file(layout, "permissions.yaml")
        )
        atomic_yaml(config / "workflow.yaml", default_file(layout, "workflow.yaml"))
        atomic_yaml(config / "team.yaml", team)
        atomic_yaml(config / "operations.yaml", default_file(layout, "operations.yaml"))

        secret_stage.mkdir(mode=0o700)
        secret_body = (
            f"# Secrets for AGK client {slug}. Never commit or print this file.\n"
            f"export AGK_CLIENT={slug}\n"
            f"export AGK_CLIENT_WORKSPACE={layout.workspace}\n"
            f"export AGK_CLIENT_DIR={destination}\n"
            "\n# OAuth credentials stay in client-selected Composio accounts.\n"
            "# Add only credentials that cannot be managed by Composio below.\n"
        )
        atomic_text(secret_stage / "env", secret_body, 0o600)

        secret_stage.rename(secret_destination)
        secret_created = True
        stage.rename(destination)
        destination_created = True
        with registry_lock(layout):
            registry = load_registry(layout)
            if any(registry_id(item) == slug for item in registry["clients"]):
                raise ClientError(f"client is already registered: {slug}")
            registry["clients"].append(
                {
                    "id": slug,
                    "name": name,
                    "status": "active",
                    "runtime": args.runtime,
                    "created": dt.date.today().isoformat(),
                    "path": str(destination),
                }
            )
            atomic_yaml(layout.registry, registry, 0o600)
            registered = True
    except Exception:
        if not registered:
            shutil.rmtree(stage, ignore_errors=True)
            shutil.rmtree(secret_stage, ignore_errors=True)
            if destination_created:
                shutil.rmtree(destination, ignore_errors=True)
            if secret_created:
                shutil.rmtree(secret_destination, ignore_errors=True)
        raise
    return {
        "dry_run": False,
        "client_id": slug,
        "workspace": str(destination),
        "secret_store": str(layout.secret_file(slug)),
        "hermes_profile": hermes_profile_id(slug),
        "external_actions": [],
    }


def client_configs(layout: Layout, slug: str) -> dict[str, dict[str, Any]]:
    root = layout.client(slug) / ".client"
    return {name: yaml_document(root / name) for name in REQUIRED_CONFIG}


def convex_checks(config: object) -> list[tuple[str, str]]:
    if not isinstance(config, dict) or not config.get("enabled"):
        return []
    checks: list[tuple[str, str]] = []
    if config.get("token_set") is True:
        checks.append(("ok", "Convex client credential is configured"))
    else:
        checks.append(("fail", "Convex client credential is not configured"))
    deployment_ids = config.get("deployment_ids", {})
    missing = []
    for environment in ("development", "staging", "production"):
        value = deployment_ids.get(environment) if isinstance(deployment_ids, dict) else None
        if not value:
            missing.append(environment)
            checks.append(("fail", f"Convex deployment id is missing: {environment}"))
    if not missing:
        checks.append(
            ("ok", "Convex deployment ids are explicit for development, staging and production")
        )
    return checks


def doctor_one(layout: Layout, slug: str, *, online: bool) -> list[tuple[str, str]]:
    root = layout.client(slug)
    checks: list[tuple[str, str]] = []

    def ok(message: str) -> None:
        checks.append(("ok", message))

    def fail(message: str) -> None:
        checks.append(("fail", message))

    if not root.is_dir():
        return [("fail", f"workspace missing: {root}")]
    ok("workspace exists")
    if root.stat().st_mode & 0o077:
        fail("workspace must not be accessible to group/other")
    else:
        ok("workspace boundary mode is private")
    for relative in REQUIRED_DIRS:
        (ok if (root / relative).is_dir() else fail)(f"directory {relative}")
    for filename in REQUIRED_CONFIG:
        (ok if (root / ".client" / filename).is_file() else fail)(f"config {filename}")
    if any(level == "fail" for level, _ in checks):
        return checks
    configs = client_configs(layout, slug)
    manifest = configs["manifest.yaml"]
    identity = manifest.get("client", {})
    if isinstance(identity, dict) and identity.get("id") == slug:
        ok("manifest identity matches")
    else:
        fail("manifest identity mismatch")
    workflow = configs["workflow.yaml"]
    invariants = workflow.get("invariants", {})
    for key in (
        "durable_work_record_required",
        "linear_issue_required",
        "full_issue_context_required",
        "backlog_is_passive",
        "explicit_human_start_authorization_required",
        "preserve_session_on_changes",
        "preserve_issue_branch_and_pr_on_changes",
        "coding_complete_is_not_qa_complete",
        "real_navigation_required",
        "screenshots_required_for_review",
        "engineering_approval_is_not_deploy_authorization",
        "agents_never_mark_approved_for_prod",
        "agents_never_mark_done",
    ):
        (ok if isinstance(invariants, dict) and invariants.get(key) is True else fail)(
            f"workflow invariant {key}"
        )
    display_names = workflow.get("display_names", {})
    for key, expected in (
        ("agent_review", "Engineering Review"),
        ("automated_qa", "QA"),
        ("security_review", "Security Review"),
        ("staging", "Staging"),
        ("business_review", "Business Review"),
        ("ready_for_cto", "CTO Review"),
        ("cto_approved", "Approved for Prod"),
        ("ready_to_deploy", "Release Queued"),
        ("production", "Deploying"),
        ("verified", "Production Verify"),
    ):
        label = expected
        (ok if isinstance(display_names, dict) and display_names.get(key) == expected else fail)(
            f"workflow maps {label}"
        )
    intake = workflow.get("intake", {})
    issue_contract = (
        set(intake.get("product_definition_requires", []))
        if isinstance(intake, dict)
        else set()
    )
    required_issue_contract = {
        "title", "source", "requester", "business_and_product_context",
        "problem", "requested_outcome", "user_and_business_impact",
        "full_issue_description", "complete_comment_history",
        "attachments_and_screenshots", "acceptance_criteria",
        "technical_context", "affected_repositories_and_services",
        "dependencies", "security_and_data_constraints", "test_plan",
        "real_navigation_requirements", "staging_and_deployment_requirements",
        "evidence_plan", "rollback_considerations",
        "links_to_source_mission_pr_release_incident_and_decisions", "risks",
    }
    (ok if required_issue_contract <= issue_contract else fail)(
        "Linear product definition contract is complete"
    )
    gates = workflow.get("gates", {})
    business_gate = gates.get("business_review", {}) if isinstance(gates, dict) else {}
    business_requirements = set(business_gate.get("requires", [])) if isinstance(business_gate, dict) else set()
    (ok if isinstance(business_gate, dict)
     and business_gate.get("human_decision_required") is True
     and {"business_reviewer_actor", "business_review_timestamp", "business_review_decision_id"} <= business_requirements
     else fail)("Business Review is an actor-attributed human decision")
    cto_gate = gates.get("ready_for_cto", {}) if isinstance(gates, dict) else {}
    cto_requirements = set(cto_gate.get("requires", [])) if isinstance(cto_gate, dict) else set()
    (ok if "security_passed_or_not_required" in cto_requirements else fail)(
        "CTO Review accepts a recorded security disposition"
    )
    tracker = workflow.get("tracker", {})
    (ok if isinstance(tracker, dict)
     and tracker.get("protocol") == "agk-work-tracker/v1"
     and tracker.get("configured_state_ids_are_authoritative") is True
     else fail)("workflow uses the tracker-neutral work protocol")
    autonomy = workflow.get("autonomy", {})
    (ok if isinstance(autonomy, dict)
     and autonomy.get("default_behavior") == "decide-act-verify-record-continue"
     and autonomy.get("questions") == "only-when-no-useful-path-remains"
     else fail)("workflow applies soft autonomy")
    blocked = workflow.get("blocked", {})
    blocked_fields = set(blocked.get("required_fields", [])) if isinstance(blocked, dict) else set()
    (ok if {"blocked_by", "already_tried", "impact", "need", "resume"} <= blocked_fields else fail)(
        "Blocked requires a complete unblock contract"
    )
    comments = workflow.get("comments", {})
    (ok if isinstance(comments, dict)
     and comments.get("dedupe_key") == "work_record+event+artifact_version"
     and comments.get("debug_stream") == "excluded"
     else fail)("workflow material comments are idempotent")
    team = configs["team.yaml"]
    orchestrator = team.get("orchestrator", {})
    (ok if isinstance(orchestrator, dict)
     and orchestrator.get("role") == "atlas"
     and orchestrator.get("provider") == "hermes"
     and orchestrator.get("public_alias") == "project-manager"
     else fail)("team Atlas is the Hermes DevOps orchestrator")
    identities = team.get("canonical_identities", {})
    expected_identities = {"atlas", "architect", "forge", "sentinel", "release-engineer", "sre"}
    (ok if isinstance(identities, dict) and set(identities) == expected_identities else fail)(
        "team has exactly six canonical DevOps identities"
    )
    aliases = team.get("role_aliases", {})
    roles = team.get("roles", {})
    (ok if isinstance(aliases, dict) and isinstance(roles, dict)
     and set(roles) <= set(aliases)
     and set(aliases.values()) <= expected_identities
     else fail)("specialists map to canonical DevOps identities")
    execution_model = team.get("execution_model", {})
    (ok if isinstance(execution_model, dict) and execution_model.get(
        "discord_identity"
    ) == "dedicated_devops_atlas_bot" else fail)(
        "team uses a dedicated DevOps Atlas Discord bot"
    )
    (ok if isinstance(execution_model, dict) and execution_model.get(
        "supervision_surface"
    ) == "agk_tui" and execution_model.get(
        "specialist_sessions"
    ) == "preserved_and_visible" else fail)(
        "team sessions are supervised in AGK TUI"
    )
    discord_channels = team.get("discord_channels", {})
    (ok if isinstance(discord_channels, dict) and discord_channels.get(
        "dev_requests"
    ) == "dev-requests" else fail)(
        "team has a dedicated dev-requests intake channel"
    )
    collaboration = team.get("agent_collaboration", {})
    (ok if isinstance(collaboration, dict) and collaboration.get(
        "changes_requested_resumes_same_session"
    ) is True else fail)(
        "changes requested preserves the same agent session"
    )
    human_gates = team.get("human_gates", {})
    (ok if isinstance(human_gates, dict) and human_gates.get(
        "agents_may_complete_human_fields"
    ) is False else fail)("team preserves human-only decision fields")
    permissions = configs["permissions.yaml"].get("actions", {})
    delete_policy = (
        permissions.get("delete_database", {}) if isinstance(permissions, dict) else {}
    )
    if isinstance(delete_policy, dict) and delete_policy.get("agent_allowed") is False:
        ok("database deletion is forbidden")
    else:
        fail("database deletion policy is unsafe")
    operations = configs["operations.yaml"]
    required_operation_sections = {
        "service_catalog", "environments", "pipelines", "reliability",
        "incidents", "backups", "dependencies", "costs", "access",
        "offboarding", "knowledge",
    }
    (ok if operations.get("contract") == "agk-client-operations/v1"
     and required_operation_sections <= set(operations)
     else fail)("client operations contract is complete")
    secret = layout.secret_file(slug)
    if secret.is_file() and (secret.stat().st_mode & 0o777) == 0o600:
        ok("secret store exists with mode 0600")
    else:
        fail(f"secret store missing or unsafe: {secret}")
    leaks = []
    for pattern in (".env", "*.pem", "*.key", "auth.json", "credentials.json"):
        leaks.extend(root.rglob(pattern))
    if leaks:
        fail("secret-shaped files found inside client workspace")
    else:
        ok("no secret-shaped files inside client workspace")
    registry = load_registry(layout)
    if any(registry_id(item) == slug for item in registry["clients"]):
        ok("client is registered")
    else:
        fail("client is absent from registry")
    active = os.environ.get("AGK_CLIENT")
    if active and active != slug:
        fail(f"foreign client already loaded in shell: {active}")
    else:
        ok("no foreign client loaded")
    if online:
        integrations = configs["integrations.yaml"]
        checks.extend(composio_checks(integrations))
        checks.extend(convex_checks(integrations.get("convex", {})))
    return checks


def parse_connections(value: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        raise ClientError("Composio connections response is not an object")
    result: dict[str, list[dict[str, Any]]] = {}
    for toolkit, raw in value.items():
        if not isinstance(raw, list):
            continue
        result[str(toolkit).lower()] = [item for item in raw if isinstance(item, dict)]
    return result


def composio_executable() -> Path | None:
    discovered = shutil.which("composio")
    if discovered:
        return Path(discovered)
    canonical = Path("/usr/local/lib/agk-terminal/bin/composio")
    return canonical if canonical.is_file() else None


def composio_connections() -> dict[str, list[dict[str, Any]]]:
    executable = composio_executable()
    if not executable:
        raise ClientError("Composio CLI is not installed in this profile")
    result = subprocess.run(
        [str(executable), "connections", "list"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ClientError("Composio connection inventory failed")
    try:
        return parse_connections(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise ClientError(
            "Composio connection inventory returned invalid JSON"
        ) from error


def composio_checks(integrations: dict[str, Any]) -> list[tuple[str, str]]:
    try:
        connections = composio_connections()
    except ClientError as error:
        return [("fail", str(error))]
    checks = []
    toolkit_map = {
        "linear": "linear",
        "github": "github",
        "vercel": "vercel",
        "google_drive": "googledrive",
        "discord": "discordbot",
        "figma": "figma",
    }
    for section, toolkit in toolkit_map.items():
        config = integrations.get(section, {})
        if not isinstance(config, dict) or not config.get("enabled"):
            continue
        if (
            section == "discord"
            and config.get("provisioning_backend") == "client-discord-bot"
        ):
            if config.get("token_set") is True and str(config.get("bot_id") or "").isdigit():
                checks.append(
                    ("ok", "Discord dedicated bot credential is configured in the client vault")
                )
            else:
                checks.append(
                    ("fail", "Discord dedicated bot credential or identity is missing")
                )
            continue
        selector = str(config.get("account_selector") or config.get("account_alias") or "")
        candidates = connections.get(toolkit, [])
        match = next(
            (
                item
                for item in candidates
                if selector
                in {
                    str(item.get("alias") or ""),
                    str(item.get("word_id") or ""),
                    str(item.get("id") or ""),
                }
            ),
            None,
        )
        if match and str(match.get("status") or "").upper() == "ACTIVE":
            checks.append(("ok", f"Composio {section} account is active: {selector}"))
        elif match:
            checks.append(
                ("fail", f"Composio {section} account is not active: {selector}")
            )
        else:
            checks.append(
                ("fail", f"Composio {section} account alias is missing: {selector}")
            )
    return checks


def show_doctor(layout: Layout, slug: str | None, online: bool) -> int:
    bootstrap(layout, upgrade=False)
    registry = load_registry(layout)
    known = [registry_id(item) for item in registry["clients"] if registry_id(item)]
    targets = [validate_slug(slug)] if slug else known
    if not targets:
        print("AGK CLIENT SYSTEM READY · 0 clients · onboarding pending")
        return 0
    failed = False
    for target in targets:
        print(f"CLIENT {target}")
        for level, message in doctor_one(layout, target, online=online):
            marker = "✓" if level == "ok" else "✗"
            print(f"  {marker} {message}")
            failed |= level == "fail"
    return 1 if failed else 0


def integration_plan(layout: Layout, slug: str) -> dict[str, Any]:
    config = client_configs(layout, slug)["integrations.yaml"]
    commands = []
    for section, toolkit in (
        ("linear", "linear"),
        ("github", "github"),
        ("vercel", "vercel"),
        ("google_drive", "googledrive"),
        ("discord", "discordbot"),
        ("figma", "figma"),
    ):
        item = config.get(section, {})
        if isinstance(item, dict) and item.get("enabled"):
            alias = str(item.get("account_alias") or "")
            commands.append(
                {
                    "integration": section,
                    "command": [
                        "agk",
                        "composio",
                        "connect",
                        toolkit,
                        "--alias",
                        alias,
                        "--no-browser",
                        "--no-wait",
                    ],
                    "account_alias": alias,
                }
            )
    return {"client_id": slug, "external_writes": False, "connections": commands}


def discord_plan(layout: Layout, slug: str) -> dict[str, Any]:
    configs = client_configs(layout, slug)
    integrations = configs["integrations.yaml"]
    discord = integrations.get("discord", {})
    if not isinstance(discord, dict) or not discord.get("enabled"):
        raise ClientError("Discord is not enabled for this client")
    guild_id = str(discord.get("guild_id") or "")
    if not guild_id.isdigit():
        raise ClientError("Discord guild_id must be configured before provisioning")
    manifest = configs["manifest.yaml"].get("client", {})
    client_name = (
        str(manifest.get("name") or slug) if isinstance(manifest, dict) else slug
    )
    return {
        "client_id": slug,
        "account_alias": discord.get("account_alias"),
        "guild_id": guild_id,
        "mode": discord.get("mode"),
        "category": f"AGK · {client_name}",
        "channels": list(DISCORD_CHANNELS),
        "idempotent": True,
        "rollback_on_failure": True,
        "external_writes": True,
    }


def unwrap_proxy_payload(value: object) -> object:
    current = value
    for _ in range(3):
        if isinstance(current, dict) and set(current).intersection({"data", "result"}):
            candidate = current.get("data", current.get("result"))
            if candidate is current:
                break
            current = candidate
            continue
        break
    return current


def composio_proxy(
    method: str,
    url: str,
    account: str,
    data: dict[str, Any] | None = None,
) -> object:
    executable = shutil.which("composio")
    if not executable:
        raise ClientError("Composio CLI is not installed in this profile")
    command = [
        executable,
        "proxy",
        url,
        "--toolkit",
        "discordbot",
        "--account",
        account,
        "-X",
        method,
    ]
    if data is not None:
        command.extend(["-H", "content-type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ClientError(f"Composio Discord {method} failed")
    if not result.stdout.strip():
        return {}
    try:
        return unwrap_proxy_payload(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise ClientError("Composio Discord proxy returned invalid JSON") from error


def composio_execute(tool: str, account: str, data: dict[str, Any]) -> object:
    executable = shutil.which("composio")
    if not executable:
        raise ClientError("Composio CLI is not installed in this profile")
    result = subprocess.run(
        [
            executable,
            "execute",
            tool,
            "--account",
            account,
            "-d",
            json.dumps(data),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=45,
    )
    if result.returncode:
        raise ClientError(f"Composio tool failed: {tool}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ClientError(f"Composio tool returned invalid JSON: {tool}") from error
    for item in nested_objects(value):
        if item.get("successful") is False:
            raise ClientError(f"Composio tool reported failure: {tool}")
        if item.get("success") is False:
            raise ClientError(f"Composio tool reported failure: {tool}")
    return value


def nested_objects(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from nested_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_objects(item)


def linear_issue_from_response(value: object, identifier: str) -> dict[str, Any]:
    for item in nested_objects(value):
        if str(item.get("identifier") or "").upper() == identifier:
            return item
    raise ClientError(f"Linear did not return the expected issue: {identifier}")


def linear_collection(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("nodes", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def authoritative_linear_snapshot(
    layout: Layout, slug: str, issue_identifier: str
) -> dict[str, Any]:
    integrations = client_configs(layout, slug)["integrations.yaml"]
    linear = integrations.get("linear", {}) if isinstance(integrations, dict) else {}
    account = str(linear.get("account_alias") or "") if isinstance(linear, dict) else ""
    expected_team = str(linear.get("team_id") or "") if isinstance(linear, dict) else ""
    if not account or not expected_team:
        raise ClientError("Linear account alias and delivery team must be configured")
    response = composio_execute(
        "LINEAR_GET_LINEAR_ISSUE", account, {"issue_id": issue_identifier}
    )
    issue = linear_issue_from_response(response, issue_identifier)
    team = issue.get("team", {})
    team_id = str(team.get("id") or "") if isinstance(team, dict) else ""
    if team_id != expected_team:
        raise ClientError("Linear issue belongs to a different delivery team")

    def allow(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: item.get(key) for key in keys if item.get(key) is not None}

    snapshot = {
        "identifier": str(issue.get("identifier") or "").upper(),
        "id": issue.get("id"),
        "title": issue.get("title"),
        "description": issue.get("description"),
        "url": issue.get("url"),
        "priority": issue.get("priority"),
        "priority_label": issue.get("priorityLabel") or issue.get("priority_label"),
        "updated_at": issue.get("updatedAt") or issue.get("updated_at"),
        "team_id": team_id,
        "state": allow(issue.get("state", {}), ("id", "name", "type"))
        if isinstance(issue.get("state"), dict)
        else {},
        "comments": [
            allow(item, ("id", "body", "createdAt", "updatedAt", "url"))
            for item in linear_collection(issue.get("comments"))
        ],
        "attachments": [
            allow(item, ("id", "title", "url", "subtitle", "createdAt"))
            for item in linear_collection(issue.get("attachments"))
        ],
        "relations": [
            allow(item, ("id", "type", "relatedIssue", "issue"))
            for item in linear_collection(issue.get("relations"))
        ],
    }
    if not snapshot["title"] or snapshot["description"] is None:
        raise ClientError("Linear issue snapshot is missing title or description")
    return snapshot


def control_plane_audit_key(layout: Layout) -> bytes:
    path = layout.home / ".config" / "agk" / "control-plane" / "audit.key"
    if not path.exists():
        atomic_text(path, os.urandom(32).hex() + "\n", 0o600)
    if path.stat().st_mode & 0o777 != 0o600:
        raise ClientError("control-plane audit key must have mode 0600")
    raw = path.read_text().strip()
    try:
        key = bytes.fromhex(raw)
    except ValueError as error:
        raise ClientError("control-plane audit key is invalid") from error
    if len(key) != 32:
        raise ClientError("control-plane audit key must be 256 bits")
    return key


def write_linear_snapshot_receipt(
    layout: Layout,
    slug: str,
    work_id: str,
    *,
    issue: str,
    team_id: str,
    snapshot_sha256: str,
    updated_at: object,
) -> str:
    payload = {
        "client": validate_slug(slug),
        "work_id": work_id,
        "issue": issue,
        "team_id": team_id,
        "snapshot_sha256": snapshot_sha256,
        "linear_updated_at": updated_at,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    receipt = {
        **payload,
        "signature": hmac.new(
            control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
        ).hexdigest(),
    }
    relative = Path("audit") / "linear-snapshots" / slug / f"{work_id}.json"
    path = layout.system / relative
    if path.exists():
        existing = yaml_document(path)
        if existing != receipt:
            raise ClientError("immutable Linear snapshot receipt already exists")
        return str(relative)
    atomic_text(
        path,
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        0o400,
    )
    return str(relative)


def verify_linear_snapshot_receipt(
    layout: Layout, receipt_relative: str, expected: dict[str, Any]
) -> None:
    path = (layout.system / receipt_relative).resolve()
    try:
        path.relative_to(layout.system.resolve())
    except ValueError as error:
        raise ClientError("Linear receipt must stay inside the control plane") from error
    if not path.is_file() or path.stat().st_mode & 0o777 != 0o400:
        raise ClientError("immutable Linear snapshot receipt is unavailable")
    receipt = yaml_document(path)
    signature = str(receipt.pop("signature", ""))
    canonical = json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    calculated = hmac.new(
        control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, calculated):
        raise ClientError("Linear snapshot receipt signature is invalid")
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ClientError("Linear snapshot receipt does not match the work context")


def write_start_authorization_receipt(
    layout: Layout,
    slug: str,
    work_id: str,
    payload: dict[str, Any],
) -> str:
    signed_payload = {"client": validate_slug(slug), "work_id": work_id, **payload}
    canonical = json.dumps(
        signed_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    receipt = {
        **signed_payload,
        "signature": hmac.new(
            control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
        ).hexdigest(),
    }
    relative = Path("audit") / "start-authorizations" / slug / f"{work_id}.json"
    path = layout.system / relative
    if path.exists():
        existing = yaml_document(path)
        if existing != receipt:
            raise ClientError("immutable START authorization receipt already exists")
        return str(relative)
    atomic_text(
        path,
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        0o400,
    )
    return str(relative)


def verify_start_authorization_receipt(
    layout: Layout, receipt_relative: str, expected: dict[str, Any]
) -> None:
    path = (layout.system / receipt_relative).resolve()
    try:
        path.relative_to(layout.system.resolve())
    except ValueError as error:
        raise ClientError("START receipt must stay inside the control plane") from error
    if not path.is_file() or path.stat().st_mode & 0o777 != 0o400:
        raise ClientError("immutable START receipt is unavailable")
    receipt = yaml_document(path)
    signature = str(receipt.pop("signature", ""))
    canonical = json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    calculated = hmac.new(
        control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, calculated):
        raise ClientError("START receipt signature is invalid")
    if receipt != expected:
        raise ClientError("START receipt does not match the authorization")


def ensure_start_message_unused(
    layout: Layout, slug: str, message_id: str, work_id: str
) -> None:
    requested_slug = validate_slug(slug)
    receipt_root = layout.system / "audit" / "start-authorizations"
    if not receipt_root.is_dir():
        return
    for path in receipt_root.glob("*/WORK-*.json"):
        if not path.is_file():
            continue
        receipt = yaml_document(path)
        signature = str(receipt.pop("signature", ""))
        canonical = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        calculated = hmac.new(
            control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, calculated):
            raise ClientError("START receipt signature is invalid")
        if str(receipt.get("message_id") or "") != str(message_id):
            continue
        same_work = (
            str(receipt.get("client") or "") == requested_slug
            and str(receipt.get("work_id") or "") == work_id
        )
        if not same_work:
            raise ClientError("Discord START message already authorized another work")


def write_qa_receipt(
    layout: Layout,
    slug: str,
    work_id: str,
    payload: dict[str, Any],
) -> str:
    signed_payload = {"client": validate_slug(slug), "work_id": work_id, **payload}
    canonical = json.dumps(
        signed_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    receipt = {
        **signed_payload,
        "signature": hmac.new(
            control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
        ).hexdigest(),
    }
    relative = Path("audit") / "qa" / slug / f"{work_id}.json"
    path = layout.system / relative
    if path.exists():
        existing = yaml_document(path)
        if existing != receipt:
            raise ClientError("immutable QA receipt already exists")
        return str(relative)
    atomic_text(
        path,
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        0o400,
    )
    return str(relative)


def verify_qa_receipt(
    layout: Layout, receipt_relative: str, expected: dict[str, Any]
) -> None:
    path = (layout.system / receipt_relative).resolve()
    try:
        path.relative_to(layout.system.resolve())
    except ValueError as error:
        raise ClientError("QA receipt must stay inside the control plane") from error
    if not path.is_file() or path.stat().st_mode & 0o777 != 0o400:
        raise ClientError("immutable QA receipt is unavailable")
    receipt = yaml_document(path)
    signature = str(receipt.pop("signature", ""))
    canonical = json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    calculated = hmac.new(
        control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, calculated):
        raise ClientError("QA receipt signature is invalid")
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ClientError("QA receipt does not match the evidence bundle")


def canonical_linear_attachment_url(
    parsed: urllib.parse.SplitResult,
) -> tuple[str, str, int | None, str, str]:
    try:
        port = parsed.port
    except ValueError as error:
        raise ClientError("Linear attachment requires an HTTPS URL") from error
    if port == 443:
        port = None
    return (
        parsed.scheme.lower(),
        str(parsed.hostname or "").lower(),
        port,
        parsed.path or "/",
        parsed.query,
    )


def validate_linear_attachments(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ClientError("Linear attachment evidence is not structured")
    normalized: list[dict[str, str]] = []
    seen_urls: set[tuple[str, str, int | None, str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ClientError("Linear attachment must be a JSON object")
        title = validate_name(str(item.get("title") or ""))
        subtitle = validate_name(
            str(item.get("subtitle") or "AGK verified evidence")
        )
        url = str(item.get("url") or "").strip()
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ClientError("Linear attachment requires an HTTPS URL")
        canonical_url = canonical_linear_attachment_url(parsed)
        if canonical_url in seen_urls:
            raise ClientError("Linear attachment URLs must be unique")
        seen_urls.add(canonical_url)
        normalized.append({"title": title, "subtitle": subtitle, "url": url})
    return normalized


def linear_sync_plan(layout: Layout, slug: str, work_id: str) -> dict[str, Any]:
    _, work = load_work(layout, slug, work_id)
    integrations = client_configs(layout, slug)["integrations.yaml"]
    linear = integrations.get("linear", {})
    if not isinstance(linear, dict) or not linear.get("enabled"):
        raise ClientError("Linear is not enabled for this client")
    account = str(linear.get("account_alias") or "")
    team_id = str(linear.get("team_id") or "")
    state_ids = linear.get("workflow_state_ids", {})
    state = str(work.get("status") or "")
    state_id = state_ids.get(state) if isinstance(state_ids, dict) else None
    issue = str(work.get("linear", {}).get("issue") or "")
    evidence = work.get("evidence", {})
    repository = work.get("repository", {})
    linear_attachments = validate_linear_attachments(
        evidence.get("linear_attachments", []) if isinstance(evidence, dict) else []
    )
    if state in LINEAR_ATTACHMENT_REQUIRED_STATES and not linear_attachments:
        raise ClientError(
            f"AGK status {state} requires verified Linear attachments"
        )
    latest_event = next(
        (
            str(item.get("event"))
            for item in reversed(work.get("events", []))
            if isinstance(item, dict)
            and item.get("event")
            and item.get("event") != "work.linear_synced"
        ),
        "work.status",
    )
    artifact_version = str(repository.get("commit") or state)
    comment_body = "\n".join(
        (
            f"**Status:** `{state}`",
            f"**Result:** `{latest_event}` for `{work_id}`",
            f"**Evidence:** PR {repository.get('pull_request') or 'pending'}; "
            f"commit `{repository.get('commit') or 'pending'}`; CI/QA/Security "
            f"{bool(evidence.get('ci_passed'))}/"
            f"{bool(evidence.get('qa_passed'))} / "
            f"{evidence.get('security_disposition') in {'passed', 'not_required'}}; "
            f"preview {evidence.get('staging_preview') or 'pending'}; "
            f"attachments {len(linear_attachments)}",
            f"**Next:** synchronize `{state}` and continue with the canonical workflow",
        )
    )
    event_key = f"{work_id}:{latest_event}:{artifact_version}"
    digest = hashlib.sha256(event_key.encode()).hexdigest()[:16]
    marker = f"<!-- agk:{slug}:{work_id}:{latest_event}:{digest} -->"
    comment = f"{comment_body}\n\n{marker}"
    return {
        "client_id": slug,
        "work_id": work_id,
        "issue": issue,
        "account_alias": account,
        "team_id": team_id,
        "agk_status": state,
        "linear_state_id": state_id,
        "state_mapping_ready": bool(state_id),
        "comment": comment,
        "comment_marker": marker,
        "attachments": linear_attachments,
        "attachments_required": state in LINEAR_ATTACHMENT_REQUIRED_STATES,
        "external_writes": True,
    }


def linear_sync_apply(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError(
            "Linear synchronization requires --yes after reviewing the plan"
        )
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return linear_sync_apply_locked(layout, args, slug)


def linear_sync_apply_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    plan = linear_sync_plan(layout, slug, args.work_id)
    account = str(plan["account_alias"] or "")
    state_id = str(plan["linear_state_id"] or "")
    if not account:
        raise ClientError("Linear Composio account alias is not configured")
    if not plan["team_id"]:
        raise ClientError("Linear team_id is not configured")
    if not state_id:
        raise ClientError(
            f"no Linear workflow state id is mapped for AGK status {plan['agk_status']}"
        )

    raw_issue = composio_execute(
        "LINEAR_GET_LINEAR_ISSUE",
        account,
        {"issue_id": plan["issue"]},
    )
    issue = linear_issue_from_response(raw_issue, str(plan["issue"]))
    team = issue.get("team", {})
    if not isinstance(team, dict) or str(team.get("id") or "") != plan["team_id"]:
        raise ClientError("Linear issue belongs to a different client team")
    canonical_issue_id = str(issue.get("id") or plan["issue"])
    existing_attachments = {
        (str(item.get("url") or ""), str(item.get("title") or ""))
        for item in nested_objects(issue.get("attachments", {}))
        if item.get("url") or item.get("title")
    }
    attachments_created = 0
    for attachment in plan.get("attachments", []):
        if not isinstance(attachment, dict):
            raise ClientError("Linear attachment evidence is invalid")
        url = str(attachment.get("url") or "")
        title = str(attachment.get("title") or "")
        if (url, title) in existing_attachments:
            continue
        composio_execute(
            "LINEAR_CREATE_ATTACHMENT",
            account,
            {
                "issue_id": canonical_issue_id,
                "title": title,
                "subtitle": str(attachment.get("subtitle") or "AGK verified evidence"),
                "url": url,
            },
        )
        attachments_created += 1
    if plan.get("attachments"):
        verified_raw = composio_execute(
            "LINEAR_GET_LINEAR_ISSUE", account, {"issue_id": plan["issue"]}
        )
        verified_issue = linear_issue_from_response(
            verified_raw, str(plan["issue"])
        )
        verified_pairs = {
            (str(item.get("url") or ""), str(item.get("title") or ""))
            for item in nested_objects(verified_issue.get("attachments", {}))
            if item.get("url") or item.get("title")
        }
        expected_pairs = {
            (str(item.get("url") or ""), str(item.get("title") or ""))
            for item in plan["attachments"]
            if isinstance(item, dict)
        }
        if not expected_pairs <= verified_pairs:
            raise ClientError("Linear attachment readback did not match evidence")
    comments = issue.get("comments", {})
    marker_exists = any(
        plan["comment_marker"] in str(item.get("body") or "")
        for item in nested_objects(comments)
    )

    mutation = """mutation AGKIssueState($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: {stateId: $stateId}) {
    success
    issue { id identifier state { id name type } }
  }
}"""
    mutation_result = composio_execute(
        "LINEAR_RUN_QUERY_OR_MUTATION",
        account,
        {
            "query_or_mutation": mutation,
            "variables": {"issueId": plan["issue"], "stateId": state_id},
        },
    )
    updated_issue = linear_issue_from_response(mutation_result, str(plan["issue"]))
    updated_state = updated_issue.get("state", {})
    if (
        not isinstance(updated_state, dict)
        or str(updated_state.get("id") or "") != state_id
    ):
        raise ClientError(
            "Linear issue state did not match the requested workflow state"
        )
    comment_created = False
    if not marker_exists:
        composio_execute(
            "LINEAR_CREATE_LINEAR_COMMENT",
            account,
            {"issueId": plan["issue"], "body": plan["comment"]},
        )
        comment_created = True

    path, work = load_work(layout, slug, args.work_id)
    work.setdefault("linear", {})["status_sync"] = plan["agk_status"]
    work_event(
        work,
        "work.linear_synced",
        state_id=state_id,
        comment_created=comment_created,
    )
    atomic_yaml(path, work)
    return {
        "client_id": slug,
        "work_id": args.work_id,
        "issue": plan["issue"],
        "status": plan["agk_status"],
        "comment_created": comment_created,
        "attachments_created": attachments_created,
    }


def discord_apply(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError(
            "Discord provisioning requires --yes after reviewing the plan"
        )
    slug = validate_slug(args.slug)
    with client_lock(layout, slug, "discord-provision"):
        return discord_apply_locked(layout, slug)


def discord_apply_locked(layout: Layout, slug: str) -> dict[str, Any]:
    plan = discord_plan(layout, slug)
    account = str(plan["account_alias"] or "")
    if not account:
        raise ClientError("Discord Composio account alias is not configured")
    guild_id = str(plan["guild_id"])
    base = "https://discord.com/api/v10"
    raw_channels = composio_proxy("GET", f"{base}/guilds/{guild_id}/channels", account)
    if not isinstance(raw_channels, list):
        raise ClientError("Discord channel inventory is not a list")
    channels = [item for item in raw_channels if isinstance(item, dict)]
    created: list[str] = []
    try:
        category = next(
            (
                item
                for item in channels
                if item.get("type") == 4 and item.get("name") == plan["category"]
            ),
            None,
        )
        if category is None:
            value = composio_proxy(
                "POST",
                f"{base}/guilds/{guild_id}/channels",
                account,
                {"name": plan["category"], "type": 4},
            )
            if not isinstance(value, dict) or not str(value.get("id") or "").isdigit():
                raise ClientError("Discord category creation returned no id")
            category = value
            created.append(str(value["id"]))
        category_id = str(category.get("id") or "")
        if not category_id.isdigit():
            raise ClientError("Discord category id is invalid")
        channel_ids: dict[str, str] = {}
        for name in DISCORD_CHANNELS:
            existing = next(
                (
                    item
                    for item in channels
                    if item.get("type") == 0
                    and item.get("name") == name
                    and str(item.get("parent_id") or "") == category_id
                ),
                None,
            )
            if existing is None:
                value = composio_proxy(
                    "POST",
                    f"{base}/guilds/{guild_id}/channels",
                    account,
                    {
                        "name": name,
                        "type": 0,
                        "parent_id": category_id,
                        "topic": f"AGK {slug} · {name}",
                    },
                )
                if (
                    not isinstance(value, dict)
                    or not str(value.get("id") or "").isdigit()
                ):
                    raise ClientError(
                        f"Discord channel creation returned no id: {name}"
                    )
                existing = value
                created.append(str(value["id"]))
            channel_ids[name.replace("-", "_")] = str(existing["id"])

        config_path = layout.client(slug) / ".client" / "integrations.yaml"
        integrations = yaml_document(config_path)
        discord = integrations.get("discord")
        if not isinstance(discord, dict):
            raise ClientError("Discord integration config changed during apply")
        discord["category_id"] = category_id
        discord["channels"] = channel_ids
        atomic_yaml(config_path, integrations)
    except Exception as error:
        rollback_errors = []
        for channel_id in reversed(created):
            try:
                composio_proxy("DELETE", f"{base}/channels/{channel_id}", account)
            except ClientError as rollback_error:
                rollback_errors.append(str(rollback_error))
        suffix = (
            f"; rollback failures: {len(rollback_errors)}" if rollback_errors else ""
        )
        raise ClientError(
            f"Discord provisioning failed and was rolled back{suffix}: {error}"
        ) from error
    return {
        "client_id": slug,
        "category_id": category_id,
        "channels": channel_ids,
        "created_resource_ids": created,
    }


def activate_client(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError("Hermes client-profile activation requires --yes")
    slug = validate_slug(args.slug)
    manifest = client_configs(layout, slug)["manifest.yaml"]
    profile = manifest.get("profile", {})
    profile_id = (
        str(profile.get("hermes_profile") or "") if isinstance(profile, dict) else ""
    )
    if not re.fullmatch(r"[a-z0-9]+", profile_id):
        raise ClientError("client Hermes profile id is invalid")
    profile_home = layout.home / ".hermes" / "profiles" / profile_id
    created = False
    if not profile_home.is_dir():
        hermes = shutil.which("hermes")
        if not hermes:
            raise ClientError("Hermes is not installed in this profile")
        result = subprocess.run(
            [
                hermes,
                "profile",
                "create",
                profile_id,
                "--no-alias",
                "--description",
                f"Isolated AGK execution context for client {slug}.",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if result.returncode or not profile_home.is_dir():
            raise ClientError("Hermes client profile creation failed")
        created = True
    instructions = (layout.client(slug) / "AGENTS.md").read_text(encoding="utf-8")
    atomic_text(
        profile_home / "AGK-CLIENT.md",
        instructions,
        0o600,
    )
    soul = profile_home / "SOUL.md"
    if not soul.exists():
        atomic_text(soul, instructions, 0o600)
    identity = manifest.get("client", {})
    client_name = (
        str(identity.get("name") or slug) if isinstance(identity, dict) else slug
    )
    intake_template = layout.source / "templates" / "MEETING-INTAKE-SKILL.md"
    intake_content = render_template(
        intake_template,
        {"CLIENT_ID": slug, "CLIENT_NAME": client_name},
    )
    atomic_text(
        profile_home / "skills" / "client-meeting-intake" / "SKILL.md",
        intake_content,
        0o600,
    )
    setup_required = not (profile_home / "config.yaml").is_file()
    return {
        "client_id": slug,
        "hermes_profile": profile_id,
        "created": created,
        "setup_required": setup_required,
        "next_command": (
            f"hermes --profile {profile_id} setup" if setup_required else None
        ),
    }


def agk_runtime(layout: Layout) -> tuple[Any, Any]:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        from agk_control import Environment, RuntimeRegistry  # type: ignore
    except (ImportError, OSError) as error:
        raise ClientError("AGK runtime registry is unavailable") from error
    environment = Environment.current()
    if environment.home.resolve() != layout.home:
        raise ClientError("AGK client runtime resolved a different profile HOME")
    return environment, RuntimeRegistry(environment)


def provider_command(provider: str, profile_id: str, workspace: Path) -> list[str]:
    if provider in {"hermes", "openrouter"}:
        hermes = shutil.which("hermes") or "hermes"
        command = [hermes, "-p", profile_id]
        if provider == "openrouter":
            command.extend(
                [
                    "--provider",
                    "openrouter",
                    "--model",
                    os.environ.get("AGK_OPENROUTER_MODEL", "stealth/ox-alpha"),
                ]
            )
        command.extend(["--in", str(workspace)])
        return command
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        from agk_control import default_command  # type: ignore
    except (ImportError, OSError) as error:
        raise ClientError("AGK provider command registry is unavailable") from error
    try:
        return default_command(provider)
    except ValueError as error:
        raise ClientError(f"unsupported client work provider: {provider}") from error


def validate_work_start_record(
    layout: Layout, slug: str, work_id: str, record: dict[str, Any]
) -> None:
    context = record.get("context", {})
    authorization = record.get("authorization", {})
    issue = str(record.get("linear", {}).get("issue") or "")
    if not isinstance(context, dict) or context.get("complete") is not True:
        raise ClientError("work start requires complete Linear context")
    snapshot_record = context.get("linear_snapshot", {})
    if not isinstance(snapshot_record, dict):
        raise ClientError("work start requires a signed Linear snapshot")
    snapshot_path = (
        layout.client(slug) / str(snapshot_record.get("path") or "")
    ).resolve()
    try:
        snapshot_path.relative_to(layout.client(slug).resolve())
    except ValueError as error:
        raise ClientError("Linear snapshot must stay inside the client boundary") from error
    snapshot = yaml_document(snapshot_path)
    canonical = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if not hmac.compare_digest(digest, str(snapshot_record.get("sha256") or "")):
        raise ClientError("work start Linear snapshot digest verification failed")
    verify_linear_snapshot_receipt(
        layout,
        str(snapshot_record.get("receipt") or ""),
        {
            "client": slug,
            "work_id": work_id,
            "issue": issue,
            "team_id": str(snapshot_record.get("team_id") or ""),
            "snapshot_sha256": digest,
            "linear_updated_at": snapshot_record.get("updated_at"),
        },
    )
    required = {
        "id", "actor", "actor_id", "source", "timestamp", "channel_id",
        "message_id", "guild_id", "client", "project", "issue", "scope",
        "priority", "constraints", "at", "message_sha256", "message_timestamp",
        "receipt",
    }
    integrations = client_configs(layout, slug)["integrations.yaml"]
    discord = integrations.get("discord", {}) if isinstance(integrations, dict) else {}
    linear = integrations.get("linear", {}) if isinstance(integrations, dict) else {}
    non_empty = required - {"constraints"}
    source = str(authorization.get("source") or "") if isinstance(authorization, dict) else ""
    expected_authorization_id = (
        f"discord:{authorization.get('message_id')}"
        if source == "discord"
        else f"discord-batch:{authorization.get('message_id')}:{work_id}"
    )
    authorization_channel = str(authorization.get("channel_id") or "") if isinstance(authorization, dict) else ""
    channel_is_valid = (
        source == "discord"
        and authorization_channel == str(discord.get("channels", {}).get("dev_requests") or "")
    ) or (
        source == "discord_batch"
        and authorization_channel_is_client_home(integrations, authorization_channel)
    )
    if (
        not isinstance(authorization, dict)
        or not required <= set(authorization)
        or any(authorization.get(key) in (None, "", [], {}) for key in non_empty)
        or not isinstance(authorization.get("constraints"), (list, dict, str))
        or authorization.get("client") != slug
        or authorization.get("issue") != issue
        or authorization.get("actor") != authorization.get("actor_id")
        or authorization.get("actor_id") != str(discord.get("owner_user_id") or "")
        or source not in {"discord", "discord_batch"}
        or authorization.get("guild_id") != str(discord.get("guild_id") or "")
        or not channel_is_valid
        or authorization.get("project")
        != str(linear.get("delivery_project_id") or "")
        or authorization.get("timestamp") != authorization.get("at")
        or authorization.get("id") != expected_authorization_id
    ):
        raise ClientError("work start authorization is incomplete or mismatched")
    verify_start_authorization_receipt(
        layout,
        str(authorization.get("receipt") or ""),
        {
            "client": slug,
            "work_id": work_id,
            **{
                key: value
                for key, value in authorization.items()
                if key != "receipt"
            },
        },
    )


def work_session_prompt(record: dict[str, Any]) -> str:
    context = record.get("context", {})
    snapshot = context.get("linear_snapshot", {}) if isinstance(context, dict) else {}
    return "\n".join(
        (
            "AGK AUTHORIZED WORK SESSION — use this exact immutable context.",
            f"Client: {record.get('client_id')}",
            f"Work: {record.get('id')}",
            f"Linear issue: {record.get('linear', {}).get('issue')}",
            f"Linear snapshot SHA-256: {snapshot.get('sha256')}",
            f"Repository: {record.get('repository', {}).get('repo')}",
            f"Branch: {record.get('repository', {}).get('branch')}",
            f"Role: {record.get('agent', {}).get('role')}",
            "Read the signed snapshot and work record before acting. Preserve this session, issue, branch and PR through every correction loop.",
        )
    )


def start_work_session(layout: Layout, slug: str, work_id: str) -> dict[str, Any]:
    path, record = load_work(layout, slug, work_id)
    if record.get("status") != "in_progress":
        raise ClientError("only IN_PROGRESS work can start or resume its agent session")
    validate_work_start_record(layout, slug, work_id, record)
    profile = client_configs(layout, slug)["manifest.yaml"].get("profile", {})
    profile_id = (
        str(profile.get("hermes_profile") or "") if isinstance(profile, dict) else ""
    )
    profile_home = layout.home / ".hermes" / "profiles" / profile_id
    if not profile_home.is_dir():
        raise ClientError(
            f"activate the client Hermes profile first: agk client activate {slug} --yes"
        )
    if not (profile_home / "config.yaml").is_file():
        raise ClientError(
            f"finish isolated Hermes setup first: hermes --profile {profile_id} setup"
        )
    _environment, registry = agk_runtime(layout)
    session = str(record.get("agent", {}).get("session") or "")
    existing = registry.get(session)
    if existing is not None:
        if existing["client"] != slug or existing["mission"] != work_id:
            raise ClientError("session name is already bound to another AGK context")
        if not registry.runtime.has_session(existing["rmux_session"]):
            registry.restart_frontend(existing)
        runtime = registry.get(session)
        if runtime is None:
            raise ClientError("AGK failed to restore the preserved session")
        created = False
    else:
        provider = str(record.get("agent", {}).get("provider") or "hermes")
        runtime = registry.create(
            name=session,
            kind=provider,
            cwd=layout.client(slug),
            client=slug,
            project=str(record.get("repository", {}).get("repo") or ""),
            mission=work_id,
            command=provider_command(provider, profile_id, layout.client(slug)),
        )
        created = True
        prompt = work_session_prompt(record)
        registry.runtime.send_input(runtime["rmux_session"], prompt)
        work_event(
            record,
            "work.context_injected",
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        )
    record.setdefault("agent", {})["runtime_id"] = runtime["id"]
    record["status"] = "in_progress"
    work_event(
        record,
        "work.session_started" if created else "work.session_resumed",
        runtime_id=runtime["id"],
    )
    atomic_yaml(path, record)
    return {
        "client_id": slug,
        "work_id": work_id,
        "session": session,
        "runtime_id": runtime["id"],
        "created": created,
    }


def resume_work_session(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    path, record = load_work(layout, args.slug, args.work_id)
    if record.get("status") != "in_progress":
        raise ClientError("only IN_PROGRESS work can resume its agent session")
    _, registry = agk_runtime(layout)
    session = str(record.get("agent", {}).get("session") or "")
    runtime = registry.get(session)
    if runtime is None:
        raise ClientError(
            "the preserved AGK session is missing; do not create a replacement"
        )
    if runtime["client"] != args.slug or runtime["mission"] != args.work_id:
        raise ClientError("the preserved session is bound to another AGK context")
    if not registry.runtime.has_session(runtime["rmux_session"]):
        registry.restart_frontend(runtime)
    feedback = args.feedback.strip() if args.feedback else ""
    if feedback:
        issue = record.get("linear", {}).get("issue")
        registry.runtime.send_input(
            runtime["rmux_session"],
            f"REQUEST CHANGES for {issue}. Resume this exact mission and context.\n\n{feedback}",
        )
    work_event(
        record,
        "work.session_resumed",
        runtime_id=runtime["id"],
        feedback_injected=bool(feedback),
    )
    atomic_yaml(path, record)
    return {
        "client_id": args.slug,
        "work_id": args.work_id,
        "session": session,
        "runtime_id": runtime["id"],
    }


def load_work(layout: Layout, slug: str, work_id: str) -> tuple[Path, dict[str, Any]]:
    if not re.fullmatch(r"WORK-[A-F0-9]{12}", work_id):
        raise ClientError("invalid AGK work id")
    path = layout.client(slug) / "state" / "work" / f"{work_id}.yaml"
    return path, yaml_document(path)


def work_event(record: dict[str, Any], event: str, **data: Any) -> None:
    record.setdefault("events", []).append(
        {
            "event": event,
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **data,
        }
    )
    record["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()


def create_work(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    issue = validate_issue(args.issue)
    configs = client_configs(layout, slug)
    team = configs["team.yaml"]
    canonical_identity = canonical_team_identity(team, args.role)
    providers = configs["manifest.yaml"].get("providers", {})
    allowed_providers = (
        providers.get("allowed", []) if isinstance(providers, dict) else []
    )
    if args.provider not in allowed_providers:
        raise ClientError(f"provider is not allowed for this client: {args.provider}")
    github = configs["integrations.yaml"].get("github", {})
    repositories = github.get("repositories", []) if isinstance(github, dict) else []
    if args.repo not in repositories:
        raise ClientError(
            "repository is not declared in .client/integrations.yaml: " + args.repo
        )
    work_id = "WORK-" + uuid.uuid4().hex[:12].upper()
    title = validate_name(args.title)
    branch = args.branch or f"feat/{issue}-{branch_component(title)}"
    session = args.session or f"{slug}-{args.role}-{issue.lower()}"
    if not SESSION_RE.fullmatch(session):
        raise ClientError("session must use lowercase canonical AGK naming")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": work_id,
        "client_id": slug,
        "title": title,
        "status": "backlog",
        "linear": {"issue": issue, "status_sync": "pending"},
        "context": {"complete": False, "fields": {}},
        "authorization": None,
        "agent": {
            "role": args.role,
            "canonical_identity": canonical_identity,
            "provider": args.provider,
            "session": session,
        },
        "repository": {
            "repo": args.repo,
            "branch": branch,
            "pull_request": None,
            "commit": None,
        },
        "environment": {"target": args.target},
        "evidence": {
            "engineering_review_passed": False,
            "ci_passed": False,
            "qa_passed": False,
            "security_disposition": "pending",
            "security_decision_id": None,
            "staging_preview": None,
            "staging_build_version": None,
            "screenshots": [],
            "validation_steps": [],
            "business_review": None,
            "rollback_plan": None,
            "risk": None,
        },
        "approvals": {"engineering": None, "production": None},
        "created_at": now,
        "updated_at": now,
        "events": [],
    }
    work_event(record, "work.created", issue=issue, session=session)
    path = layout.client(slug) / "state" / "work" / f"{work_id}.yaml"
    atomic_yaml(path, record)
    return record


def update_work_context(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    client_root = layout.client(slug).resolve()
    source = Path(args.context_file).expanduser().resolve()
    try:
        source.relative_to(client_root)
    except ValueError as error:
        raise ClientError("context file must stay inside the client boundary") from error
    with work_lock(layout, slug, args.work_id):
        path, record = load_work(layout, slug, args.work_id)
        context = record.get("context")
        if isinstance(context, dict) and context.get("complete") is True:
            raise ClientError("work context is already finalized")
        if record.get("status") != "backlog":
            raise ClientError("work context can only be finalized in Backlog")
        fields = yaml_document(source)
        workflow = client_configs(layout, slug)["workflow.yaml"]
        intake = workflow.get("intake", {})
        required = (
            set(intake.get("product_definition_requires", []))
            if isinstance(intake, dict)
            else set()
        )
        present = {
            key for key, value in fields.items() if value not in (None, "", [], {})
        }
        missing = sorted(required - present)
        if missing:
            raise ClientError("Linear work context is incomplete: " + ", ".join(missing))
        issue_identifier = str(record.get("linear", {}).get("issue") or "")
        snapshot = authoritative_linear_snapshot(layout, slug, issue_identifier)
        snapshot_body = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        snapshot_digest = hashlib.sha256(snapshot_body.encode()).hexdigest()
        snapshot_relative = Path("state") / "work" / f"{args.work_id}.linear-snapshot.json"
        snapshot_path = client_root / snapshot_relative
        atomic_text(
            snapshot_path,
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            0o600,
        )
        receipt_relative = write_linear_snapshot_receipt(
            layout,
            slug,
            args.work_id,
            issue=issue_identifier,
            team_id=str(snapshot["team_id"]),
            snapshot_sha256=snapshot_digest,
            updated_at=snapshot["updated_at"],
        )
        record["context"] = {
            "complete": True,
            "fields": fields,
            "source": str(source.relative_to(client_root)),
            "linear_snapshot": {
                "identifier": issue_identifier,
                "team_id": snapshot["team_id"],
                "updated_at": snapshot["updated_at"],
                "sha256": snapshot_digest,
                "path": str(snapshot_relative),
                "receipt": receipt_relative,
            },
            "finalized_by": validate_name(args.actor),
            "finalized_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        work_event(record, "work.context_finalized", actor=args.actor)
        atomic_yaml(path, record)
        return record


def discord_client_get(layout: Layout, slug: str, endpoint: str) -> dict[str, Any]:
    secret = layout.secret_file(validate_slug(slug))
    token = ""
    for line in secret.read_text().splitlines():
        match = re.match(r"(?:export\s+)?DISCORD_BOT_TOKEN=(.+)", line)
        if match:
            token = match.group(1).strip().strip("'\"")
            break
    if not token:
        raise ClientError("Discord dedicated bot token is unavailable")
    request = urllib.request.Request(
        "https://discord.com/api/v10" + endpoint,
        method="GET",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "AGK-client-control/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise ClientError(
            f"Discord authorization evidence lookup failed (HTTP {error.code})"
        ) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ClientError("Discord authorization evidence lookup failed") from error
    if not isinstance(data, dict):
        raise ClientError("Discord authorization evidence is invalid")
    return data


def discord_client_post(
    layout: Layout,
    slug: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    method: str = "POST",
) -> dict[str, Any]:
    if method not in {"POST", "DELETE"}:
        raise ClientError("Discord client mutation method is not allowed")
    if not endpoint.startswith("/channels/") or ".." in endpoint:
        raise ClientError("Discord client mutation endpoint is not allowed")
    secret = layout.secret_file(validate_slug(slug))
    token = ""
    for line in secret.read_text().splitlines():
        match = re.match(r"(?:export\s+)?DISCORD_BOT_TOKEN=(.+)", line)
        if match:
            token = match.group(1).strip().strip("'\"")
            break
    if not token:
        raise ClientError("Discord dedicated bot token is unavailable")
    body = None
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "AGK-client-control/1",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        "https://discord.com/api/v10" + endpoint,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise ClientError(f"Discord mutation failed (HTTP {error.code})") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise ClientError("Discord mutation failed") from error
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode())
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ClientError("Discord mutation returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ClientError("Discord mutation returned an invalid payload")
    return value


def client_home_channel_ids(integrations: dict[str, Any]) -> set[str]:
    discord = integrations.get("discord", {}) if isinstance(integrations, dict) else {}
    channels = discord.get("channels", {}) if isinstance(discord, dict) else {}
    allowed_keys = {"dev_requests", "client_status"}
    return {
        str(value)
        for key, value in channels.items()
        if key in allowed_keys and str(value or "").isdigit()
    } if isinstance(channels, dict) else set()


def authorization_channel_is_client_home(
    integrations: dict[str, Any], channel_id: str
) -> bool:
    return str(channel_id) in client_home_channel_ids(integrations)


def verified_batch_linear_context(
    layout: Layout,
    slug: str,
    work_id: str,
    record: dict[str, Any],
    expected_team: str,
) -> bool:
    try:
        issue = str(record.get("linear", {}).get("issue") or "")
        context = record.get("context", {})
        snapshot_record = context.get("linear_snapshot", {}) if isinstance(context, dict) else {}
        if (
            not issue
            or not expected_team
            or not isinstance(snapshot_record, dict)
            or str(snapshot_record.get("identifier") or "") != issue
            or str(snapshot_record.get("team_id") or "") != expected_team
        ):
            return False
        snapshot_path = (layout.client(slug) / str(snapshot_record.get("path") or "")).resolve()
        snapshot_path.relative_to(layout.client(slug).resolve())
        snapshot = yaml_document(snapshot_path)
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        if not hmac.compare_digest(digest, str(snapshot_record.get("sha256") or "")):
            return False
        if str(snapshot.get("identifier") or "") != issue or str(snapshot.get("team_id") or "") != expected_team:
            return False
        verify_linear_snapshot_receipt(
            layout,
            str(snapshot_record.get("receipt") or ""),
            {
                "client": slug,
                "work_id": work_id,
                "issue": issue,
                "team_id": expected_team,
                "snapshot_sha256": digest,
                "linear_updated_at": snapshot_record.get("updated_at"),
            },
        )
        return True
    except (ClientError, ValueError, OSError):
        return False


def _batch_work_contract(layout: Layout, slug: str) -> dict[str, Any]:
    eligible: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    integrations = client_configs(layout, slug)["integrations.yaml"]
    linear = integrations.get("linear", {}) if isinstance(integrations, dict) else {}
    expected_team = str(linear.get("team_id") or "") if isinstance(linear, dict) else ""
    work_root = layout.client(slug) / "state" / "work"
    for path in sorted(work_root.glob("WORK-*.yaml")):
        if path.is_symlink() or not path.is_file():
            raise ClientError("batch work inventory contains an unsafe record")
        record = yaml_document(path)
        work_id = str(record.get("id") or "")
        reason = ""
        if record.get("status") != "backlog":
            reason = "not-backlog"
        elif record.get("environment", {}).get("target") == "production":
            reason = "production-requires-separate-authorization"
        elif record.get("authorization"):
            reason = "already-authorized"
        else:
            context = record.get("context", {})
            snapshot = context.get("linear_snapshot", {}) if isinstance(context, dict) else {}
            if not isinstance(context, dict) or context.get("complete") is not True:
                reason = "context-incomplete"
            elif not isinstance(snapshot, dict) or not snapshot.get("receipt"):
                reason = "linear-snapshot-unverified"
            elif not verified_batch_linear_context(layout, slug, work_id, record, expected_team):
                reason = "linear-snapshot-invalid"
        if reason:
            skipped.append({"work_id": work_id, "reason": reason})
        else:
            eligible.append(
                {
                    "work_id": work_id,
                    "issue": str(record.get("linear", {}).get("issue") or ""),
                    "title": str(record.get("title") or "work"),
                }
            )
    return {"client_id": slug, "eligible": eligible, "skipped": skipped}


def _ensure_linear_issue_thread(
    layout: Layout,
    slug: str,
    *,
    channel_id: str,
    issue: str,
    work_id: str,
    title: str,
) -> dict[str, str]:
    content = f"🧵 {issue} · {title}"[:1900]
    starter = discord_client_post(
        layout,
        slug,
        f"/channels/{channel_id}/messages",
        {"content": content, "allowed_mentions": {"parse": []}},
    )
    starter_id = str(starter.get("id") or "")
    if not starter_id.isdigit():
        raise ClientError("Discord issue thread starter returned no message id")
    try:
        thread = discord_client_post(
            layout,
            slug,
            f"/channels/{channel_id}/messages/{starter_id}/threads",
            {"name": f"{issue.lower()}-{work_id.lower()}"[:100], "auto_archive_duration": 1440},
        )
    except Exception:
        discord_client_post(
            layout, slug, f"/channels/{channel_id}/messages/{starter_id}", method="DELETE"
        )
        raise
    thread_id = str(thread.get("id") or "")
    if not thread_id.isdigit():
        discord_client_post(
            layout, slug, f"/channels/{channel_id}/messages/{starter_id}", method="DELETE"
        )
        raise ClientError("Discord issue thread returned no thread id")
    return {"channel_id": channel_id, "starter_message_id": starter_id, "thread_id": thread_id}


def rollback_linear_issue_thread(layout: Layout, slug: str, thread: dict[str, str]) -> None:
    for endpoint in (
        f"/channels/{thread['thread_id']}",
        f"/channels/{thread['channel_id']}/messages/{thread['starter_message_id']}",
    ):
        try:
            discord_client_post(layout, slug, endpoint, method="DELETE")
        except ClientError:
            pass


def authorize_linear_batch(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError("batch authorization requires --yes after reviewing the plan")
    slug = validate_slug(args.slug)
    channel_id = str(args.channel_id)
    message_id = str(args.message_id)
    if not channel_id.isdigit() or not message_id.isdigit():
        raise ClientError("batch authorization requires numeric Discord ids")
    integrations = client_configs(layout, slug)["integrations.yaml"]
    discord = integrations.get("discord", {})
    linear = integrations.get("linear", {})
    if not isinstance(discord, dict) or not isinstance(linear, dict):
        raise ClientError("batch authorization integrations are invalid")
    if not authorization_channel_is_client_home(integrations, channel_id):
        raise ClientError("batch authorization must originate in the client home channel")
    channel = discord_client_get(layout, slug, f"/channels/{channel_id}")
    if str(channel.get("guild_id") or "") != str(discord.get("guild_id") or ""):
        raise ClientError("batch authorization channel belongs to another Discord guild")
    message = discord_client_get(layout, slug, f"/channels/{channel_id}/messages/{message_id}")
    author = message.get("author", {})
    content = str(message.get("content") or "")
    if (
        str(message.get("channel_id") or "") != channel_id
        or not isinstance(author, dict)
        or str(author.get("id") or "") != str(discord.get("owner_user_id") or "")
        or author.get("bot") is True
        or not is_owner_linear_batch_intent(content)
    ):
        raise ClientError("Discord batch authorization intent or owner identity is invalid")
    message_timestamp = validate_start_message_freshness(str(message.get("timestamp") or ""))
    project = str(linear.get("delivery_project_id") or "")
    if not project:
        raise ClientError("batch authorization requires a configured Linear delivery project")
    contract = _batch_work_contract(layout, slug)
    authorized: list[dict[str, str]] = []
    for item in contract["eligible"]:
        work_id = item["work_id"]
        with work_lock(layout, slug, work_id):
            path, record = load_work(layout, slug, work_id)
            if record.get("status") != "backlog" or record.get("authorization"):
                continue
            context = record.get("context", {})
            fields = context.get("fields", {}) if isinstance(context, dict) else {}
            fields = fields if isinstance(fields, dict) else {}
            thread = _ensure_linear_issue_thread(
                layout,
                slug,
                channel_id=channel_id,
                issue=item["issue"],
                work_id=work_id,
                title=item["title"],
            )
            timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
            authorization = {
                "id": f"discord-batch:{message_id}:{work_id}",
                "actor": str(author.get("id")),
                "actor_id": str(author.get("id")),
                "source": "discord_batch",
                "timestamp": timestamp,
                "channel_id": channel_id,
                "message_id": message_id,
                "guild_id": str(discord.get("guild_id") or ""),
                "client": slug,
                "project": project,
                "issue": item["issue"],
                "scope": fields.get("requested_outcome") or record.get("title"),
                "priority": "configured-batch",
                "constraints": fields.get("security_and_data_constraints", []),
                "at": timestamp,
                "message_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "message_timestamp": message_timestamp,
                "batch": True,
                "discord_thread": thread,
            }
            receipt_payload = {"work_id": work_id, **authorization}
            receipt_payload.pop("client", None)
            try:
                authorization["receipt"] = write_start_authorization_receipt(
                    layout, slug, work_id, receipt_payload
                )
                record["authorization"] = authorization
                record["status"] = "todo"
                work_event(record, "work.batch_start_authorized", **authorization)
                atomic_yaml(path, record)
            except Exception:
                rollback_linear_issue_thread(layout, slug, thread)
                raise
            authorized.append(
                {"work_id": work_id, "issue": item["issue"], "thread_id": thread["thread_id"]}
            )
    return {
        "client_id": slug,
        "root_message_id": message_id,
        "authorized": authorized,
        "skipped": contract["skipped"],
    }


def validate_start_message_freshness(
    value: str,
    *,
    now: dt.datetime | None = None,
    max_age_seconds: int = 900,
) -> str:
    try:
        message_time = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ClientError("Discord START message timestamp is invalid") from error
    if message_time.tzinfo is None:
        raise ClientError("Discord START message timestamp is invalid")
    current = now or dt.datetime.now(dt.timezone.utc)
    age_seconds = (current - message_time.astimezone(dt.timezone.utc)).total_seconds()
    if age_seconds < -30 or age_seconds > max_age_seconds:
        raise ClientError("Discord START message is outside the freshness window")
    return message_time.astimezone(dt.timezone.utc).isoformat()


def authorize_work_start(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    if not str(args.channel_id).isdigit() or not str(args.message_id).isdigit():
        raise ClientError("Discord authorization requires numeric channel and message ids")
    path, record = load_work(layout, slug, args.work_id)
    if record.get("status") != "backlog":
        raise ClientError("only Backlog work can be authorized to start")
    context = record.get("context", {})
    if not isinstance(context, dict) or context.get("complete") is not True:
        raise ClientError("READY_FOR_ENGINEERING context is incomplete")
    integrations = client_configs(layout, slug)["integrations.yaml"]
    issue = str(record.get("linear", {}).get("issue") or "")
    linear = integrations.get("linear", {}) if isinstance(integrations, dict) else {}
    expected_team = str(linear.get("team_id") or "") if isinstance(linear, dict) else ""
    snapshot_record = context.get("linear_snapshot", {})
    if (
        not isinstance(snapshot_record, dict)
        or str(snapshot_record.get("identifier") or "") != issue
        or str(snapshot_record.get("team_id") or "") != expected_team
        or len(str(snapshot_record.get("sha256") or "")) != 64
    ):
        raise ClientError("READY_FOR_ENGINEERING requires a verified Linear snapshot")
    snapshot_relative = Path(str(snapshot_record.get("path") or ""))
    snapshot_path = (layout.client(slug) / snapshot_relative).resolve()
    try:
        snapshot_path.relative_to(layout.client(slug).resolve())
    except ValueError as error:
        raise ClientError("Linear snapshot must stay inside the client boundary") from error
    snapshot = yaml_document(snapshot_path)
    snapshot_body = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if not hmac.compare_digest(
        hashlib.sha256(snapshot_body.encode()).hexdigest(),
        str(snapshot_record.get("sha256")),
    ):
        raise ClientError("Linear snapshot digest verification failed")
    if (
        str(snapshot.get("identifier") or "") != issue
        or str(snapshot.get("team_id") or "") != expected_team
    ):
        raise ClientError("Linear snapshot does not match the authorized issue")
    receipt_relative = str(snapshot_record.get("receipt") or "")
    verify_linear_snapshot_receipt(
        layout,
        receipt_relative,
        {
            "client": slug,
            "work_id": args.work_id,
            "issue": issue,
            "team_id": expected_team,
            "snapshot_sha256": str(snapshot_record.get("sha256")),
            "linear_updated_at": snapshot_record.get("updated_at"),
        },
    )

    discord = integrations.get("discord", {}) if isinstance(integrations, dict) else {}
    expected_guild = str(discord.get("guild_id") or "")
    expected_channel = str(discord.get("channels", {}).get("dev_requests") or "")
    expected_owner = str(discord.get("owner_user_id") or "")
    if str(args.channel_id) != expected_channel:
        raise ClientError("start authorization must originate in dev-requests")
    channel = discord_client_get(layout, slug, f"/channels/{args.channel_id}")
    if str(channel.get("guild_id") or "") != expected_guild:
        raise ClientError("start authorization channel belongs to another Discord guild")
    message = discord_client_get(
        layout, slug, f"/channels/{args.channel_id}/messages/{args.message_id}"
    )
    author = message.get("author", {})
    content = str(message.get("content") or "")
    if (
        str(message.get("channel_id") or "") != expected_channel
        or not isinstance(author, dict)
        or str(author.get("id") or "") != expected_owner
        or author.get("bot") is True
    ):
        raise ClientError("start authorization is not from the configured human owner")
    if content != f"START {issue}":
        raise ClientError("Discord message must be the exact START command for this issue")
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    context_fields = context.get("fields", {})
    context_fields = context_fields if isinstance(context_fields, dict) else {}
    project = str(linear.get("delivery_project_id") or "") if isinstance(linear, dict) else ""
    scope = context_fields.get("requested_outcome") or record.get("title")
    constraints = context_fields.get("security_and_data_constraints")
    if not project or not scope or constraints is None:
        raise ClientError("start authorization contract is incomplete")
    message_timestamp = str(message.get("timestamp") or "")
    if not message_timestamp:
        raise ClientError("Discord START message timestamp is unavailable")
    message_timestamp = validate_start_message_freshness(message_timestamp)
    authorization = {
        "id": f"discord:{args.message_id}",
        "actor": expected_owner,
        "actor_id": expected_owner,
        "source": "discord",
        "timestamp": timestamp,
        "channel_id": expected_channel,
        "message_id": str(args.message_id),
        "guild_id": expected_guild,
        "client": slug,
        "project": project,
        "issue": issue,
        "scope": scope,
        "priority": snapshot.get("priority_label") or snapshot.get("priority") or "unspecified",
        "constraints": constraints,
        "at": timestamp,
        "message_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "message_timestamp": message_timestamp,
    }
    receipt_payload = {"work_id": args.work_id, **authorization}
    receipt_payload.pop("client", None)
    with registry_lock(layout):
        ensure_start_message_unused(layout, slug, str(args.message_id), args.work_id)
        with work_lock(layout, slug, args.work_id):
            path, current_record = load_work(layout, slug, args.work_id)
            current_context = current_record.get("context", {})
            current_snapshot = (
                current_context.get("linear_snapshot", {})
                if isinstance(current_context, dict)
                else {}
            )
            if current_record.get("status") != "backlog":
                raise ClientError("only Backlog work can be authorized to start")
            if (
                not isinstance(current_context, dict)
                or current_context.get("complete") is not True
                or current_snapshot != snapshot_record
                or str(current_record.get("linear", {}).get("issue") or "") != issue
            ):
                raise ClientError("READY_FOR_ENGINEERING context changed during authorization")
            authorization["receipt"] = write_start_authorization_receipt(
                layout, slug, args.work_id, receipt_payload
            )
            current_record["authorization"] = authorization
            current_record["status"] = "todo"
            work_event(current_record, "work.start_authorized", **authorization)
            atomic_yaml(path, current_record)
    return current_record


def quarantine_legacy_work(
    layout: Layout,
    slug: str,
    work_id: str,
    *,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Fail closed on work created before governed context and START enforcement."""
    slug = validate_slug(slug)
    with work_lock(layout, slug, work_id):
        return quarantine_legacy_work_locked(
            layout, slug, work_id, actor=actor, reason=reason
        )


def quarantine_legacy_work_locked(
    layout: Layout,
    slug: str,
    work_id: str,
    *,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    path, record = load_work(layout, slug, work_id)
    if isinstance(record.get("legacy_quarantine"), dict):
        return record

    context = record.get("context", {})
    snapshot = context.get("linear_snapshot", {}) if isinstance(context, dict) else {}
    authorization = record.get("authorization", {})
    missing = []
    if not isinstance(context, dict) or context.get("complete") is not True:
        missing.append("complete_context")
    if not isinstance(snapshot, dict) or not snapshot.get("receipt"):
        missing.append("signed_linear_snapshot_receipt")
    required_authorization = {
        "actor_id", "source", "timestamp", "client", "project", "issue",
        "scope", "priority", "constraints", "guild_id", "channel_id", "message_id",
    }
    if (
        not isinstance(authorization, dict)
        or not required_authorization
        <= {key for key, value in authorization.items() if value not in (None, "")}
    ):
        missing.append("authenticated_start_authorization")
    if not missing:
        try:
            validate_work_start_record(layout, slug, work_id, record)
        except ClientError:
            missing.append("invalid_governance_receipts")
    if not missing:
        raise ClientError("governed work cannot be quarantined as legacy")

    previous = str(record.get("status") or "unknown")
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    record["status"] = "blocked"
    record["legacy_quarantine"] = {
        "previous_status": previous,
        "missing": missing,
        "actor": validate_name(actor),
        "reason": validate_name(reason),
        "at": timestamp,
        "retroactive_authorization_forbidden": True,
    }
    work_event(
        record,
        "work.legacy_quarantined",
        actor=actor,
        previous=previous,
        missing=missing,
        reason=reason,
    )
    atomic_yaml(path, record)
    return record


def transition_work(
    layout: Layout,
    slug: str,
    work_id: str,
    target: str,
    *,
    actor: str,
) -> dict[str, Any]:
    slug = validate_slug(slug)
    with work_lock(layout, slug, work_id):
        return transition_work_locked(
            layout, slug, work_id, target, actor=actor
        )


def transition_work_locked(
    layout: Layout,
    slug: str,
    work_id: str,
    target: str,
    *,
    actor: str,
) -> dict[str, Any]:
    path, record = load_work(layout, slug, work_id)
    workflow = client_configs(layout, slug)["workflow.yaml"]
    transitions = workflow.get("transitions", {})
    current = str(record.get("status") or "")
    allowed = transitions.get(current, []) if isinstance(transitions, dict) else []
    if target not in allowed:
        raise ClientError(f"invalid work transition: {current} -> {target}")
    if current not in {"backlog", "todo", "blocked"}:
        validate_work_start_record(layout, slug, work_id, record)
    if target == "todo":
        context = record.get("context", {})
        if not isinstance(context, dict) or context.get("complete") is not True:
            raise ClientError("READY_FOR_ENGINEERING context is incomplete")
        authorization = record.get("authorization", {})
        required_authorization = {"id", "actor_id", "source", "at"}
        if (
            not isinstance(authorization, dict)
            or not required_authorization
            <= {key for key, value in authorization.items() if value}
        ):
            raise ClientError(
                "READY_FOR_ENGINEERING requires a verified human authorization record"
            )
    if target == "in_progress":
        validate_work_start_record(layout, slug, work_id, record)
    if target in {"cto_approved", "ready_to_deploy", "production"}:
        raise ClientError(f"{target} requires its dedicated governed command")
    repository = record.get("repository", {})
    evidence = record.get("evidence", {})
    if target == "automated_qa" and (
        not isinstance(evidence, dict)
        or evidence.get("engineering_review_passed") is not True
    ):
        raise ClientError("QA requires passed engineering review evidence")
    if target == "security_review":
        missing = []
        if not isinstance(evidence, dict) or evidence.get("qa_passed") is not True:
            missing.append("qa_passed")
        if not isinstance(evidence, dict) or not evidence.get("screenshots"):
            missing.append("screenshots")
        if not isinstance(evidence, dict) or not evidence.get("validation_steps"):
            missing.append("validation_steps")
        if missing:
            raise ClientError("Security Review QA evidence is incomplete: " + ", ".join(missing))
        validate_qa_evidence(layout, slug, work_id, evidence)
    if target == "staging":
        validate_qa_evidence(layout, slug, work_id, evidence)
        missing = []
        if not isinstance(repository, dict) or not repository.get("pull_request"):
            missing.append("pull_request")
        if not isinstance(repository, dict) or not repository.get("commit"):
            missing.append("commit")
        for key in ("engineering_review_passed", "ci_passed", "qa_passed"):
            if not isinstance(evidence, dict) or evidence.get(key) is not True:
                missing.append(key)
        disposition = evidence.get("security_disposition") if isinstance(evidence, dict) else None
        if disposition not in {"passed", "not_required"}:
            missing.append("security disposition")
        if not isinstance(evidence, dict) or not evidence.get("security_decision_id"):
            missing.append("security_decision_id")
        if not isinstance(evidence, dict) or not evidence.get("rollback_plan"):
            missing.append("rollback_plan")
        if missing:
            raise ClientError("STAGING gate is incomplete: " + ", ".join(missing))
    if target == "business_review":
        validate_qa_evidence(layout, slug, work_id, evidence)
        missing = []
        for key in ("staging_preview", "staging_build_version", "screenshots", "validation_steps"):
            if not isinstance(evidence, dict) or not evidence.get(key):
                missing.append(key)
        if missing:
            raise ClientError("Business Review staging evidence is incomplete: " + ", ".join(missing))
    if target == "ready_for_cto":
        missing = []
        if not isinstance(repository, dict) or not repository.get("pull_request"):
            missing.append("pull_request")
        for key in (
            "engineering_review_passed", "ci_passed", "qa_passed",
            "staging_preview", "staging_build_version", "screenshots",
            "validation_steps", "rollback_plan",
        ):
            if not isinstance(evidence, dict) or not evidence.get(key):
                missing.append(key)
        disposition = evidence.get("security_disposition") if isinstance(evidence, dict) else None
        if disposition not in {"passed", "not_required"}:
            missing.append("security_disposition")
        if not isinstance(evidence, dict) or not evidence.get("security_decision_id"):
            missing.append("security_decision_id")
        business = evidence.get("business_review") if isinstance(evidence, dict) else None
        required_business = {"result", "actor_id", "decision_id", "at"}
        if (
            not isinstance(business, dict)
            or business.get("result") != "approved"
            or not required_business <= {key for key, value in business.items() if value}
        ):
            missing.append("Business Review human decision")
        if missing:
            raise ClientError(
                "READY_FOR_CTO evidence is incomplete: " + ", ".join(missing)
            )
        validate_qa_evidence(layout, slug, work_id, evidence)
    if target == "verified":
        evidence = record.get("evidence", {})
        if not isinstance(evidence, dict) or not evidence.get(
            "production_health_verified"
        ):
            raise ClientError("VERIFIED requires production health evidence")
    if target == "done":
        linear = record.get("linear", {})
        if not isinstance(linear, dict) or linear.get("status_sync") != "done":
            raise ClientError("DONE requires authoritative Linear completion")
    record["status"] = target
    work_event(
        record, "work.transitioned", actor=actor, previous=current, current=target
    )
    atomic_yaml(path, record)
    return record


def block_work(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        path, record = load_work(layout, slug, args.work_id)
        if not args.no_useful_next_action:
            raise ClientError("Blocked requires confirmation that no useful next action remains")
        payload = {
            "blocked_by": validate_name(args.blocked_by),
            "already_tried": validate_name(args.already_tried),
            "impact": validate_name(args.impact),
            "need": validate_name(args.need),
            "resume": validate_name(args.resume),
            "actor": validate_name(args.actor),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = record.get("blocker", {})
        if record.get("status") == "blocked":
            if isinstance(existing, dict) and existing.get("fingerprint") == fingerprint:
                return record
            raise ClientError("work is already blocked by a different dependency")
        payload.update(
            {
                "previous_status": str(record.get("status") or "todo"),
                "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "fingerprint": fingerprint,
            }
        )
        record["status"] = "blocked"
        record["blocker"] = payload
        work_event(record, "work.blocked", **payload)
        atomic_yaml(path, record)
        return record


def unblock_work(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        path, record = load_work(layout, slug, args.work_id)
        blocker = record.get("blocker", {})
        if record.get("status") != "blocked" or not isinstance(blocker, dict):
            raise ClientError("only blocked work can be unblocked")
        previous = str(blocker.get("previous_status") or "todo")
        target = previous if previous not in {"blocked", "done"} else "todo"
        record["status"] = target
        record["blocker"] = None
        work_event(
            record,
            "work.unblocked",
            actor=validate_name(args.actor),
            result=validate_name(args.result),
            resumed_status=target,
            preserved_session=record.get("agent", {}).get("session"),
        )
        atomic_yaml(path, record)
        return record


def client_evidence_artifact(
    layout: Layout,
    slug: str,
    raw_path: str,
    *,
    suffixes: set[str],
) -> dict[str, Any]:
    root = layout.client(validate_slug(slug)).resolve()
    path = Path(raw_path).expanduser().resolve()
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ClientError("evidence artifact must stay inside the client boundary") from error
    if not path.is_file() or path.stat().st_size <= 0:
        raise ClientError("evidence artifact is missing or empty")
    if path.suffix.lower() not in suffixes:
        raise ClientError("evidence artifact has an unsupported file type")
    image_metadata: dict[str, Any] = {}
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                image_metadata = {
                    "format": str(image.format or "").upper(),
                    "width": image.width,
                    "height": image.height,
                }
        except Exception as error:
            raise ClientError("evidence image does not decode") from error
        if image_metadata["width"] < 1 or image_metadata["height"] < 1:
            raise ClientError("evidence image has invalid dimensions")
    return {
        "path": str(relative),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        **image_metadata,
    }


def canonical_browser_url(value: str) -> tuple[str, str, int | None, str, str]:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ClientError("browser evidence URL is invalid")
    path = parsed.path.rstrip("/") or "/"
    return (
        parsed.scheme.lower(),
        parsed.hostname.lower(),
        parsed.port,
        path,
        parsed.query,
    )


def structured_browser_urls(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "final_url", "page_url", "current_url"} and isinstance(item, str):
                yield item
            else:
                yield from structured_browser_urls(item)
    elif isinstance(value, list):
        for item in value:
            yield from structured_browser_urls(item)


def decode_browser_tool_payload(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        lines = raw.splitlines()
        if (
            len(lines) >= 4
            and lines[0] == '<untrusted_tool_result source="browser_exec">'
            and lines[-1] == "</untrusted_tool_result>"
        ):
            try:
                return json.loads("\n".join(lines[2:-1]))
            except json.JSONDecodeError:
                pass
    raise ClientError("QA browser tool payload is not structured JSON")


def browser_payload_has_profile_binding(
    value: object, profile_binding: dict[str, Any]
) -> bool:
    required = (
        "browser_profile_id",
        "authenticated_principal",
        "authentication_probe_sha256",
    )
    if isinstance(value, dict):
        if all(
            str(value.get(key) or "") == str(profile_binding.get(key) or "")
            for key in required
        ):
            return True
        return any(
            browser_payload_has_profile_binding(item, profile_binding)
            for item in value.values()
        )
    if isinstance(value, list):
        return any(
            browser_payload_has_profile_binding(item, profile_binding) for item in value
        )
    return False


def browser_payload_has_bound_navigation(
    value: object,
    expected_url: tuple[str, str, int | None, str, str],
    profile_binding: dict[str, Any],
) -> bool:
    if isinstance(value, dict):
        required = (
            "browser_profile_id",
            "authenticated_principal",
            "authentication_probe_sha256",
        )
        has_binding = all(
            str(value.get(key) or "") == str(profile_binding.get(key) or "")
            for key in required
        )
        if has_binding:
            for key in ("url", "final_url", "page_url", "current_url"):
                candidate = value.get(key)
                if not isinstance(candidate, str):
                    continue
                try:
                    if canonical_browser_url(candidate) == expected_url:
                        return True
                except ClientError:
                    continue
        return any(
            browser_payload_has_bound_navigation(item, expected_url, profile_binding)
            for item in value.values()
        )
    if isinstance(value, list):
        return any(
            browser_payload_has_bound_navigation(item, expected_url, profile_binding)
            for item in value
        )
    return False


def browser_tool_call_has_session_binding(
    tool_call_id: str,
    serialized_calls: list[str],
    expected_browser_session: str,
) -> bool:
    if not tool_call_id or not expected_browser_session:
        return False
    for raw in serialized_calls:
        try:
            calls = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(calls, dict):
            calls = [calls]
        if not isinstance(calls, list):
            continue
        for call in calls:
            if not isinstance(call, dict) or str(call.get("id") or "") != tool_call_id:
                continue
            function = call.get("function", {})
            if not isinstance(function, dict) or function.get("name") != "browser_exec":
                continue
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if (
                isinstance(arguments, dict)
                and str(arguments.get("session") or "") == expected_browser_session
            ):
                return True
    return False


def verify_browser_session(
    layout: Layout,
    slug: str,
    session_id: str,
    *,
    url: str,
    started_at: float,
    finished_at: float,
    profile_binding: dict[str, Any],
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,100}", session_id):
        raise ClientError("QA browser session id is invalid")
    manifest = client_configs(layout, slug)["manifest.yaml"]
    profile = manifest.get("profile", {}) if isinstance(manifest, dict) else {}
    profile_id = str(profile.get("hermes_profile") or "") if isinstance(profile, dict) else ""
    db_path = layout.home / ".hermes" / "profiles" / profile_id / "state.db"
    if not db_path.is_file():
        raise ClientError("QA browser session store is unavailable")
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        session = conn.execute(
            "SELECT source, started_at, last_activity_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        message_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        tool_call_column = (
            "tool_call_id" if "tool_call_id" in message_columns else "NULL AS tool_call_id"
        )
        rows = conn.execute(
            f"SELECT content, {tool_call_column} FROM messages "
            "WHERE session_id = ? AND role = 'tool' "
            "AND tool_name LIKE 'browser%' AND timestamp BETWEEN ? AND ?",
            (session_id, started_at, finished_at),
        ).fetchall()
        assistant_calls = []
        if "tool_calls" in message_columns:
            assistant_calls = [
                str(row[0])
                for row in conn.execute(
                    "SELECT tool_calls FROM messages "
                    "WHERE session_id = ? AND role = 'assistant' AND tool_calls IS NOT NULL",
                    (session_id,),
                ).fetchall()
                if row[0]
            ]
    except sqlite3.Error as error:
        raise ClientError("QA browser session evidence is unreadable") from error
    finally:
        if conn is not None:
            conn.close()
    expected_url = canonical_browser_url(url)
    url_matches = 0
    bound_matches = 0
    for row in rows:
        try:
            payload = decode_browser_tool_payload(str(row[0] or ""))
        except ClientError:
            continue
        for candidate in structured_browser_urls(payload):
            try:
                if canonical_browser_url(candidate) == expected_url:
                    url_matches += 1
                    if (
                        browser_payload_has_bound_navigation(
                            payload, expected_url, profile_binding
                        )
                        and browser_tool_call_has_session_binding(
                            str(row[1] or ""),
                            assistant_calls,
                            str(profile_binding.get("browser_profile_id") or ""),
                        )
                    ):
                        bound_matches += 1
            except ClientError:
                continue
    if url_matches and not bound_matches:
        raise ClientError(
            "QA session navigation has no authenticated browser tool call binding"
        )
    if (
        session is None
        or bound_matches < 1
        or started_at > finished_at
        or started_at < float(session[1] or 0) - 5
        or finished_at > float(session[2] or 0) + 5
    ):
        raise ClientError("QA session has no matching browser navigation execution")
    return {
        "session_id": session_id,
        "source": str(session[0]),
        "browser_tool_calls": bound_matches,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def validate_qa_evidence(
    layout: Layout, slug: str, work_id: str, evidence: dict[str, Any]
) -> None:
    screenshots = evidence.get("screenshots", [])
    if not isinstance(screenshots, list) or not screenshots:
        raise ClientError("QA evidence has no verified screenshots")
    runtime = client_configs(layout, slug)["runtime.yaml"]
    browser_qa = runtime.get("browser_qa", {}) if isinstance(runtime, dict) else {}
    configured_viewports = browser_qa.get("viewports", []) if isinstance(browser_qa, dict) else []
    required_viewports = {
        (
            str(item.get("id") or ""),
            int(item.get("width") or 0),
            int(item.get("height") or 0),
        )
        for item in configured_viewports
        if isinstance(item, dict)
    }
    canonical_viewports = set(CANONICAL_QA_VIEWPORTS)
    if required_viewports != canonical_viewports:
        raise ClientError("QA runtime policy must retain the canonical four viewports")
    required_viewports = canonical_viewports
    observed_viewports = {
        (
            str(item.get("viewport") or ""),
            int(item.get("width") or 0),
            int(item.get("height") or 0),
        )
        for item in screenshots
        if isinstance(item, dict)
    }
    if not required_viewports or not required_viewports <= observed_viewports:
        missing = sorted(required_viewports - observed_viewports)
        raise ClientError(
            "QA evidence is missing required viewport screenshots: "
            + ", ".join(f"{name}:{width}x{height}" for name, width, height in missing)
        )
    for stored in screenshots:
        if not isinstance(stored, dict):
            raise ClientError("QA screenshot evidence is not structured")
        current = client_evidence_artifact(
            layout,
            slug,
            str(layout.client(slug) / str(stored.get("path") or "")),
            suffixes={".png", ".jpg", ".jpeg", ".webp"},
        )
        if not hmac.compare_digest(
            str(current.get("sha256") or ""), str(stored.get("sha256") or "")
        ):
            raise ClientError("QA screenshot digest verification failed")
        if (
            int(current.get("width") or 0) != int(stored.get("width") or 0)
            or int(current.get("height") or 0) != int(stored.get("height") or 0)
        ):
            raise ClientError("QA screenshot stored dimensions do not match decoded dimensions")
    runtime = client_configs(layout, slug)["runtime.yaml"]
    browser_qa = runtime.get("browser_qa", {}) if isinstance(runtime, dict) else {}
    configured_viewports = browser_qa.get("viewports", []) if isinstance(browser_qa, dict) else []
    required_dimensions = {
        (int(item["width"]), int(item["height"]))
        for item in configured_viewports
        if isinstance(item, dict) and item.get("width") and item.get("height")
    }
    captured_dimensions = {
        (int(item.get("width") or 0), int(item.get("height") or 0))
        for item in screenshots
        if isinstance(item, dict)
    }
    missing_dimensions = sorted(required_dimensions - captured_dimensions)
    if required_dimensions and missing_dimensions:
        raise ClientError(
            "QA evidence is missing required viewport dimensions: "
            + ", ".join(f"{width}x{height}" for width, height in missing_dimensions)
        )
    steps = evidence.get("validation_steps", [])
    if (
        not isinstance(steps, list)
        or not steps
        or any(len(str(step).strip()) < 12 for step in steps)
    ):
        raise ClientError("QA validation steps are missing or incomplete")
    provenance = evidence.get("qa_browser_provenance", {})
    if not isinstance(provenance, dict) or not provenance.get("session_id"):
        raise ClientError("QA browser provenance is missing")
    report_stored = provenance.get("report", {})
    if not isinstance(report_stored, dict):
        raise ClientError("QA browser report evidence is not structured")
    report_artifact = client_evidence_artifact(
        layout,
        slug,
        str(layout.client(slug) / str(report_stored.get("path") or "")),
        suffixes={".json"},
    )
    if not hmac.compare_digest(
        str(report_artifact.get("sha256") or ""),
        str(report_stored.get("sha256") or ""),
    ):
        raise ClientError("QA browser report digest verification failed")
    report = yaml_document(layout.client(slug) / str(report_stored.get("path")))
    if (
        report.get("real_browser_navigation_succeeded") is not True
        or str(report.get("session_id") or "") != str(provenance.get("session_id"))
        or str(report.get("url") or "") != str(provenance.get("url") or "")
    ):
        raise ClientError("QA browser report no longer matches its provenance")
    profile_binding = validate_browser_qa_profile(layout, slug, report)
    if any(
        str(provenance.get(key) or "") != str(value)
        for key, value in profile_binding.items()
    ):
        raise ClientError("QA browser profile binding no longer matches its provenance")
    qa_receipt_expected = {
        "client": slug,
        "work_id": work_id,
        "actor": str(provenance.get("actor") or ""),
        "session_id": str(provenance.get("session_id") or ""),
        "session_source": str(provenance.get("source") or ""),
        **profile_binding,
        "url": str(provenance.get("url") or ""),
        "started_at": float(provenance.get("started_at") or 0),
        "finished_at": float(provenance.get("finished_at") or 0),
        "report_sha256": str(report_stored.get("sha256") or ""),
        "screenshot_sha256": sorted(
            str(item.get("sha256"))
            for item in screenshots
            if isinstance(item, dict)
        ),
        "validation_sha256": hashlib.sha256(
            json.dumps(steps, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
    }
    verify_qa_receipt(
        layout, str(provenance.get("receipt") or ""), qa_receipt_expected
    )
    current_session = verify_browser_session(
        layout,
        slug,
        str(provenance["session_id"]),
        url=str(provenance.get("url") or ""),
        started_at=float(provenance.get("started_at") or 0),
        finished_at=float(provenance.get("finished_at") or 0),
        profile_binding=profile_binding,
    )
    if str(current_session.get("source") or "") != str(provenance.get("source") or ""):
        raise ClientError("QA browser session source no longer matches its receipt")


def validate_browser_qa_profile(
    layout: Layout, slug: str, report: dict[str, Any]
) -> dict[str, Any]:
    runtime = client_configs(layout, slug)["runtime.yaml"]
    browser_qa = runtime.get("browser_qa", {}) if isinstance(runtime, dict) else {}
    if not isinstance(browser_qa, dict) or browser_qa.get("enabled") is not True:
        raise ClientError("authenticated browser QA is not enabled for this client")
    profile_id = str(report.get("browser_profile_id") or "")
    environment = str(report.get("environment") or "")
    role = str(report.get("role") or "")
    principal = str(report.get("authenticated_principal") or "")
    probe = str(report.get("authentication_probe_sha256") or "")
    profiles = browser_qa.get("profiles", [])
    match = next(
        (
            item
            for item in profiles
            if isinstance(item, dict)
            and str(item.get("id") or "") == profile_id
            and str(item.get("environment") or "") == environment
            and str(item.get("role") or "") == role
        ),
        None,
    ) if isinstance(profiles, list) else None
    configured_principal = str(match.get("authenticated_principal") or "") if isinstance(match, dict) else ""
    configured_probe = str(match.get("authentication_probe_sha256") or "") if isinstance(match, dict) else ""
    if (
        not isinstance(match, dict)
        or match.get("authenticated_verified") is not True
        or environment != "staging"
        or not principal
        or not configured_principal
        or not re.fullmatch(r"[a-fA-F0-9]{64}", probe)
        or not re.fullmatch(r"[a-fA-F0-9]{64}", configured_probe)
        or principal != configured_principal
        or probe.lower() != configured_probe.lower()
    ):
        raise ClientError("browser QA profile authentication is unverified or mismatched")
    return {
        "browser_profile_id": profile_id,
        "environment": environment,
        "role": role,
        "authenticated_principal": principal,
        "authentication_probe_sha256": probe.lower(),
    }


def update_evidence(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return update_evidence_locked(layout, args)


def update_evidence_locked(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    path, record = load_work(layout, args.slug, args.work_id)
    repository = record.setdefault("repository", {})
    evidence = record.setdefault("evidence", {})
    changed: list[str] = []
    if args.pull_request is not None:
        repository["pull_request"] = args.pull_request
        changed.append("pull_request")
    if args.commit is not None:
        repository["commit"] = args.commit
        changed.append("commit")
    for argument, key in (
        (getattr(args, "engineering_review", None), "engineering_review_passed"),
        (getattr(args, "ci", None), "ci_passed"),
        (getattr(args, "production_health", None), "production_health_verified"),
    ):
        if argument is not None:
            evidence[key] = argument == "passed"
            changed.append(key)
    security = getattr(args, "security", None)
    if security is not None:
        evidence["security_disposition"] = security
        changed.append("security_disposition")
    security_decision_id = getattr(args, "security_decision_id", None)
    if security_decision_id is not None:
        evidence["security_decision_id"] = security_decision_id
        changed.append("security_decision_id")
    if security == "not_required" and not evidence.get("security_decision_id"):
        raise ClientError("security not_required requires a decision id")
    if getattr(args, "preview", None) is not None:
        evidence["staging_preview"] = args.preview
        changed.append("staging_preview")
    if getattr(args, "staging_build", None) is not None:
        evidence["staging_build_version"] = args.staging_build
        changed.append("staging_build_version")
    screenshots = getattr(args, "screenshot", None) or []
    if screenshots:
        artifacts = [
            client_evidence_artifact(
                layout,
                args.slug,
                screenshot,
                suffixes={".png", ".jpg", ".jpeg", ".webp"},
            )
            for screenshot in screenshots
        ]
        runtime = client_configs(layout, args.slug)["runtime.yaml"]
        browser_qa = runtime.get("browser_qa", {}) if isinstance(runtime, dict) else {}
        viewport_by_size = {
            (int(item.get("width") or 0), int(item.get("height") or 0)): str(
                item.get("id") or ""
            )
            for item in browser_qa.get("viewports", [])
            if isinstance(item, dict)
        } if isinstance(browser_qa, dict) else {}
        for artifact in artifacts:
            viewport = viewport_by_size.get(
                (int(artifact.get("width") or 0), int(artifact.get("height") or 0))
            )
            if not viewport:
                raise ClientError("QA screenshot does not match a configured viewport")
            artifact["viewport"] = viewport
        evidence.setdefault("screenshots", []).extend(artifacts)
        changed.append("screenshots")
    validation_steps = getattr(args, "validation_step", None) or []
    if validation_steps:
        if any(len(str(step).strip()) < 12 for step in validation_steps):
            raise ClientError("QA validation steps must be explicit and bounded")
        evidence.setdefault("validation_steps", []).extend(validation_steps)
        changed.append("validation_steps")
    linear_attachment_values = getattr(args, "linear_attachment", None) or []
    if linear_attachment_values:
        structured = []
        for raw in linear_attachment_values:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ClientError("Linear attachment must be a JSON object") from error
            if not isinstance(item, dict):
                raise ClientError("Linear attachment must be a JSON object")
            structured.append(
                {
                    "title": str(item.get("title") or ""),
                    "subtitle": str(item.get("subtitle") or "AGK verified evidence"),
                    "url": str(item.get("url") or "").strip(),
                }
            )
        structured = validate_linear_attachments(structured)
        existing = validate_linear_attachments(
            evidence.get("linear_attachments", [])
        )
        existing_urls = {
            canonical_linear_attachment_url(
                urllib.parse.urlsplit(str(item.get("url") or ""))
            )
            for item in existing
        }
        evidence.setdefault("linear_attachments", []).extend(
            item
            for item in structured
            if canonical_linear_attachment_url(urllib.parse.urlsplit(item["url"]))
            not in existing_urls
        )
        changed.append("linear_attachments")
    browser_report = getattr(args, "browser_report", None)
    qa_session_id = str(getattr(args, "qa_session_id", None) or "")
    if browser_report is not None:
        report_artifact = client_evidence_artifact(
            layout, args.slug, browser_report, suffixes={".json"}
        )
        report_path = layout.client(args.slug) / report_artifact["path"]
        report = yaml_document(report_path)
        if (
            report.get("real_browser_navigation_succeeded") is not True
            or str(report.get("session_id") or "") != qa_session_id
            or str(report.get("work_id") or "") != args.work_id
            or str(report.get("actor") or "") != str(args.actor)
            or not str(report.get("url") or "").startswith(("http://", "https://"))
            or not str(report.get("page_title") or "").strip()
        ):
            raise ClientError("QA browser report is incomplete or inconsistent")
        try:
            started_at = float(report["started_at"])
            finished_at = float(report["finished_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise ClientError("QA browser report timestamps are invalid") from error
        profile_binding = validate_browser_qa_profile(layout, args.slug, report)
        provenance = verify_browser_session(
            layout,
            args.slug,
            qa_session_id,
            url=str(report["url"]),
            started_at=started_at,
            finished_at=finished_at,
            profile_binding=profile_binding,
        )
        evidence["qa_browser_provenance"] = {
            **provenance,
            **profile_binding,
            "work_id": args.work_id,
            "actor": str(args.actor),
            "url": report["url"],
            "page_title": report["page_title"],
            "report": report_artifact,
        }
        qa_receipt_payload = {
            "actor": str(args.actor),
            "session_id": qa_session_id,
            "session_source": str(provenance.get("source") or ""),
            **profile_binding,
            "url": str(report["url"]),
            "started_at": started_at,
            "finished_at": finished_at,
            "report_sha256": str(report_artifact["sha256"]),
            "screenshot_sha256": sorted(
                str(item.get("sha256"))
                for item in evidence.get("screenshots", [])
                if isinstance(item, dict)
            ),
            "validation_sha256": hashlib.sha256(
                json.dumps(
                    evidence.get("validation_steps", []),
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        }
        evidence["qa_browser_provenance"]["receipt"] = write_qa_receipt(
            layout, args.slug, args.work_id, qa_receipt_payload
        )
        changed.append("qa_browser_provenance")
    qa = getattr(args, "qa", None)
    if qa is not None:
        if qa == "passed":
            screenshots_record = evidence.get("screenshots", [])
            if (
                not screenshots_record
                or not all(
                    isinstance(item, dict) and item.get("path") and item.get("sha256")
                    for item in screenshots_record
                )
                or not evidence.get("validation_steps")
                or not evidence.get("qa_browser_provenance")
            ):
                raise ClientError(
                    "QA PASS requires verified screenshots, validation steps and browser provenance"
                )
            validate_qa_evidence(layout, args.slug, args.work_id, evidence)
            evidence["qa_passed"] = True
        else:
            evidence["qa_passed"] = False
        changed.append("qa_passed")
    if getattr(args, "rollback_plan", None) is not None:
        evidence["rollback_plan"] = args.rollback_plan
        changed.append("rollback_plan")
    if getattr(args, "risk", None) is not None:
        evidence["risk"] = args.risk
        changed.append("risk")
    if getattr(args, "linear_done", False):
        raise ClientError(
            "Linear Done is authoritative and cannot be supplied as agent evidence"
        )
    if not changed:
        raise ClientError("no evidence update was provided")
    work_event(record, "work.evidence_updated", actor=args.actor, fields=changed)
    atomic_yaml(path, record)
    return record


def request_changes(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    feedback = args.feedback.strip()
    if not feedback:
        raise ClientError("request changes requires non-empty feedback")
    path, record = load_work(layout, args.slug, args.work_id)
    current = str(record.get("status") or "")
    if current not in {"ready_for_cto", "cto_approved", "ready_to_deploy"}:
        raise ClientError(f"request changes is not valid from {current}")
    immutable = {
        "client_id": record.get("client_id"),
        "issue": record.get("linear", {}).get("issue"),
        "repo": record.get("repository", {}).get("repo"),
        "branch": record.get("repository", {}).get("branch"),
        "session": record.get("agent", {}).get("session"),
    }
    record["status"] = "in_progress"
    record["approvals"] = {"engineering": None, "production": None}
    work_event(
        record,
        "work.changes_requested",
        actor=args.actor,
        feedback=feedback,
        resumed_context=immutable,
    )
    atomic_yaml(path, record)
    return record


def require_release_controller_enabled(layout: Layout, slug: str) -> dict[str, Any]:
    integrations = client_configs(layout, slug)["integrations.yaml"]
    linear = integrations.get("linear", {}) if isinstance(integrations, dict) else {}
    controller = linear.get("release_controller", {}) if isinstance(linear, dict) else {}
    if not isinstance(controller, dict) or controller.get("enabled") is not True:
        raise ClientError(
            "release controller is disabled; production approval and deployment fail closed"
        )
    if controller.get("operational_acceptance_verified") is not True:
        raise ClientError(
            "release controller operational acceptance is incomplete; production remains blocked"
        )
    if controller.get("fail_closed") is not True:
        raise ClientError("release controller configuration is not fail-closed")
    if controller.get("merge_method") not in {"github_api", "merge_queue", "github_api_or_merge_queue"}:
        raise ClientError("release controller merge method is not governed")
    return controller


def write_production_authorization_receipt(
    layout: Layout,
    slug: str,
    work_id: str,
    *,
    kind: str,
    payload: dict[str, Any],
) -> str:
    if kind not in {"engineering", "production"}:
        raise ClientError("release authorization receipt kind is invalid")
    signed_payload = {
        "schema_version": 1,
        "client": validate_slug(slug),
        "work_id": work_id,
        "kind": kind,
        **payload,
    }
    canonical = json.dumps(
        signed_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    receipt = {
        **signed_payload,
        "signature": hmac.new(
            control_plane_audit_key(layout), canonical.encode(), hashlib.sha256
        ).hexdigest(),
    }
    approval_id = str(payload.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", approval_id):
        raise ClientError("release authorization id is invalid")
    relative = (
        Path("audit") / "release-authorizations" / validate_slug(slug)
        / f"{work_id}.{kind}.{hashlib.sha256(approval_id.encode()).hexdigest()[:16]}.json"
    )
    path = layout.system / relative
    if path.exists():
        existing = yaml_document(path)
        if existing != receipt:
            raise ClientError("immutable release authorization receipt already exists")
        return str(relative)
    atomic_text(
        path,
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        0o400,
    )
    return str(relative)


def verify_production_authorization_receipt(
    layout: Layout,
    slug: str,
    work_id: str,
    *,
    kind: str,
    approval: dict[str, Any],
) -> None:
    if kind not in {"engineering", "production"} or not isinstance(approval, dict):
        raise ClientError("release authorization is invalid")
    relative = Path(str(approval.get("receipt") or ""))
    path = (layout.system / relative).resolve()
    try:
        path.relative_to(layout.system.resolve())
    except ValueError as error:
        raise ClientError("release authorization receipt must stay inside the control plane") from error
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o777 != 0o400:
        raise ClientError("immutable release authorization receipt is unavailable")
    observed = yaml_document(path)
    signature = str(observed.pop("signature", ""))
    expected = {
        "schema_version": 1,
        "client": validate_slug(slug),
        "work_id": work_id,
        "kind": kind,
        **{key: value for key, value in approval.items() if key != "receipt"},
    }
    if observed != expected:
        raise ClientError("release authorization receipt does not match the work record")
    canonical = json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    calculated = hmac.new(control_plane_audit_key(layout), canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, calculated):
        raise ClientError("release authorization receipt signature is invalid")


def approval_matches_current_head(record: dict[str, Any], approval: dict[str, Any]) -> bool:
    repository = record.get("repository", {})
    return (
        isinstance(repository, dict)
        and approval.get("issue") == record.get("linear", {}).get("issue")
        and approval.get("pull_request") == repository.get("pull_request")
        and approval.get("head_sha") == repository.get("commit")
        and bool(approval.get("pull_request"))
        and bool(approval.get("head_sha"))
    )


def approve_work(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    require_release_controller_enabled(layout, args.slug)
    path, record = load_work(layout, args.slug, args.work_id)
    existing = record.get("approvals", {}).get("engineering", {})
    if record.get("status") == "cto_approved" and isinstance(existing, dict):
        if existing.get("id") == args.approval_id:
            if not approval_matches_current_head(record, existing):
                raise ClientError("approved engineering head no longer matches the current PR head")
            verify_production_authorization_receipt(
                layout, args.slug, args.work_id, kind="engineering", approval=existing
            )
            return record
        raise ClientError("a different engineering approval is already recorded")
    if record.get("status") != "ready_for_cto":
        raise ClientError("engineering approval requires READY_FOR_CTO")
    approval = {
        "id": args.approval_id,
        "actor": validate_name(args.actor),
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issue": record.get("linear", {}).get("issue"),
        "pull_request": record.get("repository", {}).get("pull_request"),
        "head_sha": record.get("repository", {}).get("commit"),
    }
    if not approval["pull_request"] or not approval["head_sha"]:
        raise ClientError("engineering approval requires an exact PR and head SHA")
    approval["receipt"] = write_production_authorization_receipt(
        layout, args.slug, args.work_id, kind="engineering", payload=approval
    )
    record.setdefault("approvals", {})["engineering"] = approval
    record["status"] = "cto_approved"
    work_event(record, "work.engineering_approved", **approval)
    atomic_yaml(path, record)
    return record


def authorize_deploy(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    require_release_controller_enabled(layout, args.slug)
    path, record = load_work(layout, args.slug, args.work_id)
    existing_production = record.get("approvals", {}).get("production", {})
    if record.get("status") == "ready_to_deploy" and isinstance(existing_production, dict):
        if existing_production.get("id") == args.approval_id:
            if not approval_matches_current_head(record, existing_production):
                raise ClientError("approved production head no longer matches the current PR head")
            verify_production_authorization_receipt(
                layout, args.slug, args.work_id, kind="production", approval=existing_production
            )
            return record
        raise ClientError("a different production authorization is already recorded")
    if record.get("status") != "cto_approved":
        raise ClientError("deployment authorization requires CTO_APPROVED")
    engineering = record.get("approvals", {}).get("engineering", {})
    if not isinstance(engineering, dict) or not engineering.get("id"):
        raise ClientError("deployment authorization requires an engineering approval")
    if not approval_matches_current_head(record, engineering):
        raise ClientError("engineering approval does not match the current PR head")
    verify_production_authorization_receipt(
        layout, args.slug, args.work_id, kind="engineering", approval=engineering
    )
    if args.approval_id == engineering.get("id"):
        raise ClientError(
            "deployment authorization must be separate from engineering approval"
        )
    approval = {
        "id": args.approval_id,
        "actor": validate_name(args.actor),
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issue": record.get("linear", {}).get("issue"),
        "pull_request": record.get("repository", {}).get("pull_request"),
        "head_sha": record.get("repository", {}).get("commit"),
        "engineering_approval_id": engineering.get("id"),
    }
    approval["receipt"] = write_production_authorization_receipt(
        layout, args.slug, args.work_id, kind="production", payload=approval
    )
    record.setdefault("approvals", {})["production"] = approval
    record["status"] = "ready_to_deploy"
    work_event(record, "work.production_authorized", **approval)
    atomic_yaml(path, record)
    return record


def apply_review_action(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    match = re.fullmatch(
        r"agk:review:([a-z0-9][a-z0-9-]{1,48}[a-z0-9]):"
        r"(WORK-[A-F0-9]{12}):(changes|approve|deploy)",
        args.custom_id,
    )
    if not match:
        raise ClientError("invalid AGK Discord review action")
    slug, work_id, action = match.groups()
    actor = validate_name(args.actor)
    decision_id = str(args.decision_id or "").strip()
    if not decision_id or len(decision_id) > 100:
        raise ClientError("review action requires a bounded Discord interaction id")
    with work_lock(layout, slug, work_id):
        return apply_review_action_locked(
            layout, args, slug, work_id, action, actor, decision_id
        )


def apply_review_action_locked(
    layout: Layout,
    args: argparse.Namespace,
    slug: str,
    work_id: str,
    action: str,
    actor: str,
    decision_id: str,
) -> dict[str, Any]:
    if action == "approve":
        record = approve_work(
            layout,
            argparse.Namespace(
                slug=slug,
                work_id=work_id,
                approval_id=decision_id,
                actor=actor,
            ),
        )
        return {
            "action": action,
            "client_id": slug,
            "work_id": work_id,
            "status": record["status"],
        }
    if action == "changes":
        record = request_changes(
            layout,
            argparse.Namespace(
                slug=slug,
                work_id=work_id,
                feedback=args.feedback or "",
                actor=actor,
            ),
        )
        result = {
            "action": action,
            "client_id": slug,
            "work_id": work_id,
            "status": record["status"],
            "session_resumed": False,
        }
        if record.get("agent", {}).get("runtime_id"):
            try:
                resume_work_session(
                    layout,
                    argparse.Namespace(
                        slug=slug,
                        work_id=work_id,
                        feedback=args.feedback,
                    ),
                )
                result["session_resumed"] = True
            except ClientError as error:
                result["session_resume_error"] = str(error)
        return result

    require_release_controller_enabled(layout, slug)
    path, record = load_work(layout, slug, work_id)
    if record.get("status") != "ready_to_deploy":
        raise ClientError("DEPLOY requires READY_TO_DEPLOY")
    existing = record.get("deployment_request", {})
    if isinstance(existing, dict) and existing.get("id"):
        if existing.get("id") != decision_id:
            raise ClientError("a production deployment request is already queued")
        return {
            "action": action,
            "client_id": slug,
            "work_id": work_id,
            "status": "queued",
            "created": False,
        }
    request = {
        "id": decision_id,
        "actor": actor,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    record["deployment_request"] = request
    work_event(record, "work.production_deploy_requested", **request)
    atomic_yaml(path, record)
    return {
        "action": action,
        "client_id": slug,
        "work_id": work_id,
        "status": "queued",
        "created": True,
    }


def review_card(
    record: dict[str, Any], *, release_controller_enabled: bool = False
) -> dict[str, Any]:
    evidence = record.get("evidence", {})
    repo = record.get("repository", {})
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🛠 CTO REVIEW · {str(record.get('client_id')).upper()}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{record.get('linear', {}).get('issue')} · {record.get('title')}",
        f"Agent · {record.get('agent', {}).get('role')}",
        f"Session · {record.get('agent', {}).get('session')}",
        f"PR · {repo.get('pull_request') or 'pending'}",
        f"CI · {'PASS' if evidence.get('ci_passed') else 'PENDING'}",
        f"QA · {'PASS' if evidence.get('qa_passed') else 'PENDING'}",
        f"Security · {'PASS' if evidence.get('security_disposition') == 'passed' else 'NOT REQUIRED' if evidence.get('security_disposition') == 'not_required' else 'PENDING'}",
        f"Risk · {evidence.get('risk') or 'unrated'}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    prefix = f"agk:review:{record.get('client_id')}:{record.get('id')}"
    buttons = [
        {
            "label": "OPEN PREVIEW",
            "style": "link",
            "url": evidence.get("staging_preview"),
        },
        {
            "label": "REQUEST CHANGES",
            "style": "danger",
            "custom_id": prefix + ":changes",
        },
    ]
    if release_controller_enabled and record.get("status") == "ready_for_cto":
        buttons.append(
            {"label": "APPROVE", "style": "success", "custom_id": prefix + ":approve"}
        )
    if release_controller_enabled and record.get("status") == "ready_to_deploy":
        buttons.append(
            {"label": "DEPLOY", "style": "primary", "custom_id": prefix + ":deploy"}
        )
    return {
        "content": "\n".join(lines),
        "buttons": [
            button for button in buttons if button.get("url") or "url" not in button
        ],
    }


def discord_review_plan(layout: Layout, slug: str, work_id: str) -> dict[str, Any]:
    _, work = load_work(layout, slug, work_id)
    if work.get("status") not in {"ready_for_cto", "ready_to_deploy"}:
        raise ClientError(
            "Discord review cards require READY_FOR_CTO or READY_TO_DEPLOY"
        )
    integrations = client_configs(layout, slug)["integrations.yaml"]
    discord = integrations.get("discord", {})
    if not isinstance(discord, dict) or not discord.get("enabled"):
        raise ClientError("Discord is not enabled for this client")
    channels = discord.get("channels", {})
    channel_key = "cto_inbox" if work.get("status") == "ready_for_cto" else "releases"
    channel_id = channels.get(channel_key) if isinstance(channels, dict) else None
    linear = integrations.get("linear", {}) if isinstance(integrations, dict) else {}
    controller = linear.get("release_controller", {}) if isinstance(linear, dict) else {}
    card = review_card(
        work,
        release_controller_enabled=(
            isinstance(controller, dict) and controller.get("enabled") is True
        ),
    )
    revision = sum(
        1
        for event in work.get("events", [])
        if isinstance(event, dict) and event.get("event") == "work.changes_requested"
    )
    return {
        "client_id": slug,
        "work_id": work_id,
        "account_alias": discord.get("account_alias"),
        "channel": channel_key,
        "channel_id": channel_id,
        "revision": revision,
        "card": card,
        "external_writes": True,
        "idempotent": True,
    }


def discord_components(card: dict[str, Any]) -> list[dict[str, Any]]:
    style_codes = {"primary": 1, "success": 3, "danger": 4, "link": 5}
    components = []
    for button in card.get("buttons", []):
        if not isinstance(button, dict):
            continue
        style = str(button.get("style") or "")
        item: dict[str, Any] = {
            "type": 2,
            "style": style_codes.get(style, 2),
            "label": str(button.get("label") or "Action")[:80],
        }
        if style == "link":
            item["url"] = button.get("url")
        else:
            custom_id = str(button.get("custom_id") or "")
            if not custom_id or len(custom_id) > 100:
                raise ClientError("Discord review button custom_id is invalid")
            item["custom_id"] = custom_id
        components.append(item)
    if len(components) > 5:
        raise ClientError("Discord review card exceeds one action row")
    return [{"type": 1, "components": components}] if components else []


def discord_review_apply(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError(
            "Discord review delivery requires --yes after reviewing the plan"
        )
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return discord_review_apply_locked(layout, args, slug)


def discord_review_apply_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    plan = discord_review_plan(layout, slug, args.work_id)
    account = str(plan["account_alias"] or "")
    channel_id = str(plan["channel_id"] or "")
    if not account:
        raise ClientError("Discord Composio account alias is not configured")
    if not channel_id.isdigit():
        raise ClientError(f"Discord #{plan['channel']} channel is not provisioned")
    path, work = load_work(layout, slug, args.work_id)
    delivery = work.get("discord_review", {})
    if (
        isinstance(delivery, dict)
        and delivery.get("message_id")
        and str(delivery.get("channel_id") or "") == channel_id
        and delivery.get("status") == work.get("status")
        and delivery.get("revision") == plan["revision"]
    ):
        return {
            "client_id": slug,
            "work_id": args.work_id,
            "channel_id": channel_id,
            "message_id": delivery["message_id"],
            "created": False,
        }

    card = plan["card"]
    payload = {
        "content": card["content"],
        "components": discord_components(card),
        "allowed_mentions": {"parse": []},
    }
    value = composio_proxy(
        "POST",
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        account,
        payload,
    )
    if not isinstance(value, dict) or not str(value.get("id") or "").isdigit():
        raise ClientError("Discord review delivery returned no message id")
    message_id = str(value["id"])
    try:
        work["discord_review"] = {
            "channel": plan["channel"],
            "channel_id": channel_id,
            "message_id": message_id,
            "status": work.get("status"),
            "revision": plan["revision"],
            "sent_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        work_event(work, "work.discord_review_sent", message_id=message_id)
        atomic_yaml(path, work)
    except Exception as error:
        try:
            composio_proxy(
                "DELETE",
                f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
                account,
            )
        except ClientError as rollback_error:
            raise ClientError(
                f"Discord review local commit failed; message rollback also failed: {rollback_error}"
            ) from error
        raise ClientError(
            "Discord review local commit failed and message was rolled back"
        ) from error
    return {
        "client_id": slug,
        "work_id": args.work_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "created": True,
    }


def start_run(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return start_run_locked(layout, args, slug)


def start_run_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    _, work = load_work(layout, slug, args.work_id)
    permissions = client_configs(layout, slug)["permissions.yaml"].get("actions", {})
    policy = permissions.get(args.action, {}) if isinstance(permissions, dict) else {}
    if not isinstance(policy, dict) or not policy:
        raise ClientError(f"unknown governed action: {args.action}")
    if (
        policy.get("agent_allowed") is False
        or policy.get("human_approval") == "forbidden"
    ):
        raise ClientError(f"action is forbidden by client policy: {args.action}")
    if policy.get("issue_required") and not work.get("linear", {}).get("issue"):
        raise ClientError("governed action requires a Linear issue")
    if policy.get("human_approval") == "required" and not args.approval_id:
        raise ClientError(f"action requires human approval: {args.action}")
    if args.action == "deploy_production":
        require_release_controller_enabled(layout, slug)
        production = work.get("approvals", {}).get("production", {})
        if work.get(
            "status"
        ) != "ready_to_deploy" or args.approval_id != production.get("id"):
            raise ClientError(
                "production deploy requires its recorded deployment authorization"
            )
        expected_commit = str(work.get("repository", {}).get("commit") or "")
        if not expected_commit or args.commit != expected_commit:
            raise ClientError("production deploy commit differs from the approved PR head")
        engineering = work.get("approvals", {}).get("engineering", {})
        if (
            not isinstance(engineering, dict)
            or not isinstance(production, dict)
            or not approval_matches_current_head(work, engineering)
            or not approval_matches_current_head(work, production)
        ):
            raise ClientError("production deploy approvals do not match the current PR head")
        verify_production_authorization_receipt(
            layout, slug, args.work_id, kind="engineering", approval=engineering
        )
        verify_production_authorization_receipt(
            layout, slug, args.work_id, kind="production", approval=production
        )
        run_dir = layout.client(slug) / "state" / "runs"
        for candidate in run_dir.glob("RUN-*.yaml"):
            existing = yaml_document(candidate)
            if (
                existing.get("work_id") == args.work_id
                and existing.get("action") == "deploy_production"
                and existing.get("status") == "running"
            ):
                raise ClientError("a production Run is already active for this work")
    run_id = "RUN-" + uuid.uuid4().hex[:12].upper()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": run_id,
        "client_id": slug,
        "work_id": args.work_id,
        "linear_issue": work.get("linear", {}).get("issue"),
        "action": args.action,
        "policy_level": policy.get("level"),
        "actor": args.actor,
        "machine": args.machine,
        "commit": args.commit,
        "before": args.before,
        "after": args.after,
        "approval_id": args.approval_id,
        "rollback_available": args.rollback_available,
        "status": "running",
        "result": None,
        "started_at": now,
        "finished_at": None,
        "evidence": [],
    }
    path = layout.client(slug) / "state" / "runs" / f"{run_id}.yaml"
    atomic_yaml(path, record)
    return record


def complete_run(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    if not re.fullmatch(r"RUN-[A-F0-9]{12}", args.run_id):
        raise ClientError("invalid AGK run id")
    with client_lock(layout, slug, args.run_id):
        return complete_run_locked(layout, args, slug)


def complete_run_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    path = layout.client(slug) / "state" / "runs" / f"{args.run_id}.yaml"
    record = yaml_document(path)
    if record.get("status") != "running":
        raise ClientError("only a running AGK Run can be completed")
    if record.get("client_id") != slug:
        raise ClientError("AGK Run belongs to a different client boundary")

    production_success = (
        record.get("action") == "deploy_production" and args.result == "success"
    )
    context = (
        work_lock(layout, slug, str(record.get("work_id")))
        if production_success
        else contextlib.nullcontext()
    )
    with context:
        work_path: Path | None = None
        work: dict[str, Any] | None = None
        if production_success:
            work_path, work = load_work(layout, slug, str(record.get("work_id")))
            if work.get("status") != "ready_to_deploy":
                raise ClientError("production Run completed outside READY_TO_DEPLOY")

        record["status"] = "completed" if args.result == "success" else "failed"
        record["result"] = args.result
        record["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        record["evidence"] = args.evidence
        atomic_yaml(path, record)
        if work_path is not None and work is not None:
            work["status"] = "production"
            work_event(
                work,
                "work.production_deployed",
                run_id=record.get("id"),
                machine=record.get("machine"),
                commit=record.get("commit"),
            )
            atomic_yaml(work_path, work)
    return record


def verify_linear_webhook(
    raw_body: bytes,
    signature: str,
    secret: str,
    *,
    now_ms: int | None = None,
    replay_window_seconds: int = 60,
) -> dict[str, Any]:
    if not secret:
        raise ClientError("Linear webhook secret is unavailable")
    try:
        received = bytes.fromhex(signature)
    except ValueError as error:
        raise ClientError("Linear-Signature is not valid hexadecimal") from error
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    if not hmac.compare_digest(received, expected):
        raise ClientError("Linear webhook signature is invalid")
    try:
        payload = json.loads(raw_body)
        timestamp = int(payload["webhookTimestamp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ClientError("Linear webhook timestamp is missing or invalid") from error
    current = int(time.time() * 1000) if now_ms is None else now_ms
    if abs(current - timestamp) > replay_window_seconds * 1000:
        raise ClientError("Linear webhook is outside the replay window")
    return payload


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def list_clients(layout: Layout) -> list[dict[str, Any]]:
    registry = load_registry(layout)
    return [item for item in registry["clients"] if isinstance(item, dict)]


def command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agk client")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap_cmd = commands.add_parser("bootstrap")
    bootstrap_cmd.add_argument("--upgrade", action="store_true")
    init = commands.add_parser("init", aliases=["provision"])
    init.add_argument("slug")
    init.add_argument("--name", required=True)
    init.add_argument(
        "--runtime",
        choices=("local", "vps", "hybrid", "cloud", "external"),
        default="local",
    )
    init.add_argument(
        "--github-mode",
        choices=("dedicated", "org", "app", "token", "deploy-key", "none"),
        default="none",
    )
    init.add_argument("--github-org")
    init.add_argument("--linear-workspace")
    init.add_argument("--linear-team")
    init.add_argument("--vercel", action="store_true")
    init.add_argument("--convex", action="store_true")
    init.add_argument("--google-drive", action="store_true")
    init.add_argument(
        "--discord-mode",
        choices=("shared-command-center", "dedicated-bot"),
        default="dedicated-bot",
    )
    init.add_argument("--discord-guild")
    init.add_argument("--dry-run", action="store_true")
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("slug")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("slug", nargs="?")
    doctor.add_argument("--online", action="store_true")
    env = commands.add_parser("env")
    env.add_argument("slug")
    activate = commands.add_parser("activate")
    activate.add_argument("slug")
    activate.add_argument("--yes", action="store_true")
    integrations = commands.add_parser("integrations")
    integrations.add_argument("action", choices=("plan", "verify"))
    integrations.add_argument("slug")
    linear = commands.add_parser("linear")
    linear.add_argument("action", choices=("plan", "apply"))
    linear.add_argument("slug")
    linear.add_argument("work_id")
    linear.add_argument("--yes", action="store_true")
    discord = commands.add_parser("discord")
    discord.add_argument(
        "action", choices=("plan", "apply", "review-plan", "review-apply")
    )
    discord.add_argument("slug")
    discord.add_argument("work_id", nargs="?")
    discord.add_argument("--yes", action="store_true")

    work = commands.add_parser("work")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    work_create = work_sub.add_parser("create")
    work_create.add_argument("slug")
    work_create.add_argument("--issue", required=True)
    work_create.add_argument("--title", required=True)
    work_create.add_argument("--role", required=True)
    work_create.add_argument(
        "--provider",
        choices=("hermes", "codex", "claude", "opencode", "openrouter"),
        default="hermes",
    )
    work_create.add_argument("--repo", required=True)
    work_create.add_argument("--branch")
    work_create.add_argument("--session")
    work_create.add_argument(
        "--target",
        choices=("development", "staging", "production"),
        default="development",
    )
    context_cmd = work_sub.add_parser("context")
    context_cmd.add_argument("slug")
    context_cmd.add_argument("work_id")
    context_cmd.add_argument("--actor", required=True)
    context_cmd.add_argument("--context-file", required=True)
    authorize_start = work_sub.add_parser("authorize-start")
    authorize_start.add_argument("slug")
    authorize_start.add_argument("work_id")
    authorize_start.add_argument("--channel-id", required=True)
    authorize_start.add_argument("--message-id", required=True)
    authorize_batch = work_sub.add_parser("authorize-batch")
    authorize_batch.add_argument("slug")
    authorize_batch.add_argument("--channel-id", required=True)
    authorize_batch.add_argument("--message-id", required=True)
    authorize_batch.add_argument("--yes", action="store_true")
    quarantine = work_sub.add_parser("quarantine-legacy")
    quarantine.add_argument("slug")
    quarantine.add_argument("work_id")
    quarantine.add_argument("--actor", required=True)
    quarantine.add_argument("--reason", required=True)
    transition = work_sub.add_parser("transition")
    transition.add_argument("slug")
    transition.add_argument("work_id")
    transition.add_argument("target")
    transition.add_argument("--actor", required=True)
    block = work_sub.add_parser("block")
    block.add_argument("slug")
    block.add_argument("work_id")
    block.add_argument("--actor", required=True)
    block.add_argument("--blocked-by", required=True)
    block.add_argument("--already-tried", required=True)
    block.add_argument("--impact", required=True)
    block.add_argument("--need", required=True)
    block.add_argument("--resume", required=True)
    block.add_argument("--no-useful-next-action", action="store_true")
    unblock = work_sub.add_parser("unblock")
    unblock.add_argument("slug")
    unblock.add_argument("work_id")
    unblock.add_argument("--actor", required=True)
    unblock.add_argument("--result", required=True)
    changes = work_sub.add_parser("request-changes")
    changes.add_argument("slug")
    changes.add_argument("work_id")
    changes.add_argument("--feedback", required=True)
    changes.add_argument("--actor", required=True)
    evidence = work_sub.add_parser("evidence")
    evidence.add_argument("slug")
    evidence.add_argument("work_id")
    evidence.add_argument("--actor", required=True)
    evidence.add_argument("--pull-request")
    evidence.add_argument("--commit")
    evidence.add_argument("--engineering-review", choices=("passed", "failed"))
    evidence.add_argument("--ci", choices=("passed", "failed"))
    evidence.add_argument("--qa", choices=("passed", "failed"))
    evidence.add_argument("--security", choices=("passed", "failed", "not_required"))
    evidence.add_argument("--security-decision-id")
    evidence.add_argument("--preview")
    evidence.add_argument("--staging-build")
    evidence.add_argument("--screenshot", action="append", default=[])
    evidence.add_argument("--validation-step", action="append", default=[])
    evidence.add_argument(
        "--linear-attachment",
        action="append",
        default=[],
        help='Repeatable JSON: {"title":"Mobile QA","url":"https://..."}',
    )
    evidence.add_argument("--browser-report")
    evidence.add_argument("--qa-session-id")
    evidence.add_argument("--rollback-plan")
    evidence.add_argument("--risk", choices=("low", "medium", "high", "critical"))
    evidence.add_argument("--production-health", choices=("passed", "failed"))
    evidence.add_argument("--linear-done", action="store_true")
    approve = work_sub.add_parser("approve")
    approve.add_argument("slug")
    approve.add_argument("work_id")
    approve.add_argument("--approval-id", required=True)
    approve.add_argument("--actor", required=True)
    deploy = work_sub.add_parser("authorize-deploy")
    deploy.add_argument("slug")
    deploy.add_argument("work_id")
    deploy.add_argument("--approval-id", required=True)
    deploy.add_argument("--actor", required=True)
    card = work_sub.add_parser("review-card")
    card.add_argument("slug")
    card.add_argument("work_id")
    review_action = work_sub.add_parser("review-action")
    review_action.add_argument("custom_id")
    review_action.add_argument("--actor", required=True)
    review_action.add_argument("--decision-id", required=True)
    review_action.add_argument("--feedback")
    work_show = work_sub.add_parser("show")
    work_show.add_argument("slug")
    work_show.add_argument("work_id")
    work_start = work_sub.add_parser("start")
    work_start.add_argument("slug")
    work_start.add_argument("work_id")
    work_resume = work_sub.add_parser("resume")
    work_resume.add_argument("slug")
    work_resume.add_argument("work_id")
    work_resume.add_argument("--feedback")

    run_cmd = commands.add_parser("run")
    run_sub = run_cmd.add_subparsers(dest="run_command", required=True)
    run_start = run_sub.add_parser("start")
    run_start.add_argument("slug")
    run_start.add_argument("work_id")
    run_start.add_argument("--action", required=True)
    run_start.add_argument("--actor", required=True)
    run_start.add_argument("--machine", required=True)
    run_start.add_argument("--commit", required=True)
    run_start.add_argument("--before")
    run_start.add_argument("--after")
    run_start.add_argument("--approval-id")
    run_start.add_argument("--rollback-available", action="store_true")
    run_complete = run_sub.add_parser("complete")
    run_complete.add_argument("slug")
    run_complete.add_argument("run_id")
    run_complete.add_argument("--result", choices=("success", "failure"), required=True)
    run_complete.add_argument("--evidence", action="append", default=[])

    webhook = commands.add_parser("verify-linear-webhook")
    webhook.add_argument("--body", type=Path, required=True)
    webhook.add_argument("--signature", required=True)
    webhook.add_argument("--secret-env", default="LINEAR_WEBHOOK_SECRET")
    webhook.add_argument("--now-ms", type=int)
    webhook.add_argument("--replay-window", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = command_parser()
    args = parser.parse_args(argv)
    layout = Layout.current()
    try:
        if args.command == "bootstrap":
            bootstrap(layout, upgrade=args.upgrade)
            print_json(
                {
                    "status": "ready",
                    "workspace": str(layout.workspace),
                    "clients": len(list_clients(layout)),
                }
            )
            return 0
        if args.command in {"init", "provision"}:
            print_json(create_client(layout, args))
            return 0
        if args.command == "list":
            print_json(list_clients(layout))
            return 0
        if args.command == "show":
            print_json(client_configs(layout, validate_slug(args.slug)))
            return 0
        if args.command == "doctor":
            return show_doctor(layout, args.slug, args.online)
        if args.command == "env":
            slug = validate_slug(args.slug)
            active = os.environ.get("AGK_CLIENT")
            if active and active != slug:
                raise ClientError(
                    f"client {active} is already loaded; open a new shell"
                )
            secret = layout.secret_file(slug)
            if not secret.is_file() or (secret.stat().st_mode & 0o777) != 0o600:
                raise ClientError(f"client secret store is missing or unsafe: {secret}")
            sys.stdout.write(secret.read_text(encoding="utf-8"))
            return 0
        if args.command == "activate":
            print_json(activate_client(layout, args))
            return 0
        if args.command == "integrations":
            if args.action == "plan":
                print_json(integration_plan(layout, validate_slug(args.slug)))
                return 0
            checks = composio_checks(
                client_configs(layout, args.slug)["integrations.yaml"]
            )
            print_json(
                {
                    "client_id": args.slug,
                    "checks": [
                        {"status": level, "message": message}
                        for level, message in checks
                    ],
                }
            )
            return 1 if any(level == "fail" for level, _ in checks) else 0
        if args.command == "linear":
            print_json(
                linear_sync_plan(layout, validate_slug(args.slug), args.work_id)
                if args.action == "plan"
                else linear_sync_apply(layout, args)
            )
            return 0
        if args.command == "discord":
            if args.action == "plan":
                print_json(discord_plan(layout, validate_slug(args.slug)))
            elif args.action == "apply":
                print_json(discord_apply(layout, args))
            else:
                if not args.work_id:
                    raise ClientError(f"Discord {args.action} requires an AGK work id")
                print_json(
                    discord_review_plan(layout, validate_slug(args.slug), args.work_id)
                    if args.action == "review-plan"
                    else discord_review_apply(layout, args)
                )
            return 0
        if args.command == "work":
            if args.work_command == "create":
                print_json(create_work(layout, args))
            elif args.work_command == "context":
                print_json(update_work_context(layout, args))
            elif args.work_command == "authorize-start":
                print_json(authorize_work_start(layout, args))
            elif args.work_command == "authorize-batch":
                print_json(authorize_linear_batch(layout, args))
            elif args.work_command == "quarantine-legacy":
                print_json(
                    quarantine_legacy_work(
                        layout,
                        args.slug,
                        args.work_id,
                        actor=args.actor,
                        reason=args.reason,
                    )
                )
            elif args.work_command == "transition":
                print_json(
                    transition_work(
                        layout, args.slug, args.work_id, args.target, actor=args.actor
                    )
                )
            elif args.work_command == "block":
                print_json(block_work(layout, args))
            elif args.work_command == "unblock":
                print_json(unblock_work(layout, args))
            elif args.work_command == "request-changes":
                print_json(request_changes(layout, args))
            elif args.work_command == "evidence":
                print_json(update_evidence(layout, args))
            elif args.work_command == "approve":
                print_json(approve_work(layout, args))
            elif args.work_command == "authorize-deploy":
                print_json(authorize_deploy(layout, args))
            elif args.work_command == "review-card":
                _, record = load_work(layout, args.slug, args.work_id)
                print_json(review_card(record))
            elif args.work_command == "review-action":
                print_json(apply_review_action(layout, args))
            elif args.work_command == "start":
                print_json(start_work_session(layout, args.slug, args.work_id))
            elif args.work_command == "resume":
                print_json(resume_work_session(layout, args))
            else:
                _, record = load_work(layout, args.slug, args.work_id)
                print_json(record)
            return 0
        if args.command == "run":
            print_json(
                start_run(layout, args)
                if args.run_command == "start"
                else complete_run(layout, args)
            )
            return 0
        if args.command == "verify-linear-webhook":
            payload = verify_linear_webhook(
                args.body.read_bytes(),
                args.signature,
                os.environ.get(args.secret_env, ""),
                now_ms=args.now_ms,
                replay_window_seconds=args.replay_window,
            )
            print_json(
                {
                    "verified": True,
                    "type": payload.get("type"),
                    "action": payload.get("action"),
                }
            )
            return 0
    except (ClientError, OSError, subprocess.SubprocessError) as error:
        print(f"AGK client error: {error}", file=sys.stderr)
        return 1
    parser.error("unhandled client command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
