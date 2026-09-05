#!/usr/bin/env python3
"""Publish allowlisted operator SOFTWARE, never an operator home or account."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentik_station.errors import StationError
from agentik_station.filesystem import SafeFS
from agentik_station.installer import install_lock
from agentik_station.models import new_operation_id
from agentik_station.os_lifecycle import _directory
from agentik_station.paths import LayoutPaths
from agentik_station.projects import _rename_noreplace


class SharedToolchainError(ValueError):
    pass


CACHES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
PRIVATE = {".env", ".npmrc", ".netrc", "auth.json", "credentials.json", ".git",
           ".config", ".cache", ".npm", ".ssh", ".codex", ".hermes", ".chatbotX"}
KEYS = ("NODE_VERSION", "NPM_VERSION", "PYTHON_VERSION", "AI_PYTHON_VERSION",
        "GITHUB_CLI_VERSION", "UV_VERSION", "VERCEL_CLI_VERSION", "SHADCN_CLI_VERSION", "CHATBOTX_CLI_VERSION",
        "CHATBOTX_CLI_ENTRY_SHA256")
MAX_FILE = 512 * 1024 * 1024
MAX_FILES = 200_000


def _checked(path: Path, owners: set[int], *, directory=False):
    info = path.lstat()
    if info.st_uid not in owners or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022):
        raise SharedToolchainError(f"Untrusted software ownership/mode: {path}")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise SharedToolchainError(f"Software root must be a real directory: {path}")
    return info


def _read(path: Path, owners: set[int], *, limit=MAX_FILE) -> bytes:
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in owners
                    or info.st_mode & 0o022 or info.st_size > limit):
                raise SharedToolchainError(f"Unsafe or oversized software file: {path}")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise SharedToolchainError("Software file grew beyond its size limit")
            return data
        finally:
            os.close(fd)


def _package(path: Path, name: str, version: str, owners: set[int], *, entry_sha256=None):
    value = json.loads(_read(path / "package.json", owners, limit=1024 * 1024))
    if value.get("name") != name or value.get("version") != version:
        raise SharedToolchainError(f"Software package does not match its reviewed pin: {name}")
    expected = {"npm": {"npm": "bin/npm-cli.js", "npx": "bin/npx-cli.js"},
                "vercel": {"vercel": "dist/vc.js"}, "shadcn": {"shadcn": "dist/index.js"},
                "@openai/codex": {"codex": "bin/codex.js"}, "chatbotx": {"chatbotx": "dist/index.cjs"}}[name]
    bins = value.get("bin")
    if isinstance(bins, str):
        bins = {name.rsplit("/", 1)[-1]: bins}
    if not isinstance(bins, dict):
        raise SharedToolchainError(f"Missing reviewed package bin metadata: {name}")
    normalized = {}
    for command, target in bins.items():
        if (not isinstance(command, str) or not isinstance(target, str) or not target
                or Path(target).is_absolute() or ".." in Path(target).parts or "\\" in target):
            raise SharedToolchainError(f"Unsafe package bin metadata: {name}")
        normalized[command] = str(Path(target))
    if any(normalized.get(command) != target for command, target in expected.items()):
        raise SharedToolchainError(f"Package entrypoint differs from its reviewed layout: {name}")
    if name == "chatbotx":
        if (not isinstance(entry_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", entry_sha256)
                or hashlib.sha256(_read(path / "dist/index.cjs", owners)).hexdigest() != entry_sha256):
            raise SharedToolchainError("ChatbotX entrypoint differs from its reviewed SHA-256")
        # The reviewed tarball contains these six files (including package.json).
        # It bundles runtime dependencies into its CJS/ESM entries.
        for relative in ("README.md", "dist/index.cjs", "dist/index.mjs", "dist/index.d.cts", "dist/index.d.mts"):
            _read(path / relative, owners)


def _source_parents(home: Path, sources: dict[str, Path], owners: set[int]):
    for source in sources.values():
        if not source.is_relative_to(home):
            raise SharedToolchainError("Software source escapes its operator home")
        for parent in (source.parent, *source.parent.parents):
            if not parent.is_relative_to(home):
                break
            _checked(parent, owners, directory=True)


def _private_chatbotx_launcher(home: Path, node: Path, version: str, entry_sha256: str, *, check=False, verify=False):
    """Manage only Station's private wrapper; the upstream JS has no shebang."""
    owners = {os.geteuid()}
    prefix = home / ".local/share/station-clis/chatbotx"
    package = prefix / "node_modules/chatbotx"
    target = package / "dist/index.cjs"
    wrapper = home / ".local/bin/chatbotx"
    node_pattern = re.escape(str(home / ".local/lib/node-v")) + r"\d+\.\d+\.\d+-linux-(x64|arm64)/bin/node"
    if (not home.is_absolute() or ".." in home.parts or home == Path("/")
            or not re.fullmatch(node_pattern, str(node)) or not re.fullmatch(r"\d+\.\d+\.\d+", version)):
        raise SharedToolchainError("Invalid private ChatbotX software paths or pin")
    for path in (package / "dist", wrapper.parent, node.parent):
        SafeFS._assert_existing_absolute_chain(path)
        for parent in (path, *path.parents):
            if not parent.is_relative_to(home):
                break
            if parent.exists():
                _checked(parent, owners, directory=True)
    for path in (prefix / "package.json", prefix / "package-lock.json", prefix / "npm-shrinkwrap.json",
                 prefix / "node_modules/.package-lock.json", package / "package.json", target):
        if os.path.lexists(path):
            _read(path, owners)

    def body(runtime):
        return ("#!/bin/sh\n# Station ChatbotX code; caller-owned account/configuration.\numask 077\nexec "
                + shlex.quote(str(runtime)) + " " + shlex.quote(str(target)) + ' "$@"\n').encode()

    if os.path.lexists(wrapper):
        previous = _read(wrapper, owners, limit=8192)
        lines = previous.decode().splitlines()
        command = shlex.split(lines[3]) if len(lines) == 4 else []
        if (len(command) != 4 or command[0] != "exec" or command[2:] != [str(target), "$@"]
                or not re.fullmatch(node_pattern, command[1]) or previous != body(command[1])):
            raise SharedToolchainError("Refusing unrelated private ChatbotX launcher")
        if verify and previous != body(node):
            raise SharedToolchainError("Private ChatbotX launcher does not select the pinned Node runtime")
    elif verify:
        raise SharedToolchainError("Private ChatbotX launcher is missing")
    if check:
        return
    _read(node, owners)
    _source_parents(home, {"chatbotx": package}, owners)
    _checked(package, owners, directory=True)
    _package(package, "chatbotx", version, owners, entry_sha256=entry_sha256)
    _read(target, owners)
    if not verify:
        SafeFS([wrapper.parent]).write_bytes(wrapper, body(node), 0o755)


def _destination_parents(path: Path, owner: int):
    for parent in (path, *path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        # Root-owned sticky /tmp is safe for isolated test roots: another UID
        # cannot replace an authority-owned child there. Production paths are
        # fixed /opt/station/tools/toolchain and /usr/local/bin.
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, owner}
                or (info.st_mode & 0o022 and not sticky_root)):
            raise SharedToolchainError(f"Untrusted shared-software parent: {parent}")


def _walk_error(error):
    raise SharedToolchainError(f"Could not completely inventory shared software: {error}") from error


def _sources(home: Path, pins: dict, arch: str, codex: bool, owners: set[int]):
    machine = {"x64": "x86_64", "arm64": "aarch64"}.get(arch)
    if machine is None:
        raise SharedToolchainError("Unsupported shared Node architecture")
    sources = {"node": home / f".local/lib/node-v{pins['NODE_VERSION']}-linux-{arch}"}
    for package, key, folder in (("npm", "NPM_VERSION", "npm"), ("vercel", "VERCEL_CLI_VERSION", "vercel"),
                                 ("shadcn", "SHADCN_CLI_VERSION", "shadcn")):
        sources["npm/" + folder] = home / ".local/lib/node_modules" / package
        _package(sources["npm/" + folder], package, pins[key], owners)
    sources["npm/chatbotx"] = home / ".local/share/station-clis/chatbotx/node_modules/chatbotx"
    _package(sources["npm/chatbotx"], "chatbotx", pins["CHATBOTX_CLI_VERSION"], owners,
             entry_sha256=pins["CHATBOTX_CLI_ENTRY_SHA256"])
    if codex:
        sources["npm/codex"] = home / ".local/lib/node_modules/@openai/codex"
        _package(sources["npm/codex"], "@openai/codex", pins["CODEX_CLI_VERSION"], owners)
    for alias, folder, key in (("python-latest", "latest", "PYTHON_VERSION"), ("python-ai", "ai", "AI_PYTHON_VERSION")):
        runtime = home / f".local/share/uv/python/cpython-{pins[key]}-linux-{machine}-gnu"
        executable = runtime / "bin" / ("python" + ".".join(pins[key].split(".")[:2]))
        link = home / ".local/bin" / alias
        _checked(link, owners)
        if not link.is_symlink() or link.resolve(strict=True) != executable.resolve(strict=True):
            raise SharedToolchainError(f"Python alias does not select its reviewed complete uv runtime: {alias}")
        if not executable.resolve(strict=True).is_relative_to(runtime):
            raise SharedToolchainError("Python executable escapes its standalone runtime")
        sources["python/" + folder] = runtime
    for name in ("gh", "uv", "uvx"):
        sources["standalone/" + name] = home / ".local/bin" / name
    return sources


def _inventory(sources: dict[str, Path], owners: set[int]):
    entries, originals = {}, {}
    for destination, source in sources.items():
        with _directory(source.parent):
            pass
        top = _checked(source, owners)
        if stat.S_ISREG(top.st_mode):
            candidates = [(source, Path(destination))]
        elif stat.S_ISDIR(top.st_mode):
            candidates = [(source, Path(destination))]
            for root, dirs, files in os.walk(source, followlinks=False, onerror=_walk_error):
                dirs[:] = [name for name in dirs if name not in CACHES]
                for name in dirs + files:
                    if name in CACHES or name.endswith((".pyc", ".pyo")):
                        continue
                    original = Path(root) / name
                    relative = Path(destination) / original.relative_to(source)
                    if str(relative) == "node/lib/node_modules/npm/.npmrc":
                        # The reviewed Node archive bundles an empty npm config
                        # placeholder. It is not executable code: omit it without
                        # reading its contents. Never exempt nonempty/private
                        # configuration, aliases, or any other .npmrc location.
                        info = _checked(original, owners)
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != 0:
                            raise SharedToolchainError(f"Unsafe bundled npm config placeholder: {relative}")
                        continue
                    if name in PRIVATE or name.startswith(".env."):
                        raise SharedToolchainError(f"Private state is forbidden in shared software: {relative}")
                    candidates.append((original, relative))
        else:
            raise SharedToolchainError("Software allowlist root must not be a symlink or special file")
        for original, relative in candidates:
            if len(entries) >= MAX_FILES:
                raise SharedToolchainError("Software inventory exceeds its file limit")
            info = _checked(original, owners)
            key = str(relative)
            if stat.S_ISDIR(info.st_mode):
                entry = {"type": "directory", "mode": 0o555}
            elif stat.S_ISREG(info.st_mode):
                data = _read(original, owners)
                entry = {"type": "file", "mode": 0o555 if info.st_mode & 0o111 else 0o444,
                         "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            elif stat.S_ISLNK(info.st_mode):
                target = original.resolve(strict=True)
                mapped = next((Path(dst) / target.relative_to(src) for dst, src in sources.items()
                               if src.is_dir() and target.is_relative_to(src)), None)
                if mapped is None:
                    raise SharedToolchainError(f"Software symlink escapes the explicit allowlist: {original}")
                entry = {"type": "symlink", "target": os.path.relpath(mapped, relative.parent),
                         "resolved": str(mapped)}
            else:
                raise SharedToolchainError(f"Special file is forbidden in shared software: {original}")
            entries[key], originals[key] = entry, original
    for entry in entries.values():
        if entry["type"] == "symlink" and entry["resolved"] not in entries:
            raise SharedToolchainError("Software symlink targets excluded/private state")
    return entries, originals


def _exports(pins, codex):
    result = {"node": "node/bin/node", "npm": "npm/npm/bin/npm-cli.js", "npx": "npm/npm/bin/npx-cli.js",
              "gh": "standalone/gh", "uv": "standalone/uv", "uvx": "standalone/uvx",
              "vercel": "npm/vercel/dist/vc.js", "shadcn": "npm/shadcn/dist/index.js",
              "chatbotx": "npm/chatbotx/dist/index.cjs"}
    for alias, folder, key in (("python-latest", "latest", "PYTHON_VERSION"), ("python-ai", "ai", "AI_PYTHON_VERSION")):
        result[alias] = "python/" + folder + "/bin/python" + ".".join(pins[key].split(".")[:2])
    if codex:
        result["codex"] = "npm/codex/bin/codex.js"
    return result


def _launcher(final: Path, name: str, target: str) -> bytes:
    # All interpolation is validated canonical installation paths, never a
    # reconstructed user command. Account-related environment is left untouched.
    command = [str(final / target)]
    if name in {"npm", "npx", "vercel", "shadcn", "codex", "chatbotx"}:
        command.insert(0, str(final / "node/bin/node"))
    npm_prefix = 'export NPM_CONFIG_PREFIX="${NPM_CONFIG_PREFIX:-$HOME/.local}"\n' if name in {"npm", "npx"} else ""
    private_mode = "umask 077\n" if name == "chatbotx" else ""
    return ("#!/bin/sh\n# Station shared code; caller-owned account/configuration.\n" + npm_prefix + private_mode
            + "exec " + " ".join(shlex.quote(item) for item in command) + ' "$@"\n').encode()


def _validate_public(bin_root: Path, shared_root: Path, names, owner: int):
    for name in names:
        path = bin_root / name
        if not os.path.lexists(path):
            continue
        info = path.lstat()
        if not stat.S_ISLNK(info.st_mode) or info.st_uid != owner:
            raise SharedToolchainError(f"Refusing unrelated public entrypoint: {path}")
        link = os.readlink(path)
        target = Path(os.path.abspath(path.parent / link))
        if (not target.is_relative_to(shared_root) or target.name != name or target.parent.name != "bin"
                or target.parent.parent.parent != shared_root):
            raise SharedToolchainError(f"Refusing unrelated public symlink: {path}")
        manifest_path = target.parent.parent / "MANIFEST.json"
        manifest = json.loads(_read(manifest_path, {owner}, limit=64 * 1024 * 1024))
        expected = manifest.get("files", {}).get("bin/" + name)
        if (not isinstance(expected, dict) or expected.get("type") != "file"
                or hashlib.sha256(_read(target, {owner})).hexdigest() != expected.get("sha256")):
            raise SharedToolchainError("Previously managed public entrypoint is not intact")


def _verify_tree(final: Path, manifest: dict, owner: int):
    root_info = _checked(final, {owner}, directory=True)
    if stat.S_IMODE(root_info.st_mode) != 0o555:
        raise SharedToolchainError("Immutable shared toolchain root permissions differ")
    recorded = json.loads(_read(final / "MANIFEST.json", {owner}, limit=64 * 1024 * 1024))
    if recorded != manifest:
        raise SharedToolchainError("Same-pin immutable shared toolchain differs; reviewed rebuild required")
    observed = set()
    for root, dirs, files in os.walk(final, followlinks=False, onerror=_walk_error):
        for name in dirs + files:
            path = Path(root) / name
            relative = str(path.relative_to(final))
            if relative == "MANIFEST.json":
                continue
            entry = manifest["files"].get(relative)
            if entry is None:
                raise SharedToolchainError("Unexpected file in immutable shared toolchain")
            observed.add(relative)
            info = _checked(path, {owner})
            if entry["type"] == "symlink":
                if not stat.S_ISLNK(info.st_mode) or os.readlink(path) != entry["target"]:
                    raise SharedToolchainError("Immutable software symlink differs")
            elif entry["type"] == "directory":
                if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != entry["mode"]:
                    raise SharedToolchainError("Immutable software directory differs")
            elif stat.S_IMODE(info.st_mode) != entry["mode"] or hashlib.sha256(_read(path, {owner})).hexdigest() != entry["sha256"]:
                raise SharedToolchainError("Immutable software file differs")
    if observed != set(manifest["files"]):
        raise SharedToolchainError("Immutable shared software files are missing")


def _probe(final: Path, exports: dict, pins: dict, user: str, uid: int, gid: int):
    runner = shutil.which("runuser")
    if not runner:
        raise SharedToolchainError("runuser is required for credential-free shared-code verification")
    with tempfile.TemporaryDirectory(prefix="station-toolchain-probe-") as temporary:
        os.chown(temporary, uid, gid)
        prefix = [runner, "--user", user, "--", "/usr/bin/env", "-i", f"HOME={temporary}",
                  f"PATH={final / 'bin'}:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE=1"]
        expected = {"node": "NODE_VERSION", "npm": "NPM_VERSION", "npx": "NPM_VERSION", "gh": "GITHUB_CLI_VERSION",
                    "uv": "UV_VERSION", "uvx": "UV_VERSION", "vercel": "VERCEL_CLI_VERSION", "shadcn": "SHADCN_CLI_VERSION",
                    "codex": "CODEX_CLI_VERSION", "chatbotx": "CHATBOTX_CLI_VERSION",
                    "python-latest": "PYTHON_VERSION", "python-ai": "AI_PYTHON_VERSION"}
        for name in exports:
            completed = subprocess.run([*prefix, str(final / "bin" / name), "--version"],
                                       cwd=temporary, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
            output = completed.stdout + completed.stderr
            if (completed.returncode or pins[expected[name]] not in output
                    or (name == "chatbotx" and output.strip() != pins[expected[name]])):
                raise SharedToolchainError(f"Shared {name} version verification failed; public commands were not changed")
        if "chatbotx" in exports:
            completed = subprocess.run([*prefix, str(final / "bin/chatbotx"), "--help"],
                                       cwd=temporary, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
            if completed.returncode or "chatbotx <group> <action> [options]" not in completed.stdout:
                raise SharedToolchainError("Shared ChatbotX help verification failed; public commands were not changed")
        code = """import pathlib, ssl, sqlite3, sys, tempfile, venv, subprocess
expected = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(sys.base_prefix).resolve() == expected
assert pathlib.Path(sys.executable).resolve().is_relative_to(expected)
assert pathlib.Path(ssl.__file__).resolve().is_relative_to(expected)
with tempfile.TemporaryDirectory(prefix='station-python-probe-') as target:
    venv.EnvBuilder(with_pip=False).create(target)
    subprocess.run([target+'/bin/python', '-I', '-B', '-c', 'import ssl,sqlite3; assert ssl.OPENSSL_VERSION'], check=True)
"""
        for name, folder in (("python-latest", "latest"), ("python-ai", "ai")):
            completed = subprocess.run([*prefix, str(final / "bin" / name), "-I", "-B", "-c", code,
                                        str(final / "python" / folder)], cwd=temporary, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            if completed.returncode:
                raise SharedToolchainError("Shared Python is not self-contained after relocation; public commands were not changed")


def publish_toolchain(*, station_home: Path, station_uid: int, station_gid: int, pins: dict[str, str], node_arch: str,
                      shared_root: Path = Path("/opt/station/tools/toolchain"), bin_root: Path = Path("/usr/local/bin"),
                      include_codex=True, authority_uid=0, authority_gid=0, probe=None) -> dict:
    try:
        home, shared_root, bin_root = map(Path, (station_home, shared_root, bin_root))
        for path in (home, shared_root, bin_root):
            if not path.is_absolute() or ".." in path.parts or path == Path("/"):
                raise SharedToolchainError("Explicit canonical non-root toolchain paths are required")
            SafeFS._assert_existing_absolute_chain(path)
        if shared_root.is_relative_to(home) or bin_root.is_relative_to(home):
            raise SharedToolchainError("Shared software must not live in the operator home")
        required = (*KEYS, *(("CODEX_CLI_VERSION",) if include_codex else ()))
        for key in required:
            pattern = r"[a-f0-9]{64}" if key == "CHATBOTX_CLI_ENTRY_SHA256" else r"[0-9]+(?:\.[0-9]+){1,3}"
            if not re.fullmatch(pattern, pins.get(key, "")):
                raise SharedToolchainError(f"Missing/invalid toolchain pin: {key}")
        owners = {station_uid}
        sources = _sources(home, pins, node_arch, include_codex, owners)
        _source_parents(home, sources, owners)
        entries, originals = _inventory(sources, owners)
        chatbotx_entry = entries.get("npm/chatbotx/dist/index.cjs", {})
        if (chatbotx_entry.get("type") != "file"
                or chatbotx_entry.get("sha256") != pins["CHATBOTX_CLI_ENTRY_SHA256"]):
            raise SharedToolchainError("Inventoried ChatbotX entrypoint differs from its reviewed SHA-256")
        exports = _exports(pins, include_codex)
        identity = {"schema_version": 1, "pins": pins, "node_arch": node_arch, "codex": include_codex}
        release_id = "v1-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        final = shared_root / release_id
        generated = {}
        for name, target in exports.items():
            if target not in entries:
                raise SharedToolchainError(f"Reviewed software entrypoint is missing: {name}")
            generated["bin/" + name] = _launcher(final, name, target)
        for name, data in generated.items():
            entries[name] = {"type": "file", "mode": 0o555, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        for name in list(entries):
            for parent in Path(name).parents:
                if str(parent) != ".":
                    entries.setdefault(str(parent), {"type": "directory", "mode": 0o555})
        manifest = {**identity, "release_id": release_id, "exports": exports, "files": entries,
                    "credentials": "NOT_SHARED"}
        for path in (shared_root, bin_root):
            _destination_parents(path, authority_uid)
            if path.exists():
                _checked(path, {authority_uid}, directory=True)
        _validate_public(bin_root, shared_root, exports, authority_uid)
        fs = SafeFS([shared_root, bin_root])
        fs.mkdir(shared_root, 0o755, (authority_uid, authority_gid))
        fs.mkdir(bin_root, 0o755, (authority_uid, authority_gid))
        if final.exists() or final.is_symlink():
            _verify_tree(final, manifest, authority_uid)
        else:
            stage = shared_root / (".staging-" + uuid.uuid4().hex)
            fs.mkdir(stage, 0o700, (authority_uid, authority_gid))
            # Keep failed candidates for explicit review; never recursively remove
            # a path supplied by the caller or an operator-writable source tree.
            for name, entry in sorted(entries.items(), key=lambda item: (len(Path(item[0]).parts), item[0])):
                target = stage / name
                if entry["type"] == "directory":
                    fs.mkdir(target, 0o755, (authority_uid, authority_gid))
                elif entry["type"] == "file":
                    data = generated[name] if name in generated else _read(originals[name], owners)
                    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                        raise SharedToolchainError("Operator software changed during publication")
                    fs.write_bytes(target, data, entry["mode"], (authority_uid, authority_gid))
                else:
                    with _directory(target.parent) as fd:
                        os.symlink(entry["target"], target.name, dir_fd=fd)
                        os.chown(target.name, authority_uid, authority_gid, dir_fd=fd, follow_symlinks=False)
            fs.write_text(stage / "MANIFEST.json", json.dumps(manifest, sort_keys=True) + "\n", 0o444,
                          (authority_uid, authority_gid))
            for name, entry in sorted(entries.items(), key=lambda item: len(Path(item[0]).parts), reverse=True):
                if entry["type"] == "directory":
                    fs.chmod(stage / name, 0o555)
            fs.chmod(stage, 0o555)
            with _directory(shared_root) as parent:
                _rename_noreplace(parent, stage.name, parent, final.name)
            _verify_tree(final, manifest, authority_uid)
        if probe is None:
            user = pwd.getpwuid(station_uid).pw_name
            _probe(final, exports, pins, user, station_uid, station_gid)
        else:
            probe(final, exports, pins)
        _verify_tree(final, manifest, authority_uid)
        _validate_public(bin_root, shared_root, exports, authority_uid)
        for name in exports:
            fs.replace_symlink(bin_root / name, str(final / "bin" / name), allowed_existing_prefix=str(shared_root) + "/")
        return {"schema_version": 1, "state": "SHARED_CODE_VERIFIED", "release_id": release_id,
                "root": str(final), "exports": exports, "credentials": "NOT_SHARED", "operational": False}
    except (OSError, ValueError, StationError) as exc:
        raise SharedToolchainError(str(exc)) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station-home", type=Path, required=True)
    parser.add_argument("--station-user", required=True)
    parser.add_argument("--node-arch", choices=("x64", "arm64"), required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--without-codex", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("shared toolchain publication requires root")
    account = pwd.getpwnam(args.station_user)
    if account.pw_uid == 0 or Path(account.pw_dir) != args.station_home:
        parser.error("operator identity does not match its non-root home")
    pins = {}
    for line in args.lock.read_text().splitlines():
        if re.fullmatch(r"[A-Z][A-Z0-9_]*=\S+", line):
            key, value = line.split("=", 1)
            pins[key] = value
    with install_lock(LayoutPaths.live(), new_operation_id()):
        result = publish_toolchain(station_home=args.station_home, station_uid=account.pw_uid,
                                   station_gid=account.pw_gid, pins=pins, node_arch=args.node_arch,
                                   include_codex=not args.without_codex)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (SharedToolchainError, KeyError) as exc:
        raise SystemExit("ERROR: shared toolchain publication failed: " + str(exc)) from None
