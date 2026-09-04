from __future__ import annotations

import grp
import os
import pwd
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import ReconcileError, SecurityError, ValidationError
from .identifiers import validate_identifier


@dataclass(frozen=True)
class Identity:
    name: str
    uid: int
    gid: int
    home: Path


class IdentityManager:
    def __init__(self, *, dry_run: bool = False, test_mode: bool = False):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.commands: list[list[str]] = []

    def _run(self, argv: list[str]) -> None:
        self.commands.append(argv)
        if self.dry_run or self.test_mode:
            return
        subprocess.run(argv, check=True)

    def ensure_system_user(self, name: str, home: Path) -> Identity:
        validate_identifier(name, "Unix identity")
        if len(name) > 31:
            raise ValidationError(f"Unix identity exceeds 31 characters: {name}")
        if self.test_mode:
            return Identity(name=name, uid=os.getuid(), gid=os.getgid(), home=Path(home))
        try:
            entry = pwd.getpwnam(name)
            group = grp.getgrnam(name)
            existing_home = Path(entry.pw_dir)
            if existing_home != Path(home):
                raise ReconcileError(
                    f"Existing user {name} has home {existing_home}, expected {home}. "
                    "Resolve the identity conflict before continuing."
                )
            if entry.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"}:
                raise ReconcileError(f"Existing Station user {name} has an interactive shell: {entry.pw_shell}")
            if entry.pw_gid != group.gr_gid:
                raise ReconcileError(
                    f"Existing Station user {name} has primary gid {entry.pw_gid}, "
                    f"but its canonical group {name} has gid {group.gr_gid}. Repair the identity before continuing."
                )
            identity = Identity(name=name, uid=entry.pw_uid, gid=group.gr_gid, home=existing_home)
        except KeyError:
            if self.dry_run:
                # Numeric ownership is intentionally unresolved during a plan.
                return Identity(name=name, uid=-1, gid=-1, home=Path(home))
            self._run(
                [
                    "useradd",
                    "--system",
                    "--user-group",
                    "--shell",
                    "/usr/sbin/nologin",
                    "--home-dir",
                    str(home),
                    "--no-create-home",
                    name,
                ]
            )
            entry = pwd.getpwnam(name)
            group = grp.getgrnam(name)
            if entry.pw_gid != group.gr_gid:
                raise ReconcileError(f"Created Station user {name} does not use its canonical primary group")
            identity = Identity(name=name, uid=entry.pw_uid, gid=group.gr_gid, home=Path(home))
        if not self.dry_run:
            self.ensure_subids(name)
        return identity

    def ensure_subids(self, name: str) -> None:
        if self.test_mode:
            return
        subuid = Path("/etc/subuid")
        subgid = Path("/etc/subgid")
        self._audit_subid_file(subuid)
        self._audit_subid_file(subgid)
        existing_uid = self._read_subid(subuid, name)
        existing_gid = self._read_subid(subgid, name)
        if existing_uid and existing_gid:
            if existing_uid != existing_gid:
                raise ReconcileError(f"Subuid/subgid ranges differ for {name}; repair before continuing")
            return
        if bool(existing_uid) != bool(existing_gid):
            raise ReconcileError(f"Only one subordinate ID range exists for {name}; repair before continuing")
        start = self._next_free_subid((subuid, subgid))
        self._append_subid(subuid, name, start)
        self._append_subid(subgid, name, start)

    @staticmethod
    def _audit_subid_file(path: Path) -> None:
        if not path.exists():
            return
        ranges: list[tuple[int, int, str]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            parts = line.split(":")
            if len(parts) != 3:
                continue
            try:
                start, count = int(parts[1]), int(parts[2])
            except ValueError:
                raise ReconcileError(f"Invalid subordinate ID record at {path}:{line_no}")
            if count <= 0:
                raise ReconcileError(f"Invalid subordinate ID count at {path}:{line_no}")
            ranges.append((start, start + count, parts[0]))
        for previous, current in zip(sorted(ranges), sorted(ranges)[1:]):
            if current[0] < previous[1]:
                raise ReconcileError(
                    f"Overlapping subordinate ID ranges in {path}: {previous[2]} and {current[2]}. "
                    "Repair the host identity map before Station reconciliation."
                )

    @staticmethod
    def _read_subid(path: Path, name: str) -> tuple[int, int] | None:
        if not path.exists():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split(":")
            if len(parts) == 3 and parts[0] == name:
                return int(parts[1]), int(parts[2])
        return None

    @staticmethod
    def _next_free_subid(paths: tuple[Path, Path], size: int = 65536) -> int:
        ranges: list[tuple[int, int]] = []
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                parts = line.split(":")
                if len(parts) != 3:
                    continue
                try:
                    start, count = int(parts[1]), int(parts[2])
                except ValueError:
                    continue
                ranges.append((start, start + count))
        candidate = 1_000_000
        for start, end in sorted(ranges):
            if candidate + size <= start:
                break
            if candidate < end:
                candidate = ((end + size - 1) // size) * size
        if candidate + size >= 2**32:
            raise ReconcileError("No subordinate UID/GID range available")
        return candidate

    @staticmethod
    def _append_subid(path: Path, name: str, start: int, size: int = 65536) -> None:
        if path.exists():
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise SecurityError(f"Refusing unsafe subordinate ID file: {path}")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o644)
        try:
            os.write(fd, f"{name}:{start}:{size}\n".encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)


def zone_unix_user(category: str, name: str, environment: str) -> str:
    mapping = {
        ("SYSTEM", "station-maintainer"): "z-system-maint",
        ("SYSTEM", "discord-bootstrap"): "z-system-discord",
        ("SYSTEM", "fleet-operator"): "z-system-fleet",
    }
    if (category, name) in mapping:
        return mapping[(category, name)]
    if category == "PRIVATE":
        return "z-private"
    if category == "AGENTIK":
        return "z-agentik"
    if category == "FACTORY":
        return "z-factory"
    if category == "LAB":
        return "z-lab"
    prefix = "z-o-" if category == "ORGANIZATIONS" else "z-p-"
    suffix = {"development": "dev", "staging": "stg", "production": "prod"}[environment]
    value = f"{prefix}{name}-{suffix}"
    if len(value) > 31:
        raise ValidationError(
            f"Zone name {name!r} produces Unix identity {value!r} longer than 31 characters. "
            "Choose a shorter canonical Zone ID."
        )
    validate_identifier(value, "Unix Zone identity")
    return value
