from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import pwd
import grp
import re
import shutil
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .constants import (
    CATEGORIES,
    PRODUCT_VERSION,
    PROJECT_SUBDIRS,
    REPO_EXCLUDES,
    SYSTEM_PACKAGES,
    ZONE_STATE_SUBDIRS,
    ZONE_SUBDIRS,
)
from .errors import ReconcileError, SecurityError, StationError, ValidationError
from .filesystem import SafeFS
from .identifiers import environment_slug, validate_identifier
from .identity import Identity, IdentityManager, zone_unix_user
from .maturity import load_catalog, load_os_catalog
from .models import InstallSpec, SeedSpec, ZoneSpec
from .paths import LayoutPaths
from .configuration import compile_zones, load_station_config
from .planner import build_plan, zone_specs
from .receipts import Receipt


class CommandRunner:
    def __init__(self, *, dry_run: bool = False, test_mode: bool = False):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.commands: list[list[str]] = []

    def run(self, argv: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> int:
        if not argv or not all(isinstance(arg, str) and arg for arg in argv):
            raise ValidationError("Commands must be non-empty argument arrays")
        self.commands.append(argv)
        print("+", " ".join(_display_arg(arg) for arg in argv))
        if self.dry_run or self.test_mode:
            return 0
        completed = subprocess.run(argv, check=check, env=env)
        return completed.returncode


def _display_arg(value: str) -> str:
    # Display only. Execution always uses argv arrays, never a reconstructed shell command.
    if re.fullmatch(r"[A-Za-z0-9_./:=+@,-]+", value):
        return value
    return json.dumps(value)


def require_root(paths: LayoutPaths, dry_run: bool) -> None:
    if not dry_run and not paths.test_mode and os.geteuid() != 0:
        raise ReconcileError("Run Station apply with sudo/root. Planning and repository Doctor do not require root.")


def validate_supported_host(paths: LayoutPaths) -> None:
    if paths.test_mode:
        return
    if platform.system() != "Linux":
        raise ReconcileError("Station supports Linux only")
    os_release = Path("/etc/os-release")
    if not os_release.is_file():
        raise ReconcileError("Cannot identify Linux distribution: /etc/os-release is missing")
    values: dict[str, str] = {}
    for line in os_release.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    distro = values.get("ID", "")
    like = values.get("ID_LIKE", "")
    if distro not in {"ubuntu", "debian"} and "debian" not in like.split():
        raise ReconcileError(
            f"Unsupported distribution {distro!r}. Station is intentionally scoped to Ubuntu/Debian with systemd."
        )
    if not shutil.which("apt-get"):
        raise ReconcileError("apt-get is required by the current Ubuntu/Debian provider")
    if not Path("/run/systemd/system").is_dir() or not shutil.which("systemctl"):
        raise ReconcileError("A running systemd host is required by the current Station provider")


@contextmanager
def install_lock(paths: LayoutPaths, operation_id: str) -> Iterator[None]:
    lock_root = paths.run if paths.test_mode else Path("/run/lock")
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / "agentik-station.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReconcileError("Another Station reconcile operation is already running") from exc
        os.ftruncate(fd, 0)
        os.write(fd, f"{operation_id}\n".encode("ascii"))
        os.fsync(fd)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


PROJECT_RUNTIME_SUBDIRS = ("mission-state", "databases", "connector-state", "caches")


def project_creation_layout(paths: LayoutPaths, human: Path, zone_id: str, project_id: str) -> dict[str, Any]:
    """The kernel's Project directory plan, shared by narrow Project creation."""
    validate_identifier(zone_id, "zone_id")
    validate_identifier(project_id, "project_id")
    project = human / "projects" / project_id
    state = paths.zones_state / zone_id / "projects" / project_id
    directories = [(project, 0o750)]
    directories.extend((project / name, 0o700 if name == "credentials" else 0o750) for name in PROJECT_SUBDIRS)
    directories.extend([(project / ".station", 0o750), (state, 0o700)])
    directories.extend((state / name, 0o700) for name in PROJECT_RUNTIME_SUBDIRS)
    return {"human_root": project, "runtime_state_root": state, "directories": directories}


class StationInstaller:
    def __init__(self, repo_root: Path, spec: InstallSpec, paths: LayoutPaths | None = None, *, dry_run: bool = False):
        candidate = Path(repo_root).absolute()
        try:
            repo_stat = os.lstat(candidate)
        except FileNotFoundError as exc:
            raise ValidationError(f"Repository root does not exist: {candidate}") from exc
        if stat.S_ISLNK(repo_stat.st_mode) or not stat.S_ISDIR(repo_stat.st_mode):
            raise SecurityError(f"Repository root must be a real directory: {candidate}")
        self.repo_root = candidate
        self.spec = spec
        self.paths = paths or LayoutPaths.live()
        self.dry_run = dry_run
        self.fs = SafeFS(self.paths.allowed_roots)
        self.commands = CommandRunner(dry_run=dry_run, test_mode=self.paths.test_mode)
        self.identities = IdentityManager(dry_run=dry_run, test_mode=self.paths.test_mode)
        self.config = load_station_config(self.repo_root)
        self._compiled_zones, self._desired_os_by_zone = compile_zones(spec, self.config)
        self.receipt = Receipt(spec)
        self._zone_identities: dict[str, Identity] = {}
        self._zone_paths: dict[str, Path] = {}
        self._enabled_doctor_timer = False

    def print_plan(self, *, as_json: bool = False) -> None:
        self._preflight_zone_identities()
        payload = {
            "kind": "AgentikStationInstallPlan",
            "version": self.spec.release_version,
            "spec": self.spec.to_dict(),
            "steps": [step.to_dict() for step in build_plan(self.spec, self.config)],
            "external_installers": "NOT_RUN_BY_SAFE_KERNEL",
            "final_claim_if_successful": "READY_FOR_SETUP",
        }
        if as_json:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        print(f"Agentik Station {PRODUCT_VERSION} plan · {self.spec.operation_id}")
        print(f"Host: {self.spec.host_id} · role: {self.spec.role} · release: {self.spec.release_version}")
        for index, step in enumerate(build_plan(self.spec, self.config), 1):
            print(f"{index}. {step.id}: {step.description}")
            if step.detail:
                print("   " + json.dumps(step.detail, sort_keys=True))
        print("State after successful apply: READY_FOR_SETUP")
        print("Hermes, Discord, Composio, Tailscale, provider credentials, and remote Fleet are not claimed ready.")

    def apply(self) -> str:
        if self.spec.release_version != self._repository_version():
            raise ValidationError(
                f"InstallSpec release_version {self.spec.release_version!r} does not match repository VERSION "
                f"{self._repository_version()!r}"
            )
        require_root(self.paths, self.dry_run)
        validate_supported_host(self.paths)
        self._preflight_zone_identities()
        if self.dry_run:
            self.print_plan()
            return "PLAN_READY"

        with install_lock(self.paths, self.spec.operation_id):
            # Recheck while serialized, before receipts, apt, ownership changes,
            # or the rollback handler (which itself can write failure evidence).
            self._preflight_zone_identities()
            # Establish receipt storage before the rest of reconciliation.
            self.fs.mkdir(self.paths.varlib, 0o711)
            self.fs.mkdir(self.paths.receipts, 0o750)
            self.receipt.persist(self.fs, self.paths.receipts)
            try:
                self._step("system-packages", self._install_system_packages)
                self._step("station-identity", self._ensure_station_identity)
                self._step("fhs-layout", self._install_layout)
                self._step("versioned-release", self._install_release)
                self._step("desired-state", self._write_host_desired_state)
                self._step("zones", self._reconcile_zones)
                self._step("systemd", self._install_systemd)
                self._step("host-security", self._configure_host_security)
                self._step("observed-state", self._write_observed_state)
                self._step("doctor", self._run_doctor)
                next_actions = [
                    "Enroll and verify Tailscale using the operator-approved setup workflow.",
                    "Install/configure Hermes, then compile Zone/OS profiles and run Hermes/plugin Doctor.",
                    "Enroll dedicated Discord OS bots and require message/command readback.",
                    "Configure Composio principals and connected accounts with explicit Zone boundaries.",
                    "Complete fresh-session acceptance and backup/restore rehearsal before OPERATIONAL.",
                ]
                self.receipt.complete("READY_FOR_SETUP", next_actions)
                self.receipt.persist(self.fs, self.paths.receipts)
                self._write_observed_state(final_state="READY_FOR_SETUP")
                self._refresh_control_projection()
                return "READY_FOR_SETUP"
            except BaseException as exc:
                self.receipt.fail(
                    exc,
                    "Inspect the failed receipt, repair the named step, and rerun the same desired state. "
                    "Do not claim the Host ready.",
                )
                # Roll back Station-owned filesystem mutations best-effort. Package
                # manager changes and Unix users are convergent but not reversible.
                if self._enabled_doctor_timer and not self.paths.test_mode:
                    try:
                        self.commands.run(["systemctl", "disable", "--now", "station-doctor.timer"], check=False)
                    except Exception:
                        pass
                self.fs.rollback()
                try:
                    evidence_fs = SafeFS(self.paths.allowed_roots)
                    evidence_fs.mkdir(self.paths.varlib, 0o750)
                    evidence_fs.mkdir(self.paths.receipts, 0o750)
                    self.receipt.persist(evidence_fs, self.paths.receipts)
                    self.fs = evidence_fs
                    self._write_observed_state(final_state="DEGRADED", failure=str(exc))
                except Exception:
                    pass
                raise

    def _step(self, name: str, function: Any) -> None:
        self.receipt.step(name, "STARTED")
        self.receipt.persist(self.fs, self.paths.receipts)
        function()
        self.receipt.step(name, "COMPLETED")
        self.receipt.persist(self.fs, self.paths.receipts)

    def _repository_version(self) -> str:
        path = self.repo_root / "VERSION"
        if path.is_symlink() or not path.is_file():
            raise SecurityError("Repository VERSION must be a regular file")
        return path.read_text(encoding="utf-8").strip()

    def _install_system_packages(self) -> None:
        if not self.spec.install_system_packages:
            return
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        self.commands.run(["apt-get", "update"], env=env)
        self.commands.run(["apt-get", "install", "-y", "--no-install-recommends", *SYSTEM_PACKAGES], env=env)

    def _ensure_station_identity(self) -> None:
        home = self.paths.varlib / "system"
        identity = self.identities.ensure_system_user("station-system", home)
        self._station_identity = identity

    def _install_layout(self) -> None:
        identity = getattr(self, "_station_identity", None)
        if identity is None:
            identity = self.identities.ensure_system_user("station-system", self.paths.varlib / "system")
            self._station_identity = identity
        root_owner = (0, 0) if not self.paths.test_mode else (os.getuid(), os.getgid())
        system_group_owner = (root_owner[0], identity.gid if identity.gid >= 0 else root_owner[1])
        system_owner = (identity.uid, identity.gid) if identity.uid >= 0 else root_owner

        for path, mode, owner in [
            (self.paths.config, 0o750, system_group_owner),
            (self.paths.software, 0o755, root_owner),
            (self.paths.releases, 0o755, root_owner),
            (self.paths.staging, 0o700, root_owner),
            (self.paths.runtime, 0o755, root_owner),
            (self.paths.varlib, 0o711, system_group_owner),
            (self.paths.log, 0o711, system_group_owner),
            (self.paths.backups, 0o711, system_group_owner),
            (self.paths.run, 0o711, system_group_owner),
        ]:
            self.fs.mkdir(path, mode, owner)

        for path, mode, owner in [
            (self.paths.varlib / "system", 0o700, system_owner),
            (self.paths.varlib / "system" / "hermes-updates", 0o700, system_owner),
            (self.paths.receipts, 0o750, system_group_owner),
            (self.paths.observed, 0o750, system_group_owner),
            (self.paths.varlib / "registry", 0o750, system_group_owner),
            (self.paths.varlib / "doctor", 0o750, system_group_owner),
            (self.paths.zones_state, 0o711, root_owner),
            (self.paths.varlib / "zone-bindings", 0o711, root_owner),
            (self.paths.log / "system", 0o750, system_owner),
            (self.paths.log / "zones", 0o711, root_owner),
            (self.paths.backups / "zones", 0o711, root_owner),
            (self.paths.run / "zones", 0o711, root_owner),
        ]:
            self.fs.mkdir(path, mode, owner)

        for subdir in ["hosts.d", "zones.d", "policies.d", "bindings.d"]:
            self.fs.mkdir(self.paths.config / subdir, 0o750, system_group_owner)

        control = self.paths.runtime / "1_CONTROL"
        zones = self.paths.runtime / "2_ZONES"
        shared = self.paths.runtime / "3_SHARED"
        archive = self.paths.runtime / "4_ARCHIVE"
        for path, mode, owner in [
            (control, 0o750, system_group_owner),
            (zones, 0o755, root_owner),
            (shared, 0o755, root_owner),
            (archive, 0o750, system_group_owner),
        ]:
            self.fs.mkdir(path, mode, owner)
        for category in CATEGORIES.values():
            self.fs.mkdir(zones / category, 0o755, root_owner)
        for name in ["packages", "schemas", "assets", "cache", "resources"]:
            self.fs.mkdir(shared / name, 0o755, root_owner)

        self.fs.write_text(
            self.paths.runtime / "README.md",
            (
                "# Station Runtime\n\n"
                "- `1_CONTROL` is a generated human-readable projection, never the canonical mutable database.\n"
                "- `2_ZONES` contains human-operational Zone and Project assets.\n"
                "- `3_SHARED` contains non-secret, read-only distributions/assets only.\n"
                "- `4_ARCHIVE` contains retired operational exports.\n\n"
                "Canonical desired state lives in `/etc/station`; observed state and receipts live in `/var/lib/station`.\n"
            ),
            0o644,
            root_owner,
        )
        self.fs.write_text(
            control / "README.md",
            (
                "# Control Projection\n\n"
                "This directory is regenerated from `/etc/station` and `/var/lib/station`. "
                "It is for human navigation only and must never become a second source of truth or contain secrets.\n"
            ),
            0o640,
            system_group_owner,
        )
        self.fs.write_text(
            shared / "packages" / "README.md",
            (
                "# Shared package projection\n\n"
                "Canonical package source is in the active immutable Station release. "
                "Generated distributions may be published here later; editable duplicate sources are forbidden.\n"
            ),
            0o644,
            root_owner,
        )
        self.fs.write_text(
            shared / "resources" / "README.md",
            (
                "# Shared resource projection\n\n"
                "Canonical reviewed resources live in `/opt/station/current/resources`. "
                "Use `station resource list` and record selections in the owning Project `resources/`; "
                "this projection is non-secret and never a second editable source.\n"
            ),
            0o644,
            root_owner,
        )

    def _install_release(self) -> None:
        version = self.spec.release_version
        release = self.paths.releases / version
        stage = self.paths.staging / self.spec.operation_id
        if stage.exists():
            self.fs.remove_tree_strict(stage)
        self.fs.mkdir(stage, 0o700)
        try:
            self.fs.copy_tree_strict(self.repo_root, stage, set(REPO_EXCLUDES))
            if release.exists():
                if release.is_symlink() or not release.is_dir():
                    raise SecurityError(f"Release destination is not a real directory: {release}")
                if not self.fs.trees_equal(stage, release):
                    raise ReconcileError(
                        f"Release {version} already exists with different content. Bump VERSION; immutable releases are never overwritten."
                    )
                self.fs.remove_tree_strict(stage)
            else:
                # Move the writable staged tree atomically first, then freeze the
                # final immutable release in place. Freezing the staging directory
                # itself removes write permission from its parent entry and can
                # make rename fail for non-root sandbox reconciliation.
                os.replace(stage, release)
                self.fs.freeze_tree(release)
                if release not in self.fs.journal.created_dirs:
                    self.fs.journal.created_dirs.append(release)
        except Exception:
            if stage.exists():
                self.fs.remove_tree_strict(stage)
            raise

        current_target = f"releases/{version}"
        self.fs.replace_symlink(self.paths.current, current_target, allowed_existing_prefix="releases/")
        cli_target = str(self.paths.current / "station")
        self.fs.replace_symlink(
            self.paths.bin / "station",
            cli_target,
            allowed_existing_prefix=str(self.paths.software),
        )
        source_manifest = self.repo_root / "MANIFEST.json"
        installed_manifest = release / "MANIFEST.json"
        loaded_manifest = self.paths.current / "MANIFEST.json"
        hashes = {
            "source_manifest_sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
            "installed_manifest_sha256": hashlib.sha256(installed_manifest.read_bytes()).hexdigest(),
            "loaded_manifest_sha256": hashlib.sha256(loaded_manifest.read_bytes()).hexdigest(),
        }
        if len(set(hashes.values())) != 1:
            raise ReconcileError("source, installed and loaded release manifest hashes differ")
        self.receipt.evidence["release_provenance"] = {
            **hashes,
            "active_release": version,
            "verified_equal": True,
        }

    def _write_host_desired_state(self) -> None:
        root_owner = (0, 0) if not self.paths.test_mode else (os.getuid(), os.getgid())
        station_identity = getattr(self, "_station_identity")
        owner = (root_owner[0], station_identity.gid if station_identity.gid >= 0 else root_owner[1])
        payload = {
            "schema_version": 1,
            "station_id": self.config.station_id,
            "host_id": self.spec.host_id,
            "role": self.spec.role,
            "release_version": self.spec.release_version,
            "operation_id": self.spec.operation_id,
            "paths": {
                "config": str(self.paths.config),
                "software": str(self.paths.software),
                "runtime": str(self.paths.runtime),
                "state": str(self.paths.varlib),
            },
            "policy": dict(self.config.policy),
            "external_modules": {
                "hermes": "NOT_CONFIGURED",
                "discord": "NOT_CONFIGURED",
                "composio": "NOT_CONFIGURED",
                "tailscale": "NOT_CONFIGURED",
            },
        }
        self.fs.write_text(
            self.paths.config / "station.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            0o640,
            owner,
        )
        yaml = (
            "schema_version: 1\n"
            "station:\n"
            f"  id: {self.config.station_id}\n"
            f"  host_id: {self.spec.host_id}\n"
            f"  role: {self.spec.role}\n"
            f"  release_version: {self.spec.release_version}\n"
            "state_claim: READY_FOR_SETUP_ONLY_AFTER_DOCTOR\n"
        )
        self.fs.write_text(self.paths.config / "station.yaml", yaml, 0o640, owner)
        self.fs.write_text(
            self.paths.config / "hosts.d" / f"{self.spec.host_id}.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "id": self.spec.host_id,
                    "role": self.spec.role,
                    "placement": "local",
                    "release_version": self.spec.release_version,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            0o640,
            owner,
        )

    def _preflight_zone_identities(self) -> None:
        """Never convert an existing client's paths/account into another scope.

        This only reads trusted records and account metadata. A missing record
        is not consent to adopt surviving runtime files or a Unix identity.
        """
        from .doctor import _validate_local_zone_record, _validate_remote_zone_record
        from .organizations import _read_json
        from .os_lifecycle import _directory

        def occupied(path: Path) -> bool:
            SafeFS._assert_existing_absolute_chain(path.parent)
            try:
                os.lstat(path)
                return True
            except FileNotFoundError:
                return False

        host_path = self.paths.config / "station.json"
        if occupied(host_path):
            host = _read_json(self.paths, host_path)
            if (type(host.get("schema_version")) is not int or host["schema_version"] != 1
                    or host.get("host_id") != self.spec.host_id):
                raise ReconcileError("Existing Host identity differs; explicit migration is required")

        root = self.paths.config / "zones.d"
        try:
            with _directory(root, uid=os.getuid() if self.paths.test_mode else 0,
                            trusted_root=self.paths.config if self.paths.test_mode else None) as fd:
                names = os.listdir(fd)
                if len(names) > 2000:
                    raise ValidationError("Zone registry exceeds its entry limit")
                for name in names:
                    if not name.endswith(".json") or not stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                        raise SecurityError("Unexpected entry in the trusted Zone registry")
        except FileNotFoundError:
            names = []
        except OSError as exc:
            raise SecurityError("Cannot safely inspect the trusted Zone registry") from exc

        existing: dict[str, ZoneSpec] = {}
        identities: dict[str, ZoneSpec] = {}
        for name in sorted(names):
            record_path = root / name
            value = _read_json(self.paths, record_path)
            try:
                if value.get("placement") == "REMOTE_DESIRED_NOT_APPLIED":
                    _validate_remote_zone_record(value, record_path=record_path)
                    continue
                zone, _, _, user = _validate_local_zone_record(
                    value, record_path=record_path, paths=self.paths, expected_host_id=self.spec.host_id)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValidationError("Existing Zone record is unsafe or belongs to another Host") from exc
            if user in identities and identities[user] != zone:
                raise ReconcileError("Existing Zones alias one Unix identity; explicit repair is required")
            existing[zone.zone_id], identities[user] = zone, zone

        for zone in self._compiled_zones:
            user = zone_unix_user(zone.category, zone.name, zone.environment)
            prior = existing.get(zone.zone_id)
            if prior is not None and prior != zone:
                raise ReconcileError("Existing Zone identity conflicts with requested category/client/environment/Host")
            if user in identities and identities[user] != zone:
                raise ReconcileError("Requested Zones alias one Unix identity; explicit isolation is required")
            identities[user] = zone
            if prior is None:
                for path in (self._zone_human_path(zone), self.paths.zones_state / zone.zone_id,
                             self.paths.log / "zones" / zone.zone_id,
                             self.paths.run / "zones" / zone.zone_id,
                             self.paths.backups / "zones" / zone.zone_id,
                             self.paths.varlib / "zone-bindings" / f"{zone.zone_id}.json"):
                    if occupied(path):
                        raise ReconcileError("Zone state exists without its trusted identity record; explicit repair is required")
        if not self.paths.test_mode:
            self._audit_zone_accounts(identities, existing)

    def _audit_zone_accounts(self, identities: dict[str, ZoneSpec], existing: dict[str, ZoneSpec]) -> None:
        """Read existing accounts; never reassign names, homes, UIDs or groups."""
        seen_uids: dict[int, str] = {}
        seen_gids: dict[int, str] = {}
        for user, zone in identities.items():
            try:
                entry = pwd.getpwnam(user)
            except KeyError:
                entry = None
            try:
                group = grp.getgrnam(user)
            except KeyError:
                group = None
            if zone.zone_id not in existing:
                if entry is not None or group is not None:
                    raise ReconcileError("Unix Zone account exists without its trusted identity record; explicit repair is required")
                continue
            if (entry is None or group is None or entry.pw_uid == 0 or entry.pw_gid == 0
                    or entry.pw_gid != group.gr_gid
                    or Path(entry.pw_dir) != self.paths.zones_state / zone.zone_id / "home"
                    or entry.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"}):
                raise ReconcileError("Existing Zone Unix identity differs from its trusted home/group contract")
            if entry.pw_uid in seen_uids or entry.pw_gid in seen_gids:
                raise ReconcileError("Different Zones share a Unix UID or group; explicit repair is required")
            seen_uids[entry.pw_uid], seen_gids[entry.pw_gid] = user, user

    def _zone_human_path(self, zone: ZoneSpec) -> Path:
        base = self.paths.runtime / "2_ZONES" / CATEGORIES[zone.category]
        if zone.category in {"ORGANIZATIONS", "PROJECTS"}:
            path = base / zone.name / environment_slug(zone.environment)
        else:
            path = base / zone.name
        # Components are validated before joining; containment is still checked by SafeFS.
        self.fs.anchor_for(path)
        return path

    def _reconcile_zones(self) -> None:
        for zone in zone_specs(self.spec, self.config):
            self._create_zone(zone)
        if self.spec.seed and self.spec.seed.project:
            seed_zone = ZoneSpec(
                category=self.spec.seed.category,
                name=self.spec.seed.name,
                environment=self.spec.seed.environment,
                host_id=self.spec.host_id,
                organization=self.spec.seed.organization,
            )
            self._create_project(seed_zone, self.spec.seed.project)

    def _create_zone(self, zone: ZoneSpec) -> None:
        user_name = zone_unix_user(zone.category, zone.name, zone.environment)
        state_root = self.paths.zones_state / zone.zone_id
        identity = self.identities.ensure_system_user(user_name, state_root / "home")
        owner = (identity.uid, identity.gid) if identity.uid >= 0 else (os.getuid(), os.getgid())
        root_owner = (0, 0) if not self.paths.test_mode else (os.getuid(), os.getgid())
        human = self._zone_human_path(zone)

        if zone.category in {"ORGANIZATIONS", "PROJECTS"}:
            self.fs.mkdir(human.parent, 0o711, root_owner)
        self.fs.mkdir(human, 0o750, owner)
        created_human = [human]
        for name in ZONE_SUBDIRS:
            mode = 0o700 if name == "credentials" else 0o750
            path = self.fs.mkdir(human / name, mode, owner)
            created_human.append(path)

        self.fs.mkdir(state_root, 0o700, owner)
        for name in ZONE_STATE_SUBDIRS:
            self.fs.mkdir(state_root / name, 0o700, owner)
        self._seed_zone_hermes_voice(state_root, owner)
        self.fs.mkdir(self.paths.log / "zones" / zone.zone_id, 0o700, owner)
        self.fs.mkdir(self.paths.run / "zones" / zone.zone_id, 0o700, owner)
        self.fs.mkdir(self.paths.backups / "zones" / zone.zone_id, 0o700, root_owner)
        self._configure_zone_rootless(zone, identity, state_root)

        payload = {
            "schema_version": 2,
            "id": zone.zone_id,
            "name": zone.name,
            "category": zone.category,
            "organization": zone.organization,
            "environment": zone.environment,
            "host_id": zone.host_id,
            "unix_user": user_name,
            "human_root": str(human),
            "state_root": str(state_root),
            "hermes_home": str(state_root / "hermes"),
            "log_root": str(self.paths.log / "zones" / zone.zone_id),
            "runtime_root": str(self.paths.run / "zones" / zone.zone_id),
            "backup_staging_root": str(self.paths.backups / "zones" / zone.zone_id),
            "placement": "local",
            "isolation": {
                "filesystem": "unix-identity",
                "hermes_home": "dedicated",
                "credentials": "zone-scoped",
                "cross_zone_mounts": "deny",
            },
        }
        if zone.category == "ORGANIZATIONS":
            self.fs.write_text(
                human / "members" / "README.md",
                "# Organization member scopes\n\n"
                "Member scopes hold bindings and namespaces for individual humans inside the Organization. "
                "They are not a substitute for a separate Zone when hard filesystem isolation is required.\n",
                0o640,
                owner,
            )

        self.fs.write_text(human / "ZONE.json", json.dumps(payload, indent=2, sort_keys=True) + "\n", 0o640, owner)
        self.fs.write_text(
            human / "ZONE.yaml",
            "".join(
                [
                    "schema_version: 2\n",
                    f"id: {zone.zone_id}\n",
                    f"category: {zone.category}\n",
                    f"organization: {zone.organization or 'null'}\n",
                    f"environment: {zone.environment}\n",
                    f"host_id: {zone.host_id}\n",
                    f"unix_user: {user_name}\n",
                    f"state_root: {state_root}\n",
                    f"hermes_home: {state_root / 'hermes'}\n",
                ]
            ),
            0o640,
            owner,
        )
        self.fs.write_text(
            human / "README.md",
            f"# {zone.name}\n\nZone `{zone.zone_id}` on Host `{zone.host_id}`. High-churn runtime state is stored under `{state_root}`.\n",
            0o640,
            owner,
        )
        desired = []
        catalog = self._os_catalog()
        by_id = {item["id"]: item for item in catalog["packages"]}
        for package_id in self._desired_os_by_zone.get(zone.zone_id, ()):
            package = by_id.get(package_id)
            if package is None:
                raise ReconcileError(f"Desired OS package is absent from the canonical catalog: {package_id}")
            desired.append(
                {
                    "id": package_id,
                    "desired": True,
                    "package_maturity": package["maturity"],
                    "runtime_state": "NOT_INSTALLED",
                    "claim": "DECLARED_ONLY",
                }
            )
        self.fs.write_text(
            human / "os" / "DESIRED.json",
            json.dumps({"schema_version": 1, "zone_id": zone.zone_id, "packages": desired}, indent=2, sort_keys=True)
            + "\n",
            0o640,
            owner,
        )
        self.fs.write_text(
            self.paths.config / "zones.d" / f"{zone.zone_id}.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            0o640,
            ((0 if not self.paths.test_mode else os.getuid()), getattr(self, "_station_identity").gid if getattr(self, "_station_identity").gid >= 0 else os.getgid()),
        )
        self._zone_identities[zone.zone_id] = identity
        # A root-owned, group-scoped projection lets a Zone read ONLY its own
        # binding without opening /etc/station or trusting its editable ZONE.json.
        self.fs.write_text(
            self.paths.varlib / "zone-bindings" / f"{zone.zone_id}.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n", 0o640,
            (root_owner[0], owner[1]),
        )
        self._zone_paths[zone.zone_id] = human

    def _seed_zone_hermes_voice(self, state_root: Path, owner: tuple[int, int]) -> None:
        """Seed the reviewed voice defaults without overwriting operator state."""
        source = self.repo_root / "config" / "hermes" / "voice.default.yaml"
        if source.is_symlink() or not source.is_file():
            raise ReconcileError(f"Hermes voice defaults are missing or unsafe: {source}")
        target = state_root / "hermes" / "config.yaml"
        if target.is_symlink():
            raise SecurityError(f"Hermes config may not be a symlink: {target}")
        if target.exists():
            if not target.is_file():
                raise SecurityError(f"Hermes config must be a regular file: {target}")
            return
        self.fs.write_text(target, source.read_text(encoding="utf-8"), 0o600, owner)

    def _configure_zone_rootless(self, zone: ZoneSpec, identity: Identity, state_root: Path) -> None:
        """Provision deterministic per-Zone rootless container configuration.

        This does not start containers or claim runtime verification. It creates
        isolated storage/config roots that a Zone-owned Podman service can use
        after the external runtime gate is enrolled.
        """
        owner = (identity.uid, identity.gid) if identity.uid >= 0 else (os.getuid(), os.getgid())
        home = state_root / "home"
        config = home / ".config" / "containers"
        data = home / ".local" / "share" / "containers"
        runtime = state_root / "rootless"
        self.fs.mkdir(config, 0o700, owner)
        self.fs.mkdir(data, 0o700, owner)
        self.fs.mkdir(runtime, 0o700, owner)
        self.fs.mkdir(runtime / "networks", 0o700, owner)
        self.fs.write_text(
            config / "storage.conf",
            (
                "[storage]\n"
                'driver = "overlay"\n'
                f'graphroot = "{data / "storage"}"\n'
                f'runroot = "{self.paths.run / "zones" / zone.zone_id / "containers"}"\n'
                "\n[storage.options]\n"
                'mount_program = "/usr/bin/fuse-overlayfs"\n'
            ),
            0o600,
            owner,
        )
        self.fs.write_text(
            config / "containers.conf",
            (
                "[containers]\n"
                "pids_limit = 2048\n"
                "default_capabilities = []\n"
                "no_hosts = false\n"
                "\n[engine]\n"
                'events_logger = "file"\n'
                f'events_logfile_path = "{self.paths.log / "zones" / zone.zone_id / "podman-events.log"}"\n'
            ),
            0o600,
            owner,
        )
        self.fs.write_text(
            runtime / "POLICY.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "zone_id": zone.zone_id,
                    "unix_user": identity.name,
                    "storage_root": str(data / "storage"),
                    "run_root": str(self.paths.run / "zones" / zone.zone_id / "containers"),
                    "network_policy": "zone-private-by-default",
                    "cross_zone_mounts": "deny",
                    "resource_policy": {
                        "pids_limit": 2048,
                        "cpu": "explicit-per-workload",
                        "memory": "explicit-per-workload",
                    },
                    "claim": "ROOTLESS_CONFIGURED_NOT_RUNTIME_VERIFIED",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            0o600,
            owner,
        )

    def _create_project(self, zone: ZoneSpec, project_id: str) -> None:
        project_id = validate_identifier(project_id, "project_id")
        identity = self._zone_identities.get(zone.zone_id)
        human = self._zone_paths.get(zone.zone_id)
        if identity is None or human is None:
            raise ReconcileError(f"Zone must be reconciled before Project creation: {zone.zone_id}")
        owner = (identity.uid, identity.gid) if identity.uid >= 0 else (os.getuid(), os.getgid())
        layout = project_creation_layout(self.paths, human, zone.zone_id, project_id)
        project, state_root = layout["human_root"], layout["runtime_state_root"]
        for directory, mode in layout["directories"]:
            self.fs.mkdir(directory, mode, owner)
        payload = {
            "schema_version": 2,
            "id": project_id,
            "zone_id": zone.zone_id,
            "organization": zone.organization,
            "environment": zone.environment,
            "human_root": str(project),
            "runtime_state_root": str(state_root),
            "repos": [],
            "credential_references": [],
        }
        self.fs.write_text(project / "PROJECT.json", json.dumps(payload, indent=2, sort_keys=True) + "\n", 0o640, owner)
        self.fs.write_text(
            project / "PROJECT.yaml",
            f"schema_version: 2\nid: {project_id}\nzone_id: {zone.zone_id}\nenvironment: {zone.environment}\nruntime_state_root: {state_root}\n",
            0o640,
            owner,
        )
        self.fs.write_text(
            project / "README.md",
            (
                f"# {project_id}\n\n"
                "All Project source, documentation, knowledge, resources, references, workspaces, artifacts, evidence, and operations belong here.\n\n"
                "Clone repositories only under `repos/`. Then run `station rules install --repo <absolute-repository-path>` "
                "as the owning Zone user so Hermes, Codex, Claude Code, Gemini CLI and GitHub Copilot inherit the same Station rules.\n"
            ),
            0o640,
            owner,
        )
        rules_path = self.repo_root / "rules" / "STATION_AGENT_RULES.md"
        if rules_path.is_symlink() or not rules_path.is_file():
            raise ReconcileError(f"Canonical Station agent rules are missing or unsafe: {rules_path}")
        self.fs.write_text(
            project / ".station" / "STATION_AGENT_RULES.md",
            rules_path.read_text(encoding="utf-8"),
            0o640,
            owner,
        )
        adapters = {
            "AGENTS.md": "# Project agent contract\n\nRead and obey `.station/STATION_AGENT_RULES.md` before any work.\n",
            "CLAUDE.md": "# Claude Code contract\n\nRead and obey `.station/STATION_AGENT_RULES.md` before any work.\n",
            "GEMINI.md": "# Gemini CLI contract\n\nRead and obey `.station/STATION_AGENT_RULES.md` before any work.\n",
        }
        for filename, content in adapters.items():
            self.fs.write_text(project / filename, content, 0o640, owner)

    def _os_catalog(self) -> dict[str, Any]:
        return load_os_catalog(self.repo_root / "os" / "CATALOG.json")

    def _install_systemd(self) -> None:
        source = self.repo_root / "runtime" / "systemd"
        if source.is_symlink() or not source.is_dir():
            raise ReconcileError("The single canonical runtime/systemd directory is missing")
        for unit in sorted(source.iterdir()):
            if unit.suffix not in {".service", ".timer"} or not unit.is_file() or unit.is_symlink():
                continue
            self.fs.copy_file(unit, self.paths.systemd / unit.name, 0o644)
        if not self.paths.test_mode:
            self.commands.run(["systemctl", "daemon-reload"])
            if self.spec.enable_doctor_timer:
                self.commands.run(["systemctl", "enable", "--now", "station-doctor.timer"])
                self._enabled_doctor_timer = True
            # Hermes watch is installed but intentionally disabled until Hermes setup and LAB acceptance.

    def _configure_host_security(self) -> None:
        if self.spec.configure_fail2ban and not self.paths.test_mode:
            self.commands.run(["systemctl", "enable", "--now", "fail2ban"])

    def _module_observations(self) -> list[dict[str, Any]]:
        catalog = load_catalog(self.repo_root / "modules" / "catalog.json")
        observations = []
        for module in catalog["modules"]:
            item = dict(module)
            probes = module.get("binary_probes", [])
            item["binaries"] = {name: bool(shutil.which(name)) for name in probes}
            if module["id"] in {"station-kernel", "host-foundation", "zone-runtime"}:
                item["runtime_readiness"] = "CONFIGURED"
            elif probes and all(item["binaries"].values()):
                item["runtime_readiness"] = "BINARY_AVAILABLE"
            else:
                item["runtime_readiness"] = "NOT_CONFIGURED"
            observations.append(item)
        return observations

    def _write_observed_state(self, *, final_state: str = "RECONCILING", failure: str | None = None) -> None:
        station_identity = getattr(self, "_station_identity", None)
        owner = (
            (0 if not self.paths.test_mode else os.getuid()),
            station_identity.gid if station_identity and station_identity.gid >= 0 else os.getgid(),
        )
        payload: dict[str, Any] = {
            "schema_version": 1,
            "host_id": self.spec.host_id,
            "role": self.spec.role,
            "release_version": self.spec.release_version,
            "operation_id": self.spec.operation_id,
            "state": final_state,
            "modules": self._module_observations(),
            "zones": sorted(self._zone_paths),
        }
        if failure:
            payload["failure"] = failure
            payload["next_repair_action"] = "Inspect the latest failed receipt and rerun reconciliation after repair."
        self.fs.write_text(
            self.paths.observed / "host.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            0o640,
            owner,
        )

    def _run_doctor(self) -> None:
        from .doctor import station_doctor

        result = station_doctor(self.paths, repo_root=self.repo_root, full=True, expect_operation=self.spec.operation_id)
        if not result.ok:
            summary = "; ".join(issue["message"] for issue in result.issues[:5])
            raise ReconcileError(f"Station Doctor failed after reconcile: {summary}")
        station_identity = getattr(self, "_station_identity")
        owner = ((0 if not self.paths.test_mode else os.getuid()), station_identity.gid if station_identity.gid >= 0 else os.getgid())
        self.fs.write_text(
            self.paths.varlib / "doctor" / "latest.json",
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            0o640,
            owner,
        )

    def _refresh_control_projection(self) -> None:
        station_identity = getattr(self, "_station_identity")
        owner = ((0 if not self.paths.test_mode else os.getuid()), station_identity.gid if station_identity.gid >= 0 else os.getgid())
        control = self.paths.runtime / "1_CONTROL"
        host = json.loads((self.paths.observed / "host.json").read_text(encoding="utf-8"))
        zones = []
        for path in sorted((self.paths.config / "zones.d").glob("*.json")):
            if path.is_symlink():
                raise SecurityError(f"Symlink forbidden in desired state: {path}")
            zones.append(json.loads(path.read_text(encoding="utf-8")))
        self.fs.write_text(control / "HOST.json", json.dumps(host, indent=2, sort_keys=True) + "\n", 0o640, owner)
        self.fs.write_text(
            control / "ZONES.json",
            json.dumps({"schema_version": 1, "zones": zones}, indent=2, sort_keys=True) + "\n",
            0o640,
            owner,
        )


def build_seed(
    category: str | None,
    name: str | None,
    environment: str | None,
    organization: str | None,
    project: str | None,
) -> SeedSpec | None:
    values = [category, name, environment]
    if not any(values):
        if organization or project:
            raise ValidationError("Organization/project seed options require category, name, and environment")
        return None
    if not all(values):
        raise ValidationError("Seed category, name, and environment must be supplied together")
    return SeedSpec(
        category=str(category),
        name=str(name),
        environment=str(environment),
        organization=organization,
        project=project,
    )
