#!/usr/bin/env python3
"""Explicit reviewed operator software refresh; no credentials or services."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import pwd
import stat
import sys
import uuid


# Exact reviewed Station 11.22 and 11.23 controls. The latter comes from
# 8d6994ea329c348abea628311e9e20b1ec6863a1. Never accept arbitrary installed bytes.
PREVIOUS = {
    "bin/agk": frozenset({
        "f86d05b8e2c014056eb49e362bffcac2c9c73755536ebd5699b4b59364b68df8",
        "4e84b0bf28eb936a062b476c52dc3d546281c1739dec2c117e7d97e96e829be6",
    }),
    "scripts/agk_control.py": frozenset({
        "5ae627aa79d2eca21194b0b735dbee5030039c3a498526ec3f3b262f5773133d",
        "0e527d95999f1bf052abe6b27adc1e01054c6f505328fb853d68da328ffcba5b",
    }),
    "scripts/provider.sh": frozenset({
        "e9d8c11fe54612b7598cf4aa2690a5b8526300f5aa1ecca8a96a76fca0037c13",
    }),
    "scripts/gateway_watchdog.py": frozenset({
        "a20c69424a87d6121ac62e54756836d4e63d7c090a7e80fff9a431c122f24419",
    }),
    "scripts/doctor.sh": frozenset({
        "ace715215cecb66869c20aed1a7402fcdfc8c6fd6e36233421a4cb3c8b9b1c82",
    }),
    "hermes/plugins/platforms/discord/agk_session_panel.py": frozenset({
        "28695b10ddc08b55f5563bb9a6fb712db7b2f8b8e6836cd1e77e724290b59b98",
    }),
    "scripts/sync-hermes.sh": frozenset({
        "246dc7015ad4c4fb5722218a89127d7b244b9d5a4ab0b92e193a061733c27c80",
    }),
}
# Exact HOME-relative software destinations only, including the one confirmed
# operator plugin copy. Other profiles, state, configuration and native binaries
# are never scanned or implicitly adopted. Every destination must already exist.
TARGETS = {
    ".local/bin/agk": ("bin/agk", 0o755),
    ".local/lib/agk-terminal/scripts/agk_control.py": ("scripts/agk_control.py", 0o755),
    ".local/lib/agk-terminal/scripts/provider.sh": ("scripts/provider.sh", 0o755),
    ".local/lib/agk-terminal/scripts/gateway_watchdog.py": ("scripts/gateway_watchdog.py", 0o755),
    ".local/lib/agk-terminal/scripts/doctor.sh": ("scripts/doctor.sh", 0o755),
    ".local/lib/agk-terminal/hermes/plugins/platforms/discord/agk_session_panel.py": (
        "hermes/plugins/platforms/discord/agk_session_panel.py", 0o644),
    ".hermes/plugins/platforms/discord/agk_session_panel.py": (
        "hermes/plugins/platforms/discord/agk_session_panel.py", 0o644),
    ".local/lib/agk-terminal/scripts/sync-hermes.sh": ("scripts/sync-hermes.sh", 0o755),
}
MAX_BYTES = 256 * 1024


def _operator():
    account = pwd.getpwuid(os.geteuid())
    if (os.geteuid() == 0 or os.getuid() != account.pw_uid or account.pw_name != "agk-station"
            or account.pw_dir != "/home/agk-station"):
        raise ValueError("Run controls-only as the dedicated non-root agk-station operator")
    return account


@contextmanager
def _parent(path: Path, *, uid: int, anchor: Path):
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(anchor):
        raise ValueError("Invalid controls path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current = Path("/")
    observed = []
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            current /= part
            if current.is_relative_to(anchor):
                info = os.fstat(fd)
                if info.st_uid not in {0, uid} or info.st_mode & 0o022:
                    raise ValueError("Unsafe controls directory")
                observed.append((current, (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)))
        yield fd
        for directory, identity in observed:
            info = directory.lstat()
            if (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid) != identity:
                raise ValueError("Controls directory changed during refresh; inspect the canonical installed paths")
    finally:
        os.close(fd)


def _read(parent: int, name: str, owners: set[int], executable: bool = True) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in owners
                or info.st_mode & 0o022 or (executable and not info.st_mode & 0o100)
                or info.st_size > MAX_BYTES):
            raise ValueError("Unsafe controls file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Controls file exceeds limit")
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
                    value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (identity(os.fstat(fd)) != identity(info)
                or identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity(info)):
            raise ValueError("Controls file changed while reading; stop and review")
        return data
    finally:
        os.close(fd)


def refresh_controls(source: Path, prefix: Path) -> dict:
    account = _operator()
    home = Path(account.pw_dir)
    if prefix != home / ".local":
        raise ValueError("Controls-only requires the operator's canonical .local prefix")
    prepared = []
    for destination, (relative, mode) in TARGETS.items():
        previous = PREVIOUS[relative]
        source_file = source / relative
        executable = bool(mode & 0o100)
        target = home / destination
        with _parent(source_file.parent, uid=account.pw_uid, anchor=source) as parent:
            # Source files are copied as data, never executed. Git ships some
            # Python helpers as 0644 even though install.sh publishes them 0755.
            content = _read(parent, source_file.name, {0, account.pw_uid}, False)
        with _parent(target.parent, uid=account.pw_uid, anchor=home) as parent:
            old = _read(parent, target.name, {account.pw_uid}, executable)
        if old != content and hashlib.sha256(old).hexdigest() not in previous:
            raise ValueError("Installed controls were customized or are not a reviewed release; preserved for review")
        prepared.append((target, old, content, mode, executable))
    changed = []
    # All files are checked before the first mutation. This is not a global
    # transaction: a filesystem failure after one replacement requires retry.
    for target, old, content, mode, executable in prepared:
        with _parent(target.parent, uid=account.pw_uid, anchor=home) as parent:
            if _read(parent, target.name, {account.pw_uid}, executable) != old:
                raise ValueError("Installed controls changed during refresh; stop and review")
            if old == content:
                continue
            temporary = ".station-control-" + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(content)
                    stream.flush()
                os.fchmod(fd, mode)
                os.fsync(fd)
                os.replace(temporary, target.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                os.close(fd)
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
            if _read(parent, target.name, {account.pw_uid}, executable) != content:
                raise ValueError("Controls readback failed; inspect and retry the explicit refresh")
            changed.append(str(target.relative_to(home)))
    return {"state": "CONTROLS_REFRESHED", "changed": changed, "runtime_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = refresh_controls(Path(__file__).resolve().parents[1], args.prefix)
    except (OSError, ValueError):
        print("Controls refresh incomplete: require reviewed unmodified controls and safe operator-owned paths; "
              "inspect before retrying. No credentials or runtime data are changed.", file=sys.stderr)
        return 2
    print(result["state"] + ": " + (", ".join(result["changed"]) or "already current"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
