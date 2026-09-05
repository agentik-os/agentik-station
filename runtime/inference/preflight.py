#!/usr/bin/python3
"""Read-only root preflight before launching source-owned Hermes Python.

It never imports or executes Hermes as root. Ownership checks attest separation
from Zone identities, not immutability against the source operator. The existing
operator's uv hardlinks are allowed only when their inode owner/mode are trusted.
"""

from __future__ import annotations

import ast
import argparse
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys


HERMES_PARENT = Path("/opt/station/tools/hermes")
HERMES_CURRENT = HERMES_PARENT / "current"
PYTHON_PARENT = HERMES_PARENT / "python"
HERMES_PIN = "29112bef099274229cadff79cdff7bf7b99c4b77"
SOURCE_HOME = "/home/agk-station"
MAX_ENTRIES = 500000
EXCLUDED = {".git", "node_modules"}
KNOWN_MODE_REPAIRS = (
    ("venv/.lock", "file", 0o666, 0o600),
    ("plugins/platforms/discord/__pycache__", "directory", 0o775, 0o755),
    ("tui_gateway/__pycache__", "directory", 0o775, 0o755),
    ("gateway/relay/__pycache__", "directory", 0o775, 0o755),
    ("agent/monitoring/__pycache__", "directory", 0o775, 0o755),
)


class PreflightError(Exception):
    pass


def inside(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def open_checked(path: Path, owners: tuple[int, ...], *, directory: bool = False) -> int:
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.parts[1:]
        for index, name in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1 or directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            if st.st_uid not in owners or stat.S_IMODE(st.st_mode) & 0o022:
                raise PreflightError("unsafe_code_path")
        return fd
    except BaseException:
        os.close(fd)
        raise


def safe_resolve(path: Path, roots: tuple[Path, ...], owners: tuple[int, ...]) -> Path:
    """Resolve only explicitly confined links, checking real parents with dirfds."""
    path = Path(os.path.abspath(path))
    if not inside(path, roots) or EXCLUDED.intersection(path.parts):
        raise PreflightError("unapproved_code_path")
    links = 0
    while True:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        current = Path("/")
        restart = None
        try:
            parts = path.parts[1:]
            for index, name in enumerate(parts):
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if st.st_uid not in owners:
                    raise PreflightError("untrusted_code_owner")
                if stat.S_ISLNK(st.st_mode):
                    links += 1
                    if links > 40:
                        raise PreflightError("code_link_cycle")
                    target = Path(os.readlink(name, dir_fd=fd))
                    if not target.is_absolute():
                        target = current / target
                    target = Path(os.path.abspath(target))
                    if not inside(target, roots) or EXCLUDED.intersection(target.parts):
                        raise PreflightError("code_link_escape")
                    restart = target.joinpath(*parts[index + 1:])
                    break
                if stat.S_IMODE(st.st_mode) & 0o022:
                    raise PreflightError("writable_code_path")
                current /= name
                if index < len(parts) - 1:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino):
                        os.close(child)
                        raise PreflightError("changed_code_path")
                    os.close(fd)
                    fd = child
                elif not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                    raise PreflightError("special_code_path")
        finally:
            os.close(fd)
        if restart is None:
            return current
        path = restart


def read_regular(path: Path, roots: tuple[Path, ...], owners: tuple[int, ...], limit=262144) -> bytes:
    resolved = safe_resolve(path, roots, owners)
    fd = open_checked(resolved, owners)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid not in owners
                or stat.S_IMODE(st.st_mode) & 0o022 or st.st_size > limit):
            raise PreflightError("unsafe_code_file")
        raw = os.read(fd, limit + 1)
        if len(raw) > limit:
            raise PreflightError("oversized_code_file")
        return raw
    finally:
        os.close(fd)


def inspect_tree(root: Path, roots: tuple[Path, ...], owners: tuple[int, ...], *, exclusions=()) -> dict:
    count, links = 0, 0
    startup_files = []
    root = safe_resolve(root, roots, owners)
    def walk(fd: int, path: Path, depth: int):
        nonlocal count, links
        if depth > 100:
            raise PreflightError("code_tree_too_deep")
        for name in os.listdir(fd):
            if name == 'node_modules' or (depth == 0 and name in exclusions):
                continue
            count += 1
            if count > MAX_ENTRIES:
                raise PreflightError("code_tree_too_large")
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if st.st_uid not in owners:
                raise PreflightError("untrusted_code_owner")
            child_path = path / name
            if stat.S_ISLNK(st.st_mode):
                links += 1
                safe_resolve(child_path, roots, owners)
            elif stat.S_IMODE(st.st_mode) & 0o022:
                raise PreflightError("writable_code_path")
            elif stat.S_ISDIR(st.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino):
                        raise PreflightError("changed_code_path")
                    walk(child, child_path, depth + 1)
                finally:
                    os.close(child)
            elif not stat.S_ISREG(st.st_mode):
                raise PreflightError("special_code_path")
            if name.endswith(".pth") or name.endswith(".egg-link"):
                startup_files.append(child_path)
    fd = open_checked(root, owners, directory=True)
    try:
        walk(fd, root, 0)
    finally:
        os.close(fd)
    return {"entries": count, "links": links, "startup_files": startup_files}


def validate_startup_file(path: Path, source: Path, roots: tuple[Path, ...], owners: tuple[int, ...]):
    raw = read_regular(path, roots, owners, limit=16384).decode("utf-8")
    if path.suffix == ".egg-link":
        raise PreflightError("unreviewed_python_startup")
    lines = [line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if path.name == "_virtualenv.pth" and lines == ["import _virtualenv"]:
        return
    if path.name == 'distutils-precedence.pth' and lines == [
        "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'; enabled and __import__('_distutils_hack').add_shim();"
    ]:
        return  # Reviewed standard setuptools shim in the managed base Python.
    finder = "__editable___hermes_agent_0_21_0_finder"
    if (path.name != "__editable__.hermes_agent-0.21.0.pth"
            or lines != [f"import {finder}; {finder}.install()"]):
        # Python startup executes .pth code before broker checks. Only the
        # observed pinned native startup hooks are admitted, no arbitrary path.
        raise PreflightError("unreviewed_python_startup")
    parsed = ast.parse(read_regular(path.with_name(finder + ".py"), roots, owners).decode("utf-8"))
    found = {}
    for node in parsed.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in ("MAPPING", "NAMESPACES"):
                found[node.target.id] = ast.literal_eval(node.value)
    if set(found) != {"MAPPING", "NAMESPACES"}:
        raise PreflightError("invalid_editable_mapping")
    for name, mapping in found.items():
        if not isinstance(mapping, dict):
            raise PreflightError("invalid_editable_mapping")
        for target in mapping.values():
            values = target if name == "NAMESPACES" else [target]
            if not isinstance(values, list):
                raise PreflightError("invalid_editable_mapping")
            for value in values:
                if not isinstance(value, str) or not Path(value).is_absolute():
                    raise PreflightError("invalid_editable_mapping")
                normalized = Path(os.path.abspath(value))
                if not inside(normalized, (source, HERMES_CURRENT)) or EXCLUDED.intersection(normalized.parts):
                    raise PreflightError("editable_mapping_escape")


def repair_known_modes(source: Path, python: Path, owners: tuple[int, ...]) -> list[str]:
    """Only six observed historical software modes, no traversal or broad chmod."""
    changed = []
    targets = [(source / relative, kind, before, after)
               for relative, kind, before, after in KNOWN_MODE_REPAIRS]
    targets.append((python / ".lock", "file", 0o666, 0o600))
    for path, kind, before, after in targets:
        parent = open_checked(path.parent, owners, directory=True)
        try:
            try:
                st = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue  # a cache/uv lock not yet generated does not need creation
            if st.st_uid not in owners or not (stat.S_ISDIR(st.st_mode) if kind == "directory"
                                               else stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                                               and st.st_size == 0):
                raise PreflightError("unreviewed_mode_repair_target")
            mode = stat.S_IMODE(st.st_mode)
            if not mode & 0o022:
                continue
            if mode != before:
                raise PreflightError("unreviewed_mode_repair_value")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if kind == "directory":
                flags |= os.O_DIRECTORY
            fd = os.open(path.name, flags, dir_fd=parent)
            try:
                current = os.fstat(fd)
                if (current.st_dev, current.st_ino, current.st_mode, current.st_uid,
                        current.st_nlink, current.st_size) != (
                        st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_nlink, st.st_size):
                    raise PreflightError("changed_mode_repair_target")
                os.fchmod(fd, after)
                os.fsync(fd)
                changed.append(str(path.relative_to(source)) if path.is_relative_to(source) else "python/.lock")
            finally:
                os.close(fd)
        finally:
            os.close(parent)
    return changed


def preflight(*, repair: bool = False) -> dict:
    if os.getuid() != 0 or os.geteuid() != 0:
        raise PreflightError("root_preflight_required")
    account = pwd.getpwnam("agk-station")
    if account.pw_uid == 0 or account.pw_dir != SOURCE_HOME:
        raise PreflightError("source_identity_mismatch")
    owners = (0, account.pw_uid)
    source = safe_resolve(HERMES_CURRENT, (HERMES_PARENT,), owners)
    python = safe_resolve(PYTHON_PARENT, (HERMES_PARENT,), owners)
    roots = (source, python)
    repaired = repair_known_modes(source, python, owners) if repair else []
    source_tree = inspect_tree(source, roots, owners, exclusions=(".git", "node_modules"))
    python_tree = inspect_tree(python, roots, owners)
    interpreter = safe_resolve(source / "venv/bin/python", roots, owners)
    if not interpreter.is_relative_to(python):
        raise PreflightError("unapproved_interpreter")
    cfg = read_regular(source / "venv/pyvenv.cfg", roots, owners, limit=8192).decode("utf-8")
    values = dict(line.split("=", 1) for line in cfg.splitlines() if "=" in line)
    values = {key.strip(): value.strip() for key, value in values.items()}
    if values.get("include-system-site-packages") != "false":
        raise PreflightError("system_site_packages_not_isolated")
    home = safe_resolve(Path(values.get("home", "/")), roots, owners)
    if not home.is_relative_to(python):
        raise PreflightError("unapproved_interpreter_home")
    for startup in source_tree["startup_files"] + python_tree["startup_files"]:
        validate_startup_file(startup, source, roots, owners)
    # Never run operator-owned Git config/hooks under root. Git is invoked as
    # its existing operator, with global/system config and helper hooks disabled.
    base = ["/usr/sbin/runuser", "-u", "agk-station", "--", "/usr/bin/env", "-i",
            "HOME=" + SOURCE_HOME, "PATH=/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM=1",
            "GIT_CONFIG_GLOBAL=/dev/null", "/usr/bin/git", "-c", "core.fsmonitor=false",
            "-c", "core.hooksPath=/dev/null", "-C", str(source)]
    pin = subprocess.run(base + ["rev-parse", "HEAD"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
    clean = subprocess.run(base + ["diff", "--no-ext-diff", "--no-textconv", "--quiet", "HEAD", "--"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30, check=False)
    if pin.returncode or pin.stdout.strip() != HERMES_PIN.encode() or clean.returncode:
        raise PreflightError("source_pin_or_tracked_bytes_changed")
    return {"schema_version": 1, "state": "SOURCE_TRUST_VERIFIED", "source_uid": account.pw_uid,
            "source_owned_code_mutable_by_operator": True, "provider_authentication": "NOT_CHECKED",
            "entries_checked": source_tree["entries"] + python_tree["entries"],
            "links_checked": source_tree["links"] + python_tree["links"],
            "known_modes_repaired": repaired,
            "hermes_commit": HERMES_PIN}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-known-modes", action="store_true",
                        help="Normalize only the six documented historical software modes")
    args = parser.parse_args()
    try:
        result = preflight(repair=args.repair_known_modes)
    except PreflightError as exc:
        print("Inference source trust preflight failed: " + str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("Inference source trust preflight failed; no provider was executed", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
