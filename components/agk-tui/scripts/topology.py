#!/usr/bin/env python3
"""Non-destructive AGK profile-to-runtime topology manager."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml


PROFILE_IDS = ("operator", "agentik", "mission", "private")
CLIENT_LAYOUT = (
    ".client", "projects", "missions", "knowledge", "artifacts",
    "infrastructure", "automation",
)


def status_cache_path() -> Path:
    return Path(os.environ.get("AGK_TOPOLOGY_STATUS", "/var/lib/agk-terminal/topology-status.json"))


def default_config_path() -> Path:
    override = os.environ.get("AGK_TOPOLOGY")
    if override:
        return Path(override).expanduser()
    system = Path("/etc/agk-terminal/topology.yaml")
    if system.is_file():
        return system
    root = Path(os.environ.get("AGK_TERMINAL_ROOT", "/usr/local/lib/agk-terminal"))
    installed = root / "config/topology.yaml"
    if installed.is_file():
        return installed
    return Path(__file__).resolve().parents[1] / "config/topology.yaml"


def safe_path(value: object, *, label: str) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute() or path in {Path("/"), Path("/home"), Path("/opt")}:
        raise ValueError(f"{label} must be a specific absolute path")
    return path


@dataclass(frozen=True)
class Profile:
    profile_id: str
    display_name: str
    linux_user: str
    workspace: Path
    hermes_home: Path
    rmux_scope: str
    workspace_layout: tuple[str, ...]
    client_layout: tuple[str, ...]

    @classmethod
    def parse(cls, profile_id: str, raw: dict[str, object]) -> "Profile":
        runtime = raw.get("runtime") or {}
        if not isinstance(runtime, dict) or runtime.get("driver") != "linux-user":
            raise ValueError(f"profile {profile_id} needs runtime.driver=linux-user")
        linux_user = str(runtime.get("linux_user") or "")
        if not linux_user:
            raise ValueError(f"profile {profile_id} has no runtime linux_user")
        workspace = safe_path(raw.get("workspace"), label=f"{profile_id}.workspace")
        hermes_home = safe_path(raw.get("hermes_home"), label=f"{profile_id}.hermes_home")
        expected_home = Path(pwd.getpwnam(linux_user).pw_dir) if user_exists(linux_user) else None
        for label, path in (("workspace", workspace), ("hermes_home", hermes_home)):
            if expected_home and path != expected_home and expected_home not in path.parents:
                raise ValueError(f"profile {profile_id} {label} escapes {linux_user}'s home")
        layout = tuple(str(item) for item in raw.get("workspace_layout") or ())
        client_layout = tuple(str(item) for item in raw.get("client_layout") or ())
        for child in (*layout, *client_layout):
            if not child or Path(child).is_absolute() or ".." in Path(child).parts:
                raise ValueError(f"profile {profile_id} has unsafe layout entry: {child!r}")
        return cls(
            profile_id=profile_id,
            display_name=str(raw.get("display_name") or profile_id.title()),
            linux_user=linux_user,
            workspace=workspace,
            hermes_home=hermes_home,
            rmux_scope=str(raw.get("rmux_scope") or "linux-user"),
            workspace_layout=layout,
            client_layout=client_layout,
        )


def user_exists(name: str) -> bool:
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


class TopologyManager:
    def __init__(self, path: Path):
        self.path = path
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("topology schema_version must be 1")
        if document.get("mode") not in {"multi-user", "single-user"}:
            raise ValueError("topology mode must be multi-user or single-user")
        raw_profiles = document.get("profiles") or {}
        if not isinstance(raw_profiles, dict) or not raw_profiles:
            raise ValueError("topology must define profiles")
        unknown = set(raw_profiles) - set(PROFILE_IDS)
        if unknown:
            raise ValueError(f"unknown profile IDs: {', '.join(sorted(unknown))}")
        self.mode = str(document["mode"])
        self.machine_id = str(document.get("machine_id") or "agk-core")
        shared = document.get("shared") or {}
        if not isinstance(shared, dict):
            raise ValueError("shared topology must be a mapping")
        self.hermes_code = safe_path(shared.get("hermes_code"), label="shared.hermes_code")
        self.hermes_alias = safe_path(shared.get("hermes_alias"), label="shared.hermes_alias")
        self.os_registry = safe_path(shared.get("os_registry"), label="shared.os_registry")
        self.profiles = {
            profile_id: Profile.parse(profile_id, raw)
            for profile_id, raw in raw_profiles.items()
            if isinstance(raw, dict)
        }
        if set(self.profiles) != set(raw_profiles):
            raise ValueError("every profile definition must be a mapping")

    def detect(self) -> dict[str, object]:
        profiles = []
        for profile in self.profiles.values():
            exists = user_exists(profile.linux_user)
            home = Path(pwd.getpwnam(profile.linux_user).pw_dir) if exists else None
            gateway_state, discord_state = self._gateway_health(profile) if exists else (None, None)
            identity_matches = self._identity_matches(profile) if exists else False
            profiles.append({
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "runtime_driver": "linux-user",
                "linux_user": profile.linux_user,
                "user_exists": exists,
                "home": str(home) if home else None,
                "workspace": str(profile.workspace),
                "workspace_exists": profile.workspace.is_dir(),
                "hermes_home": str(profile.hermes_home),
                "hermes_state_exists": profile.hermes_home.is_dir(),
                "rmux_scope": profile.rmux_scope,
                "rmux_sessions": self._rmux_session_count(profile) if exists else None,
                "gateway_state": gateway_state,
                "discord_state": discord_state,
                "runtime_identity_matches": identity_matches,
                "missing_workspace_dirs": [
                    child for child in profile.workspace_layout
                    if not (profile.workspace / child).is_dir()
                ],
            })
        official = False
        origin = None
        if (self.hermes_code / ".git").is_dir():
            result = subprocess.run(
                ["git", "-c", f"safe.directory={self.hermes_code}", "-C", str(self.hermes_code),
                 "remote", "get-url", "origin"],
                text=True, capture_output=True, check=False,
            )
            origin = result.stdout.strip() or None
            official = origin in {
                "https://github.com/NousResearch/hermes-agent",
                "https://github.com/NousResearch/hermes-agent.git",
            }
        alias_target = str(self.hermes_alias.resolve()) if self.hermes_alias.exists() else None
        return {
            "schema_version": 1,
            "mode": self.mode,
            "machine_id": self.machine_id,
            "generated_at": int(time.time()),
            "recommended": all(item["user_exists"] for item in profiles),
            "profiles": profiles,
            "shared": {
                "hermes_code": str(self.hermes_code),
                "hermes_origin": origin,
                "hermes_official": official,
                "hermes_alias": str(self.hermes_alias),
                "hermes_alias_target": alias_target,
                "os_registry": str(self.os_registry),
            },
        }

    def resolve(self, profile_id: str) -> dict[str, object]:
        profile = self.profiles.get(profile_id)
        if not profile:
            raise ValueError(f"unknown profile_id: {profile_id}")
        return {
            "profile_id": profile.profile_id,
            "display_name": profile.display_name,
            "machine_id": self.machine_id,
            "runtime": {
                "driver": "linux-user",
                "linux_user": profile.linux_user,
                "workspace": str(profile.workspace),
                "hermes_home": str(profile.hermes_home),
                "rmux_scope": profile.rmux_scope,
            },
        }

    @staticmethod
    def _gateway_health(profile: Profile) -> tuple[str | None, str | None]:
        path = profile.hermes_home / "gateway_state.json"
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            discord = (state.get("platforms") or {}).get("discord") or {}
            return state.get("gateway_state"), discord.get("state")
        except (OSError, ValueError, AttributeError):
            return None, None

    def _identity_matches(self, profile: Profile) -> bool:
        path = profile.hermes_home / "config.yaml"
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            identity = config.get("runtime_identity") or {}
            return (
                identity.get("machine_id") == self.machine_id
                and identity.get("environment_id") == profile.profile_id
            )
        except (OSError, ValueError, AttributeError, yaml.YAMLError):
            return False

    @staticmethod
    def _rmux_session_count(profile: Profile) -> int | None:
        account = pwd.getpwnam(profile.linux_user)
        if os.geteuid() == account.pw_uid:
            prefix: list[str] = []
        elif os.geteuid() == 0 and shutil.which("sudo"):
            prefix = ["sudo", "-n", "-u", profile.linux_user]
        else:
            return None
        environment = [
            "env",
            f"HOME={account.pw_dir}",
            f"XDG_RUNTIME_DIR=/run/user/{account.pw_uid}",
            "PATH=/usr/local/bin:/usr/bin:/bin",
        ]
        result = subprocess.run(
            [*prefix, *environment, "rmux", "list-sessions"],
            text=True, capture_output=True, check=False,
        )
        if result.returncode:
            return 0 if "no server running" in result.stderr.lower() else None
        return len([line for line in result.stdout.splitlines() if line.strip()])

    def refresh(self) -> dict[str, object]:
        if os.geteuid() != 0:
            raise PermissionError("topology refresh must run as root")
        status = self.detect()
        path = status_cache_path()
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        os.chown(path.parent, 0, 0)
        path.parent.chmod(0o755)
        temporary = path.with_name(path.name + ".new")
        temporary.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chown(temporary, 0, 0)
        temporary.chmod(0o644)
        temporary.replace(path)
        return status

    def cached_status(self) -> dict[str, object] | None:
        try:
            value = json.loads(status_cache_path().read_text(encoding="utf-8"))
            return value if isinstance(value, dict) and value.get("schema_version") == 1 else None
        except (OSError, ValueError):
            return None

    def apply(self) -> list[str]:
        if os.geteuid() != 0:
            raise PermissionError("topology apply must run as root")
        actions: list[str] = []
        for profile in self.profiles.values():
            if not user_exists(profile.linux_user):
                actions.append(f"skipped missing Linux user {profile.linux_user} ({profile.profile_id})")
                continue
            account = pwd.getpwnam(profile.linux_user)
            home = Path(account.pw_dir).resolve()
            if profile.workspace != home and home not in profile.workspace.resolve(strict=False).parents:
                raise ValueError(f"workspace for {profile.profile_id} escapes {home}")
            self._ensure_dir(profile.workspace, account.pw_uid, account.pw_gid, actions)
            for child in profile.workspace_layout:
                self._ensure_dir(profile.workspace / child, account.pw_uid, account.pw_gid, actions)
            if profile.profile_id == "mission":
                clients = profile.workspace / "clients"
                for client in sorted(path for path in clients.iterdir() if path.is_dir() and not path.name.startswith(".")):
                    for child in profile.client_layout or CLIENT_LAYOUT:
                        self._ensure_dir(client / child, account.pw_uid, account.pw_gid, actions)
            agentik_home = home / ".agentik"
            self._ensure_dir(agentik_home, account.pw_uid, account.pw_gid, actions)
            manifest = {
                "schema_version": 1,
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "machine_id": self.machine_id,
                "runtime": {
                    "driver": "linux-user",
                    "linux_user": profile.linux_user,
                    "workspace": str(profile.workspace),
                    "hermes_home": str(profile.hermes_home),
                    "rmux_scope": profile.rmux_scope,
                },
            }
            self._write_managed_yaml(
                agentik_home / "profile.yaml", manifest, account.pw_uid, account.pw_gid, actions
            )
            self._write_workspace_index(profile, account.pw_uid, account.pw_gid, actions)
            self._write_knowledge_index(profile, account.pw_uid, account.pw_gid, actions)
        if not self.hermes_code.is_dir():
            raise FileNotFoundError(f"shared Hermes code is missing: {self.hermes_code}")
        self.hermes_alias.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        target = self.hermes_alias.resolve() if self.hermes_alias.exists() else None
        if target != self.hermes_code.resolve():
            temporary = self.hermes_alias.with_name(self.hermes_alias.name + ".new")
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            temporary.symlink_to(self.hermes_code)
            temporary.replace(self.hermes_alias)
            actions.append(f"linked {self.hermes_alias} -> {self.hermes_code}")
        self.refresh()
        return actions

    @staticmethod
    def _ensure_dir(path: Path, uid: int, gid: int, actions: list[str]) -> None:
        if path.exists() and not path.is_dir():
            raise ValueError(f"required directory is occupied by a file: {path}")
        if not path.exists():
            path.mkdir(mode=0o700, parents=True)
            actions.append(f"created {path}")
        os.chown(path, uid, gid)
        path.chmod(0o700)

    @staticmethod
    def _write_managed_yaml(path: Path, value: dict[str, object], uid: int, gid: int,
                            actions: list[str]) -> None:
        content = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            os.chown(path, uid, gid)
            path.chmod(0o600)
            return
        temporary = path.with_name(path.name + ".new")
        temporary.write_text(content, encoding="utf-8")
        os.chown(temporary, uid, gid)
        temporary.chmod(0o600)
        temporary.replace(path)
        actions.append(f"updated {path}")

    @staticmethod
    def _write_workspace_index(profile: Profile, uid: int, gid: int, actions: list[str]) -> None:
        path = profile.workspace / "WORKSPACE.md"
        managed = "\n".join(f"- `{child}/`" for child in profile.workspace_layout)
        content = (
            f"# {profile.display_name} Workspace\n\n"
            f"Canonical AGK profile: `{profile.profile_id}`. Linux ownership is a runtime detail\n"
            "resolved by TopologyManager. Existing extra directories are preserved.\n\n"
            f"## Managed layout\n\n{managed}\n"
        )
        if path.exists():
            return
        path.write_text(content, encoding="utf-8")
        os.chown(path, uid, gid)
        path.chmod(0o600)
        actions.append(f"created {path}")

    @staticmethod
    def _write_knowledge_index(profile: Profile, uid: int, gid: int, actions: list[str]) -> None:
        destinations = {
            "operator": (
                profile.workspace / "docs/KNOWLEDGE.md",
                "Infrastructure decisions, runbooks and architecture belong here. "
                "Secrets and raw provider state stay outside the workspace.",
            ),
            "agentik": (
                profile.workspace / "knowledge/README.md",
                "Reusable product and company knowledge belongs here. Project-specific context "
                "stays under projects/<project>/knowledge.",
            ),
            "mission": (
                profile.workspace / "KNOWLEDGE.md",
                "Client knowledge is isolated under clients/<client>/knowledge. Only explicitly "
                "shareable internal material belongs under shared.",
            ),
            "private": (
                profile.workspace / "knowledge/README.md",
                "Durable personal knowledge belongs here. Journal entries, goals and project "
                "artifacts remain in their dedicated private directories.",
            ),
        }
        path, rule = destinations[profile.profile_id]
        if path.exists():
            return
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        content = (
            f"# {profile.display_name} Knowledge\n\n{rule}\n\n"
            "Hermes session state remains in `~/.hermes`; AGK runtime metadata remains in "
            "`~/.agentik`. This index contains no credentials.\n"
        )
        path.write_text(content, encoding="utf-8")
        os.chown(path, uid, gid)
        path.chmod(0o600)
        actions.append(f"created {path}")


def print_status(status: dict[str, object]) -> None:
    print(f"AGK TOPOLOGY · {status['mode']} · {status['machine_id']}")
    print(f"{'PROFILE':<11} {'RUNTIME':<18} {'WORKSPACE':<9} {'HERMES':<8} {'RMUX':<5} GATEWAY")
    for raw in status["profiles"]:  # type: ignore[index]
        profile = raw  # type: ignore[assignment]
        runtime = f"linux-user:{profile['linux_user']}"
        print(
            f"{profile['profile_id']:<11} {runtime:<18} "
            f"{'READY' if profile['workspace_exists'] else 'MISSING':<9} "
            f"{'READY' if profile['hermes_state_exists'] else 'MISSING':<8} "
            f"{str(profile.get('rmux_sessions') if profile.get('rmux_sessions') is not None else '—'):<5} "
            f"{profile.get('gateway_state') or '—'}/{profile.get('discord_state') or '—'}"
        )
        missing = ",".join(profile["missing_workspace_dirs"])
        if missing:
            print(f"  missing layout: {missing}")
    shared = status["shared"]  # type: ignore[assignment]
    print(f"Hermes code: {shared['hermes_code']}")
    print(f"Hermes official: {'yes' if shared['hermes_official'] else 'no'}")
    print(f"Hermes alias: {shared['hermes_alias']} -> {shared['hermes_alias_target'] or 'missing'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AGK profile topology manager")
    parser.add_argument("--config", type=Path, default=default_config_path())
    subparsers = parser.add_subparsers(dest="action", required=True)
    for command in ("detect", "status"):
        child = subparsers.add_parser(command)
        child.add_argument("--json", action="store_true")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--yes", action="store_true")
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("--yes", action="store_true")
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("profile_id", choices=PROFILE_IDS)
    resolve_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manager = TopologyManager(args.config)
    if args.action == "resolve":
        resolved = manager.resolve(args.profile_id)
        if args.json:
            print(json.dumps(resolved, indent=2, sort_keys=True))
        else:
            runtime = resolved["runtime"]
            print(f"PROFILE {resolved['profile_id']} · {resolved['display_name']}")
            print(f"Runtime: {runtime['driver']}:{runtime['linux_user']}")
            print(f"Workspace: {runtime['workspace']}")
            print(f"Hermes: {runtime['hermes_home']}")
        return 0
    if args.action in {"detect", "status"}:
        # Profile users cannot traverse the other users' private homes. The
        # root refresh service publishes a credential-free complete snapshot.
        # Root keeps explicit detection live; other callers consume the
        # snapshot instead of reporting false MISSING states.
        use_cache = args.action == "status" or os.geteuid() != 0
        status = manager.cached_status() if use_cache else None
        status = status or manager.detect()
        if args.json:
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            print_status(status)
        return 0 if status["recommended"] else 1
    if not args.yes:
        print(f"topology {args.action} requires --yes", file=sys.stderr)
        return 2
    if args.action == "refresh":
        print_status(manager.refresh())
        return 0
    for action in manager.apply():
        print(action)
    print_status(manager.detect())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, PermissionError, yaml.YAMLError) as exc:
        print(f"topology error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
