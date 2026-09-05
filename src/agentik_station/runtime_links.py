"""Read-only, closed native-cache link policy; never a privileged-write waiver."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .paths import LayoutPaths


class RuntimeLinkError(ValueError):
    pass


ALIASES = {"applypatch", "apply_patch", "codex-execve-wrapper", "codex-linux-sandbox"}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,254}\Z")
NONCE = re.compile(r"codex-arg0[A-Za-z0-9_-]{6,64}\Z")
ARCHES = {"x64": ("x86_64", "codex-linux-x64"), "arm64": ("aarch64", "codex-linux-arm64")}


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _directory(path: Path, anchor: Path, owner: tuple[int, int], *, immutable=False):
    """Traverse real directories only and bind the observed owned path chain."""
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(anchor):
        raise RuntimeLinkError("Invalid runtime link anchor")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current = Path("/")
    chain = []
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            current /= part
            if current.is_relative_to(anchor):
                info = os.fstat(fd)
                access = 0o500 if immutable else 0o700
                if ((info.st_uid, info.st_gid) != owner or info.st_mode & 0o022
                        or info.st_mode & access != access):
                    raise RuntimeLinkError("Unsafe native-cache directory owner or permissions")
                if immutable and stat.S_IMODE(info.st_mode) != 0o555:
                    raise RuntimeLinkError("Shared executable directory is not immutable")
                chain.append((current, (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)))
        yield fd
        for directory, evidence in chain:
            observed = os.lstat(directory)
            if (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_uid, observed.st_gid) != evidence:
                raise RuntimeLinkError("Native-cache directory changed during readback")
    finally:
        os.close(fd)


def _read_regular(parent, name, owner, mode, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or (before.st_uid, before.st_gid) != owner
                or stat.S_IMODE(before.st_mode) != mode or before.st_size > limit):
            raise RuntimeLinkError("Unsafe shared-toolchain authority file")
        chunks = []
        size = 0
        while chunk := os.read(fd, min(1024 * 1024, limit + 1 - size)):
            size += len(chunk)
            if size > limit:
                raise RuntimeLinkError("Shared-toolchain authority file exceeds its limit")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (_identity(before) != _identity(after)
                or _identity(after) != _identity(os.stat(name, dir_fd=parent, follow_symlinks=False))):
            raise RuntimeLinkError("Shared-toolchain authority file changed during readback")
        return b"".join(chunks), after
    finally:
        os.close(fd)


def _codex_target(paths: LayoutPaths, target: str, cache: dict):
    authority = (os.getuid(), os.getgid()) if paths.test_mode else (0, 0)
    shared = paths.software / "tools/toolchain"
    candidate = Path(target)
    if not candidate.is_absolute() or ".." in candidate.parts or not candidate.is_relative_to(shared):
        raise RuntimeLinkError("Codex alias is not an exact shared-toolchain target")
    relative = candidate.relative_to(shared)
    if len(relative.parts) != 10 or not re.fullmatch(r"v1-[a-f0-9]{24}", relative.parts[0]):
        raise RuntimeLinkError("Codex alias target does not match its reviewed native layout")
    release = shared / relative.parts[0]
    with _directory(shared, paths.software, authority):
        pass
    with _directory(release, release, authority, immutable=True) as root_fd:
        manifest_bytes, manifest_info = _read_regular(root_fd, "MANIFEST.json", authority, 0o444, 64 * 1024 * 1024)
    manifest = json.loads(manifest_bytes)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("codex") is not True or manifest.get("credentials") != "NOT_SHARED"
            or not isinstance(manifest.get("pins"), dict) or manifest.get("node_arch") not in ARCHES
            or manifest.get("exports", {}).get("codex") != "npm/codex/bin/codex.js"):
        raise RuntimeLinkError("Invalid shared-toolchain manifest contract")
    identity = {key: manifest[key] for key in ("schema_version", "pins", "node_arch", "codex")}
    identifier = "v1-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    if manifest.get("release_id") != identifier or release.name != identifier:
        raise RuntimeLinkError("Shared-toolchain manifest identity differs from its release")
    machine, package = ARCHES[manifest["node_arch"]]
    expected = f"npm/codex/node_modules/@openai/{package}/vendor/{machine}-unknown-linux-musl/bin/codex"
    if str(candidate.relative_to(release)) != expected:
        raise RuntimeLinkError("Codex alias does not select the manifest's exact native architecture")
    files = manifest.get("files", {})
    entry = files.get(expected)
    if (not isinstance(entry, dict) or entry.get("type") != "file" or entry.get("mode") != 0o555
            or not isinstance(entry.get("size"), int) or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("sha256")))):
        raise RuntimeLinkError("Codex native executable is absent from the trusted manifest")
    for parent in Path(expected).parents:
        if str(parent) != "." and files.get(str(parent)) != {"type": "directory", "mode": 0o555}:
            raise RuntimeLinkError("Codex native parent is absent from the trusted manifest")
    with _directory(candidate.parent, release, authority, immutable=True) as parent:
        info = os.stat(candidate.name, dir_fd=parent, follow_symlinks=False)
        stamp = (str(candidate), _identity(info), _identity(manifest_info))
        if stamp not in cache:
            payload, info = _read_regular(parent, candidate.name, authority, 0o555, 512 * 1024 * 1024)
            if len(payload) != entry["size"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise RuntimeLinkError("Codex native executable differs from its trusted manifest")
            cache[stamp] = True


def _allowed(paths, link, state_root, owner, cache):
    home = state_root / "home"
    if owner is None or not link.is_relative_to(home):
        return False
    relative = link.relative_to(home).parts
    codex = (len(relative) == 5 and relative[:3] == (".codex", "tmp", "arg0")
             and NONCE.fullmatch(relative[3]) and relative[4] in ALIASES)
    uv = (len(relative) == 6 and relative[:4] == (".cache", "uv", "wheels-v6", "pypi")
          and all(TOKEN.fullmatch(part) for part in relative[4:]))
    if not codex and not uv:
        return False
    with _directory(link.parent, state_root, owner) as parent:
        before = os.stat(link.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISLNK(before.st_mode) or (before.st_uid, before.st_gid) != owner:
            raise RuntimeLinkError("Native cache alias has the wrong owner or type")
        target = os.readlink(link.name, dir_fd=parent)
        if codex:
            _codex_target(paths, target, cache)
        else:
            match = re.fullmatch(r"\.\./\.\./\.\./archive-v0/([A-Za-z0-9_-]{1,128})", target)
            if not match:
                raise RuntimeLinkError("uv wheel alias is not confined to its exact same-Zone archive")
            archive = home / ".cache/uv/archive-v0" / match.group(1)
            with _directory(archive, state_root, owner):
                pass
        if (_identity(before) != _identity(os.stat(link.name, dir_fd=parent, follow_symlinks=False))
                or os.readlink(link.name, dir_fd=parent) != target):
            raise RuntimeLinkError("Native cache alias changed during readback")
    return True


def audit_zone_links(paths: LayoutPaths, *, human: Path, state_root: Path,
                     owner: tuple[int, int] | None) -> dict:
    """Report links without deleting caches or relaxing any managed-write guard."""
    result = {"unsafe": [], "allowed": [], "errors": []}
    cache = {}

    def failed(error):
        raise RuntimeLinkError("Could not completely scan the Zone runtime") from error

    for root in (human, state_root):
        try:
            root_info = os.lstat(root)
            if not stat.S_ISDIR(root_info.st_mode):
                result["unsafe"].append(root)
                continue
            for current, directories, files in os.walk(root, followlinks=False, onerror=failed):
                for name in directories + files:
                    link = Path(current) / name
                    if not stat.S_ISLNK(os.lstat(link).st_mode):
                        continue
                    try:
                        approved = root == state_root and _allowed(paths, link, state_root, owner, cache)
                    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                        approved = False
                        result["errors"].append(f"{link}: {type(exc).__name__}")
                    result["allowed" if approved else "unsafe"].append(link)
        except (OSError, RuntimeLinkError) as exc:
            result["errors"].append(f"{root}: {type(exc).__name__}")
    return result
