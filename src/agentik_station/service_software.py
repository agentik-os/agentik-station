"""Install immutable server software, never activate a service or enroll an account.

Only local root Podman's pull and image-inspect operations are permitted. A
receipt means all reviewed images are present, not that containers, databases,
listeners, migrations, credentials or Hermes bindings have been configured.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import subprocess
from pathlib import Path
from typing import Callable

from .errors import ReconcileError, SecurityError, ValidationError
from .filesystem import SafeFS
from .native_process import OUTPUT_LIMIT, run_bounded_native
from .os_runtime import require_root_owned_directory_chain

EVIDENCE_ROOT = Path("/var/lib/station/service-software")
PODMAN = Path("/usr/bin/podman")
ENV = Path("/usr/bin/env")
STORE = Path("/var/lib/containers/storage")
RUNROOT = Path("/run/containers/storage")
PLATFORM = "linux/amd64"
_ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_REFERENCE = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)+/(?:(?:[a-z0-9]+(?:[._-][a-z0-9]+)*)/)*"
                        r"[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[a-f0-9]{64}\Z")
_AUTH = '{"auths": {}}\n'
_MAX_JSON = 131072


def _absolute(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise SecurityError("Service software paths must be absolute without parent traversal")
    return path


def _chain(path: Path, *, privileged: bool) -> None:
    """Check every existing ancestor without following a symlink."""
    SafeFS._assert_existing_absolute_chain(path)
    existing = path
    while not existing.exists():
        existing = existing.parent
    if privileged:
        require_root_owned_directory_chain(existing)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Duplicate key in service software JSON")
        result[key] = value
    return result


def _read(path: Path, *, uid: int | None, private: bool = False) -> bytes:
    """Descriptor-relative bounded read; no links, FIFOs, or parent substitution."""
    _absolute(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(file_fd)
            forbidden = 0o077 if private else 0o022
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or (uid is not None and info.st_uid != uid) or info.st_mode & forbidden):
                raise SecurityError("Service software input must be a trusted single-link regular file")
            if info.st_size > _MAX_JSON:
                raise ValidationError("Service software JSON exceeds size limit")
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                data = stream.read(_MAX_JSON + 1)
            if len(data) > _MAX_JSON:
                raise ValidationError("Service software JSON exceeds size limit")
            return data
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


def _json(data: bytes | str) -> dict:
    try:
        value = json.loads(data, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as exc:
        raise ValidationError("Invalid service software JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("Service software JSON must be an object")
    return value


def _manifest(repo: Path, component: str, *, uid: int | None, privileged: bool) -> tuple[dict, str]:
    if not isinstance(component, str) or not _ID.fullmatch(component):
        raise ValidationError("Invalid service software component identifier")
    root = _absolute(repo) / "resources/services"
    _chain(root, privileged=privileged)
    try:
        data = _read(root / f"{component}.json", uid=uid)
    except FileNotFoundError:
        raise ValidationError("Service software manifest is missing from this release") from None
    value = _json(data)
    keys = {"schema_version", "id", "source", "platforms", "images", "configuration_required", "limitations"}
    if (set(value) != keys or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["id"] != component or value["platforms"] != [PLATFORM]
            or value["configuration_required"] is not True):
        raise ValidationError("Unsupported service software manifest identity/schema/platform")
    source = value["source"]
    if (not isinstance(source, dict) or set(source) != {"repository", "commit"}
            or not isinstance(source["repository"], str)
            or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source["repository"])
            or not isinstance(source["commit"], str) or not re.fullmatch(r"[a-f0-9]{40}", source["commit"])):
        raise ValidationError("Service software requires exact primary source provenance")
    images, limitations = value["images"], value["limitations"]
    if not isinstance(images, list) or not 1 <= len(images) <= 24:
        raise ValidationError("Service software requires a bounded nonempty image list")
    if (not isinstance(limitations, list) or not 1 <= len(limitations) <= 32
            or any(not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in limitations)):
        raise ValidationError("Service software requires explicit bounded limitations")
    names = set()
    for item in images:
        if (not isinstance(item, dict) or set(item) != {"name", "reference", "version", "role"}
                or any(not isinstance(text, str) or not text or len(text) > 1000 for text in item.values())
                or not _ID.fullmatch(item["name"]) or item["name"] in names
                or not _REFERENCE.fullmatch(item["reference"])
                or any(ord(char) < 32 for text in item.values() for char in text)):
            raise ValidationError("Service software image requires unique name and immutable qualified digest")
        names.add(item["name"])
    return value, hashlib.sha256(data).hexdigest()


def _context(evidence_root: Path, run: Callable | None, *, plan: bool) -> tuple[Path, int | None, bool]:
    root = _absolute(evidence_root)
    synthetic = run is not None
    if synthetic and (root == EVIDENCE_ROOT or EVIDENCE_ROOT in root.parents):
        raise SecurityError("An injected executor may not write canonical service evidence")
    privileged = not synthetic and not plan
    if privileged:
        if os.geteuid() != 0 or platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
            raise SecurityError("Service software installation/readback requires root on Linux AMD64")
        _trusted_executable(PODMAN)
        _trusted_executable(ENV, env_alias=True)
        for storage in (STORE, RUNROOT):
            _chain(storage, privileged=True)
    if not plan:
        _chain(root, privileged=privileged)
    return root, (None if plan else 0 if privileged else os.geteuid()), privileged


def _trusted_executable(path: Path, *, env_alias: bool = False) -> Path:
    """Allow only the named distro env alias, never a writable link chain.

    Ubuntu's Rust coreutils package installs /usr/bin/env as a root-owned
    symlink. Validate its original parent and link ownership, then its direct
    target's entire directory chain and regular executable. Execute the target,
    not the alias. Additional file/directory aliases remain forbidden here.
    """
    _chain(path.parent, privileged=True)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            if not env_alias or path != ENV or info.st_uid != 0:
                raise SecurityError("Only the root-owned distribution env alias is permitted")
            link = Path(os.readlink(path))
            path = Path(os.path.abspath(link if link.is_absolute() else path.parent / link))
            _chain(path.parent, privileged=True)
            info = path.lstat()
    except FileNotFoundError:
        raise ReconcileError("Required root Podman/native executable is not installed") from None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or not info.st_mode & 0o111:
        raise SecurityError("Expected trusted root-owned native executables")
    return path


def _private_directory(fs: SafeFS, path: Path, *, uid: int, create: bool = True) -> None:
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise SecurityError("Refusing to adopt a non-private service software directory")
    elif create:
        fs.mkdir(path, mode=0o700, owner=(uid, os.getegid()))


def _private_environment(base: Path) -> None:
    """No fallback Docker login, custom config or client certificates are adopted."""
    home = base / "home"
    if home.exists() and set(os.listdir(home)) - {"config", "cache"}:
        raise SecurityError("Refusing unexpected files in the private Podman HOME")
    for directory in (home / "config", base / "certs"):
        if directory.exists() and os.listdir(directory):
            raise SecurityError("Refusing existing Podman configuration or client certificates")


def _receipt(path: Path, expected: dict, *, uid: int | None, images: list) -> dict | None:
    try:
        receipt = _json(_read(path, uid=uid, private=True))
    except FileNotFoundError:
        return None
    if (set(receipt) != set(expected) | {"images"}
            or any(type(receipt.get(k)) is not type(v) or receipt.get(k) != v for k, v in expected.items())
            or not isinstance(receipt["images"], list) or len(receipt["images"]) != len(images)):
        raise SecurityError("Service software receipt drift; review before replacing existing evidence")
    for recorded, desired in zip(receipt["images"], images):
        if (not isinstance(recorded, dict) or set(recorded) != {"name", "reference", "image_id", "platform"}
                or recorded["name"] != desired["name"] or recorded["reference"] != desired["reference"]
                or recorded["platform"] != PLATFORM or not isinstance(recorded["image_id"], str)
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", recorded["image_id"])):
            raise SecurityError("Service software receipt image identity drift")
    return receipt


def _command(args: list[str], *, base: Path, run: Callable | None, timeout: int) -> subprocess.CompletedProcess:
    if not args or (args[0] != "pull" and args[:2] != ["image", "inspect"]):
        raise SecurityError("Only service software pull and image inspection are authorized")
    argv = [str(PODMAN), "--remote=false", "--root", str(STORE), "--runroot", str(RUNROOT), *args]
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": str(base / "home"),
           "XDG_CONFIG_HOME": str(base / "home/config"), "XDG_CACHE_HOME": str(base / "home/cache"),
           "REGISTRY_AUTH_FILE": str(base / "auth.json"), "LANG": "C.UTF-8"}
    try:
        if run is not None:
            result = run(argv, env=env, stdin=subprocess.DEVNULL, cwd="/",
                         capture_output=True, text=True, check=False, timeout=timeout)
        else:
            executable = _trusted_executable(ENV, env_alias=True)
            result = run_bounded_native([str(executable), "-i", *[f"{key}={value}" for key, value in env.items()], *argv],
                                        timeout=timeout, capture=args[0] == "image")
            if args[0] == "image":
                result.stdout = result.stdout.decode("utf-8")
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise ReconcileError("Podman service software operation failed; no service activation was attempted") from None
    if result.returncode != 0:
        raise ReconcileError("Podman service software operation failed; inspect/pull did not succeed")
    return result


def _inspect(item: dict, *, base: Path, run: Callable | None) -> dict:
    result = _command(["image", "inspect", "--", item["reference"]], base=base, run=run, timeout=60)
    try:
        if len(result.stdout.encode("utf-8")) > OUTPUT_LIMIT:
            raise ValueError("oversize")
        records = json.loads(result.stdout, object_pairs_hook=_unique_object)
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise ValueError("shape")
        image = records[0]
        digest = item["reference"].split("@", 1)[1]
        image_id = image["Id"].removeprefix("sha256:")
        repository_digests = image.get("RepoDigests")
        if (image.get("Os") != "linux" or image.get("Architecture") != "amd64"
                or image.get("Digest") != digest or not isinstance(repository_digests, list)
                or any(not isinstance(value, str) for value in repository_digests)
                or item["reference"] not in repository_digests
                or not _SHA.fullmatch(image_id)):
            raise ValueError("identity")
    except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
        raise ReconcileError(f"Podman digest/platform readback failed for {item['name']}") from None
    return {"name": item["name"], "reference": item["reference"], "image_id": "sha256:" + image_id,
            "platform": PLATFORM}


def _result(manifest: dict, digest: str, path: Path, *, state: str, images: list, installed: bool) -> dict:
    return {"component": manifest["id"], "state": state, "software_installed": installed,
            "configuration_required": True, "operational": False, "platform": PLATFORM,
            "manifest_sha256": digest, "evidence_path": str(path), "images": images,
            "limitations": manifest["limitations"]}


def _expected(component: str, digest: str) -> dict:
    return {"schema_version": 1, "component": component, "manifest_sha256": digest,
            "platform": PLATFORM, "software_installed": True, "configuration_required": True, "operational": False}


def install_bundle(repo: Path, component: str, *, evidence_root: Path = EVIDENCE_ROOT,
                   run: Callable | None = None, plan: bool = False) -> dict:
    """Pull all reviewed images; write evidence only after exact local readback."""
    root, uid, privileged = _context(evidence_root, run, plan=plan)
    manifest, digest = _manifest(repo, component, uid=uid, privileged=privileged)
    base = root / component
    path = base / "receipt.json"
    if plan:
        return _result(manifest, digest, path, state="PLANNED", images=manifest["images"], installed=False)
    _chain(base, privileged=privileged)
    expected = _expected(component, digest)
    previous = _receipt(path, expected, uid=uid, images=manifest["images"])
    fs = SafeFS([root])
    for directory in (root, base, base / "home", base / "home/config", base / "home/cache", base / "certs"):
        _private_directory(fs, directory, uid=uid)
    _private_environment(base)
    try:
        if _read(base / "auth.json", uid=uid, private=True) != _AUTH.encode():
            raise SecurityError("Refusing existing registry authentication material")
    except FileNotFoundError:
        fs.write_text(base / "auth.json", _AUTH, mode=0o600, owner=(uid, os.getegid()))
    observed = []
    for item in manifest["images"]:
        _command(["pull", "--quiet", "--platform=" + PLATFORM, "--tls-verify=true",
                  "--authfile", str(base / "auth.json"), "--cert-dir", str(base / "certs"), "--", item["reference"]],
                 base=base, run=run, timeout=1800)
        observed.append(_inspect(item, base=base, run=run))
    if _manifest(repo, component, uid=uid, privileged=privileged)[1] != digest:
        raise SecurityError("Service software manifest changed during installation")
    receipt = {**expected, "images": observed}
    current = _receipt(path, expected, uid=uid, images=manifest["images"])
    if current != previous or (previous is not None and previous != receipt):
        raise SecurityError("Service software receipt/image drift during installation")
    if previous is None:
        fs.write_text(path, json.dumps(receipt, indent=2, sort_keys=True) + "\n", mode=0o600, owner=(uid, os.getegid()))
    if _receipt(path, expected, uid=uid, images=manifest["images"]) != receipt:
        raise SecurityError("Service software receipt failed final readback")
    return _result(manifest, digest, path, state="SOFTWARE_INSTALLED", images=observed, installed=True)


def check_bundle(repo: Path, component: str, *, evidence_root: Path = EVIDENCE_ROOT,
                 run: Callable | None = None, plan: bool = False) -> dict:
    """Inspect local images and the bound receipt; never pull or repair drift."""
    root, uid, privileged = _context(evidence_root, run, plan=plan)
    manifest, digest = _manifest(repo, component, uid=uid, privileged=privileged)
    base, expected = root / component, _expected(component, digest)
    path = base / "receipt.json"
    if plan:
        return _result(manifest, digest, path, state="PLANNED", images=manifest["images"], installed=False)
    _chain(base, privileged=privileged)
    receipt = _receipt(path, expected, uid=uid, images=manifest["images"])
    fs = SafeFS([root])
    for directory in (root, base, base / "home", base / "home/config", base / "home/cache", base / "certs"):
        _private_directory(fs, directory, uid=uid, create=False)
    _private_environment(base)
    try:
        if _read(base / "auth.json", uid=uid, private=True) != _AUTH.encode():
            raise SecurityError("Refusing existing registry authentication material")
    except FileNotFoundError:
        pass
    observed, failures = [], []
    for item in manifest["images"]:
        try:
            observed.append(_inspect(item, base=base, run=run))
        except ReconcileError:
            failures.append({"name": item["name"], "reference": item["reference"], "verified": False})
    if _manifest(repo, component, uid=uid, privileged=privileged)[1] != digest:
        raise SecurityError("Service software manifest changed during readback")
    if _receipt(path, expected, uid=uid, images=manifest["images"]) != receipt:
        raise SecurityError("Service software receipt changed during readback")
    installed = receipt is not None and not failures and receipt["images"] == observed
    return _result(manifest, digest, path, state="SOFTWARE_INSTALLED" if installed else "NOT_VERIFIED",
                   images=observed + failures, installed=installed)
