"""Explicit personal Workstation context; never a Unix/Zone sandbox.

No environment-only project-root override: resolve the same owned marker used by
the npm installer. Same-UID software can still edit its own marker and files.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import stat
import sys
from pathlib import Path


def agent_environment(environment: str, home: Path) -> tuple[str, str]:
    """Resolve legacy agent scope from the real identity, never an env-only alias.

    ``agk-station`` is the dedicated Host operator's session namespace; existing
    agent catalogs call its policy role ``operator``. Neither spelling grants
    access to another Unix identity, arbitrary agents, or canonical OS instances.
    Personal Workstation enrollment has a separate, validated private namespace.
    """
    uid = os.geteuid()
    if uid == 0 or os.getuid() != uid:
        raise ValueError("Specialized agents require their non-root owning identity")
    account = pwd.getpwuid(uid)
    if Path.home() != home:
        raise ValueError("Specialized agent HOME differs from its runtime owner")
    if os.environ.get("STATION_WORKSTATION_ROOT"):
        if workstation_root() is None or environment != "private":
            raise ValueError("Workstation specialized agents require the private environment")
        return "private", "private"
    expected_home = Path("/home") / account.pw_name
    if home != expected_home or Path(account.pw_dir) != expected_home:
        raise ValueError("Specialized agent HOME is not the canonical account home")
    if account.pw_name == "agk-station":
        if environment not in {"agk-station", "operator"}:
            raise ValueError("Specialized agent environment differs from the Station operator")
        return "agk-station", "operator"
    if account.pw_name not in {"operator", "agentik", "mission", "private"} or environment != account.pw_name:
        raise ValueError("Specialized agent environment differs from its owning account")
    return environment, environment


def workstation_root() -> Path | None:
    value = os.environ.get("STATION_WORKSTATION_ROOT")
    if not value:
        return None
    root = Path(value)
    if not root.is_absolute() or str(root) != value or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid Workstation root")
    # Resolve each actual parent before trusting the marker or derived paths.
    cursor = Path(root.anchor)
    for part in root.parts[1:]:
        cursor /= part
        record = cursor.lstat()
        if not stat.S_ISDIR(record.st_mode):
            raise ValueError("Unsafe Workstation directory")
    record = root.stat()
    if record.st_uid != os.getuid() or record.st_mode & 0o077:
        raise ValueError("Workstation root must be owned and private")
    marker = root / ".station-workstation.json"
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077 or metadata.st_size > 65536:
            raise ValueError("Unsafe Workstation marker")
        with os.fdopen(fd, "r", closefd=False, encoding="utf-8") as handle:
            document = json.load(handle)
    finally:
        os.close(fd)
    profile = "station-" + hashlib.sha256(value.encode()).hexdigest()[:12]
    expected = {"schema": 1, "mode": "workstation", "root": value, "uid": os.getuid(), "profile": profile}
    if not isinstance(document, dict) or any(document.get(key) != item for key, item in expected.items()):
        raise ValueError("Workstation marker/context mismatch")
    expected_home = root / "personal/home"
    if Path.home() != expected_home:
        raise ValueError("Workstation HOME mismatch")
    for target in (root / "personal", expected_home, root / "projects", root / "bin"):
        record = target.lstat()
        if not stat.S_ISDIR(record.st_mode) or record.st_uid != os.getuid() or record.st_mode & 0o077:
            raise ValueError("Unsafe Workstation child directory")
    return root


def agk_executable() -> str:
    root = workstation_root()
    if root is None:
        return "/usr/local/bin/agk"
    executable = root / "bin/agk"
    record = executable.lstat()
    if not stat.S_ISREG(record.st_mode) or record.st_nlink != 1 or record.st_uid != os.getuid() or record.st_mode & 0o022 or not os.access(executable, os.X_OK):
        raise ValueError("Unsafe Workstation AGK launcher")
    return str(executable)


def permitted_cwd(candidate: Path, home: Path) -> bool:
    root = workstation_root()
    roots = [home.resolve()]
    if root is not None:
        roots.append(root / "projects")
    resolved = candidate.resolve()
    return any(resolved == allowed or allowed in resolved.parents for allowed in roots)


if __name__ == "__main__":
    if sys.argv[1:] != ["--validate"]:
        raise SystemExit("usage: workstation.py --validate")
    try:
        selected = workstation_root()
        if selected is None:
            raise ValueError("No Workstation selected")
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit("Invalid Station Workstation scope; no legacy command executed") from None
