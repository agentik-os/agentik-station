"""Read-only, closed native runtime link policy; never a privileged-write waiver."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .paths import LayoutPaths
from .errors import StationError
from .identifiers import validate_identifier


class RuntimeLinkError(ValueError):
    pass


ALIASES = {"applypatch", "apply_patch", "codex-execve-wrapper", "codex-linux-sandbox"}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,254}\Z")
NONCE = re.compile(r"codex-arg0[A-Za-z0-9_-]{6,64}\Z")
ARCHES = {"x64": ("x86_64", "codex-linux-x64"), "arm64": ("aarch64", "codex-linux-arm64")}
SYSTEMD_PARENT = (".config", "systemd", "user", "default.target.wants")


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


def _systemd_fields(payload: bytes) -> dict:
    """Read a bounded pinned-native unit grammar, not general systemd syntax.

    Provenance: NousResearch/hermes-agent@29112bef099274229cadff79cdff7bf7b99c4b77,
    hermes_cli/gateway.py:generate_systemd_unit/get_systemd_unit_path/systemd_install.
    This checks link scope, not the service's runtime safety or readiness.
    """
    keys = {
        "Unit": {"Description", "After", "Wants", "StartLimitIntervalSec"},
        "Service": {"Type", "NotifyAccess", "WatchdogSec", "ExecStart", "WorkingDirectory", "Environment",
                    "Restart", "RestartSec", "RestartForceExitStatus", "RestartPreventExitStatus", "KillMode",
                    "KillSignal", "ExecReload", "ExecStopPost", "TimeoutStopSec", "StandardOutput", "StandardError"},
        "Install": {"WantedBy"},
    }
    result, section = {}, None
    for raw in payload.decode("utf-8").splitlines():
        if any(ord(char) < 32 for char in raw) or "\\" in raw:
            raise RuntimeLinkError("Unsupported native user-unit syntax")
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            section = line[1:-1]
            if line != f"[{section}]" or section not in keys or section in result:
                raise RuntimeLinkError("Unsupported or repeated native user-unit section")
            result[section] = {}
            continue
        key, separator, value = line.partition("=")
        if section is None or not separator or key not in keys[section]:
            raise RuntimeLinkError("Unsupported native user-unit directive")
        if key == "Environment":
            match = re.fullmatch(r'"(PATH|VIRTUAL_ENV|HERMES_HOME|HERMES_SUPERVISED_CHILD)=([^"%]*)"', value)
            if not match:
                raise RuntimeLinkError("Unsupported native user-unit environment")
            key, value = match.groups()
        if key in result[section]:
            raise RuntimeLinkError("Repeated native user-unit directive")
        result[section][key] = value
    if set(result) != set(keys):
        raise RuntimeLinkError("Incomplete native user-unit sections")
    return result


def _installed_systemd_home(paths, human, state_root, profile, home_value, owner):
    """Select only a canonical Zone root or a trusted installed OS team member."""
    from . import os_lifecycle as lifecycle

    base = state_root / "hermes"
    if profile is None:
        if home_value != str(base):
            raise RuntimeLinkError("Default user unit does not select its Zone Hermes root")
        return base
    validate_identifier(profile, "Native service profile")
    zone = lifecycle._trusted_json(paths.config / "zones.d" / f"{state_root.name}.json", paths, paths.config)
    if zone.get("state_root") != str(state_root) or zone.get("human_root") != str(human):
        raise RuntimeLinkError("User unit Zone differs from its trusted scope")
    home = Path(home_value)
    if home_value == str(base / "profiles" / profile):
        # Legacy installed OS profiles still share the Zone-base Hermes root.
        records = paths.varlib / "registry/os" / state_root.name
        authority = lifecycle._authority(paths)
        with lifecycle._directory(records, uid=authority[0],
                                  trusted_root=paths.varlib if paths.test_mode else None) as fd:
            names = os.listdir(fd)
        if len(names) > 100:
            raise RuntimeLinkError("Too many legacy OS records for bounded link verification")
        matches = 0
        for name in names:
            if not name.endswith(".json"):
                raise RuntimeLinkError("Unexpected legacy OS authority entry")
            os_id = validate_identifier(name[:-5], "OS id")
            record = lifecycle.load_os_runtime_record(paths, zone=zone, os_id=os_id, require_configured=True)
            matches += profile in record["expected_profiles"]
        if matches != 1:
            raise RuntimeLinkError("Named user unit does not select one installed OS profile")
    else:
        from .os_instances import load_os_instance_record

        relative = home.relative_to(state_root)
        if (len(relative.parts) != 5 or relative.parts[0] != "os-instances"
                or relative.parts[2:] != ("hermes", "profiles", profile)):
            raise RuntimeLinkError("User unit does not select a canonical instance profile")
        instance = validate_identifier(relative.parts[1], "OS instance id")
        record = load_os_instance_record(paths, zone=zone, instance_id=instance, require_configured=True)
        if (profile not in record["expected_profiles"]
                or home_value != str(Path(record["hermes_home"]) / "profiles" / profile)):
            raise RuntimeLinkError("User unit profile is not installed in its selected instance")
    with _directory(home, state_root, owner):
        pass
    return home


def _systemd_target(paths, link, target, human, state_root, owner):
    unit_directory = link.parent.parent
    unit_path = unit_directory / link.name
    if target not in {str(unit_path), f"../{link.name}"}:
        raise RuntimeLinkError("User-service enablement link must select its exact sibling unit")
    match = re.fullmatch(r"hermes-gateway(?:-([a-z][a-z0-9-]{0,47}))?\.service", link.name)
    if not match:
        raise RuntimeLinkError("Unsupported native service name")
    profile = match.group(1)
    with _directory(unit_directory, state_root, owner) as unit_parent:
        info = os.stat(link.name, dir_fd=unit_parent, follow_symlinks=False)
        mode = stat.S_IMODE(info.st_mode)
        if mode not in {0o600, 0o640, 0o644}:
            raise RuntimeLinkError("Unsafe native user-unit permissions")
        payload, info = _read_regular(unit_parent, link.name, owner, mode, 64 * 1024)
        fields = _systemd_fields(payload)
        service = fields["Service"]
        home_value = service.get("HERMES_HOME", "")
        home = _installed_systemd_home(paths, human, state_root, profile, home_value, owner)
        with _directory(home, state_root, owner):
            pass
        python = str(paths.software / "tools/hermes/current/venv/bin/python")
        expected_start = f"{python} -m hermes_cli.main" + (f" --profile {profile}" if profile else "") + " gateway run"
        if (service.get("ExecStart") != expected_start or service.get("WorkingDirectory") != str(home)
                or service.get("ExecStopPost") != f"-{python} -m gateway.cgroup_cleanup"
                or service.get("ExecReload") != "/bin/kill -USR1 $MAINPID"
                or service.get("HERMES_SUPERVISED_CHILD") != "1"
                or service.get("Type") not in {"simple", "notify"}
                or fields["Install"] != {"WantedBy": "default.target"}):
            raise RuntimeLinkError("Native user unit does not match the scoped gateway contract")
        if _identity(info) != _identity(os.stat(link.name, dir_fd=unit_parent, follow_symlinks=False)):
            raise RuntimeLinkError("Native user unit changed during readback")


def _allowed(paths, link, human, state_root, owner, cache):
    home = state_root / "home"
    if owner is None or not link.is_relative_to(home):
        return False
    relative = link.relative_to(home).parts
    codex = (len(relative) == 5 and relative[:3] == (".codex", "tmp", "arg0")
             and NONCE.fullmatch(relative[3]) and relative[4] in ALIASES)
    uv = (len(relative) == 6 and relative[:4] == (".cache", "uv", "wheels-v6", "pypi")
          and all(TOKEN.fullmatch(part) for part in relative[4:]))
    systemd = len(relative) == 5 and relative[:4] == SYSTEMD_PARENT
    if not codex and not uv and not systemd:
        return False
    with _directory(link.parent, state_root, owner) as parent:
        before = os.stat(link.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISLNK(before.st_mode) or (before.st_uid, before.st_gid) != owner:
            raise RuntimeLinkError("Native cache alias has the wrong owner or type")
        target = os.readlink(link.name, dir_fd=parent)
        if codex:
            _codex_target(paths, target, cache)
        elif uv:
            match = re.fullmatch(r"\.\./\.\./\.\./archive-v0/([A-Za-z0-9_-]{1,128})", target)
            if not match:
                raise RuntimeLinkError("uv wheel alias is not confined to its exact same-Zone archive")
            archive = home / ".cache/uv/archive-v0" / match.group(1)
            with _directory(archive, state_root, owner):
                pass
        else:
            _systemd_target(paths, link, target, human, state_root, owner)
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
                        approved = root == state_root and _allowed(paths, link, human, state_root, owner, cache)
                    except (OSError, ValueError, TypeError, KeyError, AttributeError, StationError) as exc:
                        approved = False
                        result["errors"].append(f"{link}: {type(exc).__name__}")
                    result["allowed" if approved else "unsafe"].append(link)
        except (OSError, RuntimeLinkError) as exc:
            result["errors"].append(f"{root}: {type(exc).__name__}")
    return result
