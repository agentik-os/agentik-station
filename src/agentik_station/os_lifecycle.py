"""Resumable, Zone-local Hermes installation; never an operational acceptance.

The privileged ledger binds a bare native team to exactly one Project per Zone.
Zone-owned runtime projections and native command output are not authority.
"""
from __future__ import annotations

import grp
import hashlib
import json
import os
import pwd
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .doctor import _validate_local_zone_record, _validate_project_record
from .errors import SecurityError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_identifier, validate_version
from .installer import install_lock
from .models import new_operation_id
from .os_runtime import compile_os_to_hermes, require_root_owned_directory_chain
from .paths import LayoutPaths
from .receipts import utc_now

MAX_FILE = 2 * 1024 * 1024
MAX_TREE = 64 * 1024 * 1024
REPAIR = "Repair the named native profile without overwriting provider configuration, then rerun OS install."
NEXT_GATE = "Configure the Director and gateway, run OS verify, then prove fresh-session/provider/chat acceptance."
FIELDS = {
    "schema_version", "zone_id", "project_id", "os_id", "os_version", "project_root",
    "compiled_distribution", "bundle_sha256", "nano_director", "expected_profiles",
    "profile_states", "state", "verification", "operational", "updated_at", "next_repair_action",
}


def _profile_id(value: str) -> str:
    value = validate_identifier(value, "Hermes profile")
    if value in {"default", "hermes", "test", "tmp", "root", "sudo", "chat", "model", "gateway",
                 "setup", "whatsapp", "login", "logout", "status", "cron", "doctor", "dump", "config",
                 "pairing", "skills", "tools", "mcp", "sessions", "insights", "version", "update",
                 "uninstall", "profile", "plugins", "honcho", "acp"}:
        raise ValidationError("OS profile must not use a reserved native Hermes identity")
    return value


@contextmanager
def _directory(path: Path, *, uid: int | None = None, trusted_root: Path | None = None):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise SecurityError("Expected an absolute path without parent traversal")
    if trusted_root is not None and not path.is_relative_to(trusted_root):
        raise SecurityError("Path is outside its trusted anchor")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current = Path("/")
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            current /= part
            if uid is not None and current.is_relative_to(trusted_root or Path("/")):
                info = os.fstat(fd)
                if info.st_uid != uid or info.st_mode & 0o022:
                    raise SecurityError("Untrusted runtime metadata directory")
        yield fd
    finally:
        os.close(fd)


def _read_at(fd: int, name: str, *, uid: int, limit: int, immutable: bool = False) -> bytes:
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid:
            raise SecurityError("Expected a single-link regular file owned by the required identity")
        if immutable and info.st_mode & 0o022:
            raise SecurityError("Runtime authority may not be group/world writable")
        if info.st_size > limit:
            raise ValidationError("Runtime metadata exceeds its size limit")
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValidationError("Runtime metadata exceeds its size limit")
        return data
    finally:
        os.close(file_fd)


def _read_bytes(path: Path, *, uid: int, limit: int = MAX_FILE,
                immutable: bool = False, trusted_root: Path | None = None) -> bytes:
    with _directory(path.parent, uid=uid if immutable else None, trusted_root=trusted_root) as fd:
        return _read_at(fd, path.name, uid=uid, limit=limit, immutable=immutable)


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if not isinstance(key, str) or key in value:
            raise ValidationError("Runtime JSON contains duplicate or non-string keys")
        value[key] = item
    return value


def read_runtime_json(path: Path, *, uid: int, immutable: bool = False,
                      limit: int = 65536, trusted_root: Path | None = None) -> dict:
    """Bounded read-only, no-follow JSON reader; never creates missing anchors.

    With immutable=True, all directories from trusted_root (default '/') and the
    file must be owned by uid and not group/world writable. Mapped test layouts
    can supply their own anchor; production callers should keep the default.
    """
    try:
        value = json.loads(_read_bytes(Path(path), uid=uid, limit=limit, immutable=immutable,
                                      trusted_root=trusted_root), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValidationError("Non-finite JSON value")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("Invalid runtime JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("Expected a runtime JSON object")
    return value


def _yaml(data: bytes) -> dict:
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        return _unique_pairs([(loader.construct_object(key, deep=True), loader.construct_object(value, deep=True))
                              for key, value in node.value])

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        value = yaml.load(data, Loader=Loader)
    except (yaml.YAMLError, UnicodeError, RecursionError) as exc:
        raise ValidationError("Invalid native profile YAML") from exc
    if not isinstance(value, dict):
        raise ValidationError("Native profile YAML must be a mapping")
    return value


def _authority(paths: LayoutPaths) -> tuple[int, int]:
    return (os.getuid(), os.getgid()) if paths.test_mode else (0, 0)


def _trusted_json(path: Path, paths: LayoutPaths, anchor: Path) -> dict:
    return read_runtime_json(path, uid=_authority(paths)[0], immutable=True,
                             trusted_root=anchor if paths.test_mode else None)


def _ensure_authority_directory(fs: SafeFS, path: Path, paths: LayoutPaths, *, anchor: Path, mode: int) -> None:
    """Never repair/take over an untrusted publication parent during an install."""
    uid = _authority(paths)[0]
    current = anchor
    for part in (None, *path.relative_to(anchor).parts):
        if part is not None:
            current /= part
        try:
            with _directory(current, uid=uid, trusted_root=anchor if paths.test_mode else None):
                pass
        except FileNotFoundError:
            if current == anchor:
                raise ValidationError("Station authority anchor is missing; reconcile Station first") from None
            fs.mkdir(current, mode=mode, owner=_authority(paths))


def _context(paths: LayoutPaths, zone: dict, project_id: str | None = None) -> dict:
    zone_id = validate_identifier(zone.get("id"), "Zone id")
    record_path = paths.config / "zones.d" / f"{zone_id}.json"
    desired = _trusted_json(record_path, paths, paths.config)
    if desired != zone:
        raise SecurityError("Zone does not match its trusted desired record")
    try:
        spec, human, state, user = _validate_local_zone_record(
            desired, record_path=record_path, paths=paths, expected_host_id=None)
        entry = pwd.getpwnam(user)
        group = grp.getgrnam(user)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValidationError("Zone identity/layout is not canonically reconciled") from exc
    if (Path(entry.pw_dir) != state / "home" or entry.pw_gid != group.gr_gid
            or (not paths.test_mode and (entry.pw_uid == 0 or entry.pw_gid == 0
                or entry.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"}))):
        raise SecurityError("Zone Unix identity does not match its canonical home/group")
    for directory in (human, state, state / "home", state / "hermes"):
        with _directory(directory) as fd:
            info = os.fstat(fd)
            if info.st_uid != entry.pw_uid or info.st_mode & 0o022:
                raise SecurityError("Zone directory identity/permissions differ from its contract")
    context = {"zone": desired, "spec": spec, "uid": entry.pw_uid, "gid": entry.pw_gid, "user": user,
               "hermes_home": state / "hermes", "home": state / "home"}
    if project_id is not None:
        project_id = validate_identifier(project_id, "Project id")
        project = human / "projects" / project_id
        with _directory(project) as fd:
            if os.fstat(fd).st_uid != entry.pw_uid:
                raise SecurityError("Project is not owned by its Zone identity")
        payload = read_runtime_json(project / "PROJECT.json", uid=entry.pw_uid)
        try:
            _validate_project_record(payload, zone=spec, project_path=project, paths=paths)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValidationError("Project does not match its canonical Zone scope") from exc
        context["project_root"] = project
    return context


def _tree(root: Path, *, uid: int, immutable: bool = False, trusted_root: Path | None = None) -> dict[str, bytes | None]:
    result, total = {}, 0
    def fail(error):
        raise error
    with _directory(root, uid=uid if immutable else None, trusted_root=trusted_root) as root_fd:
        for current, dirs, files, fd in os.fwalk(".", dir_fd=root_fd, follow_symlinks=False, onerror=fail):
            for name in sorted(dirs):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or (immutable and info.st_mode & 0o222):
                    raise SecurityError("Bundle contains an unsafe directory")
                result[(Path(current) / name).as_posix() + "/"] = None
            for name in sorted(files):
                data = _read_at(fd, name, uid=uid, limit=MAX_FILE, immutable=immutable)
                total += len(data)
                result[(Path(current) / name).as_posix()] = data
            if total > MAX_TREE or len(result) > 5000:
                raise ValidationError("OS bundle exceeds the bounded local readback limit")
    return result


def _digest(tree: dict[str, bytes | None]) -> str:
    entries = [(name, hashlib.sha256(data).hexdigest() if data is not None else None)
               for name, data in sorted(tree.items())]
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


def _ledger_path(paths: LayoutPaths, zone_id: str, os_id: str) -> Path:
    return paths.varlib / "registry" / "os" / zone_id / f"{os_id}.json"


def _manifest(root: Path, paths: LayoutPaths, record: dict) -> tuple[dict, dict]:
    tree = _tree(root, uid=_authority(paths)[0], immutable=True,
                 trusted_root=paths.software if paths.test_mode else None)
    manifest = _trusted_json(root / "COMPILED.json", paths, paths.software)
    profiles = manifest.get("profiles")
    if (manifest.get("schema_version") != record["schema_version"] or not isinstance(profiles, list) or not profiles
            or not all(isinstance(x, str) for x in profiles)
            or len(profiles) != len(set(profiles)) or manifest.get("nano_director") not in profiles):
        raise ValidationError("Compiled team is incomplete or ambiguous")
    for profile in profiles:
        _profile_id(profile)
    binding_fields = ("workspace_root", "zone_id", "instance_id", "organization_id", "allowed_project_ids", "role_profile_map") if record["schema_version"] == 3 else ("project_root",)
    for field in ("os_id", "os_version", "nano_director", *binding_fields):
        if manifest.get(field) != record.get(field):
            raise SecurityError("Compiled OS identity differs from its trusted ledger")
    if profiles != record.get("expected_profiles") or _digest(tree) != record.get("bundle_sha256"):
        raise SecurityError("Compiled OS bytes/team differ from its trusted ledger")
    return manifest, tree


def _read_record(paths: LayoutPaths, context: dict, os_id: str) -> dict:
    zone_id = context["zone"]["id"]
    record = _trusted_json(_ledger_path(paths, zone_id, os_id), paths, paths.varlib)
    if (set(record) != FIELDS or record.get("schema_version") != 2
            or record.get("zone_id") != zone_id or record.get("os_id") != os_id
            or record.get("operational") is not False):
        raise ValidationError("Unsupported or invalid trusted OS ledger")
    project_id = validate_identifier(record.get("project_id"), "Project id")
    version = validate_version(record.get("os_version"))
    project = Path(context["zone"]["human_root"]) / "projects" / project_id
    compiled = paths.software / "os-distributions" / zone_id / project_id / os_id / version
    if record.get("project_root") != str(project) or record.get("compiled_distribution") != str(compiled):
        raise SecurityError("OS ledger paths do not match canonical Zone/Project scope")
    profiles, states = record.get("expected_profiles"), record.get("profile_states")
    if (not isinstance(profiles, list) or not profiles or not all(isinstance(x, str) for x in profiles)
            or len(set(profiles)) != len(profiles) or not isinstance(states, dict) or set(states) != set(profiles)
            or record.get("state") not in {"INSTALLABLE", "CONFIGURED", "VERIFIED", "DEGRADED"}
            or not isinstance(record.get("verification"), dict)):
        raise ValidationError("OS ledger must contain the exact complete team")
    for profile in profiles:
        _profile_id(profile)
        value = states[profile]
        if (not isinstance(value, dict) or set(value) != {"state", "returncode", "reason"}
                or value["state"] not in {"PENDING", "INSTALLING", "INSTALLED", "FAILED"}
                or (value["returncode"] is not None and type(value["returncode"]) is not int)
                or not isinstance(value["reason"], str)):
            raise ValidationError("Invalid per-profile checkpoint")
    _manifest(compiled, paths, record)
    return record


def _profile_present(context: dict, profile: str) -> bool:
    root = context["hermes_home"] / "profiles"
    # Pinned Hermes stores deletion markers beside the profile, not inside it.
    try:
        with _directory(root / ".deleted") as fd:
            os.stat(profile, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise ValidationError("Native profile has been tombstoned; explicit repair is required")
    try:
        with _directory(root) as fd:
            info = os.stat(profile, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != context["uid"]:
                raise SecurityError("Native profile path is unsafe or owned by another identity")
            return True
    except FileNotFoundError:
        return False


def _readback(record: dict, profile: str, context: dict, paths: LayoutPaths) -> str:
    """Read only known distribution data; never .env, authentication or sessions."""
    source = Path(record["compiled_distribution"]) / "profiles" / profile
    native = context["hermes_home"] / "profiles" / profile
    expected = _tree(source, uid=_authority(paths)[0], immutable=True,
                     trusted_root=paths.software if paths.test_mode else None)
    if not _profile_present(context, profile):
        raise ValidationError("Native profile is missing")
    for relative, data in expected.items():
        if relative in {"config.yaml", "distribution.yaml"}:
            continue
        target = native / relative.rstrip("/")
        if data is None:
            with _directory(target) as fd:
                if os.fstat(fd).st_uid != context["uid"]:
                    raise SecurityError("Native distribution directory belongs to another identity")
        elif _read_bytes(target, uid=context["uid"]) != data:
            raise ValidationError("Native distribution content differs from the published bundle")
    installed = _yaml(_read_bytes(native / "distribution.yaml", uid=context["uid"]))
    wanted = _yaml(expected["distribution.yaml"])
    owned = installed.get("distribution_owned")
    if (installed.get("name") != profile or str(installed.get("version")) != record["os_version"]
            or installed.get("source") != str(source) or not installed.get("installed_at")
            or not isinstance(owned, list) or not all(isinstance(x, str) for x in owned)
            or sorted(x.rstrip("/") for x in owned) != sorted(x.rstrip("/") for x in wanted["distribution_owned"])):
        raise ValidationError("Native installed distribution identity/source is not the expected bundle")
    config_data = _read_bytes(native / "config.yaml", uid=context["uid"])
    config, required = _yaml(config_data), _yaml(expected["config.yaml"])
    terminal, identity, plugins = config.get("terminal", {}), config.get("profile", {}), config.get("plugins", {})
    if (not all(isinstance(x, dict) for x in (terminal, identity, plugins))
            or identity.get("id") != profile or terminal.get("cwd") != record.get("workspace_root", record.get("project_root"))
            or terminal.get("home_mode") != "profile"):
        raise ValidationError("Native profile has an unsafe Project binding")
    enabled, entries = plugins.get("enabled"), plugins.get("entries")
    if not isinstance(enabled, list) or not isinstance(entries, dict):
        raise ValidationError("Required OS plugins are not configured")
    for name in required["plugins"]["enabled"]:
        if name not in enabled or not isinstance(entries.get(name), dict) or entries[name].get("allow_tool_override") is not False:
            raise ValidationError("Required OS plugin policy differs from the compiled contract")
    return hashlib.sha256(config_data).hexdigest()


def load_os_runtime_record(paths: LayoutPaths, *, zone: dict, os_id: str,
                           require_configured: bool = False) -> dict:
    """Read trusted local installation evidence, with no filesystem mutations."""
    os_id = validate_identifier(os_id, "OS id")
    context = _context(paths, zone)
    record = _read_record(paths, context, os_id)
    if require_configured:
        context = _context(paths, zone, record["project_id"])
        if record["state"] not in {"CONFIGURED", "VERIFIED", "DEGRADED"} or any(
                value["state"] != "INSTALLED" for value in record["profile_states"].values()):
            raise ValidationError("OS team is not completely installed; resume OS install first")
        hashes = {profile: _readback(record, profile, context, paths) for profile in record["expected_profiles"]}
        if record["state"] == "VERIFIED" and record["verification"].get("config_sha256") != hashes:
            record["state"] = "CONFIGURED"
            record["verification"] = {"state": "STALE", "reason": "Native configuration changed; rerun OS verify."}
            record["next_repair_action"] = NEXT_GATE
    return record


def _save(paths: LayoutPaths, record: dict) -> None:
    path = _ledger_path(paths, record["zone_id"], record["os_id"])
    fs = SafeFS(paths.allowed_roots)
    owner = _authority(paths)
    for parent in (paths.varlib / "registry", paths.varlib / "registry/os", path.parent):
        try:
            with _directory(parent, uid=owner[0], trusted_root=paths.varlib if paths.test_mode else None):
                pass
        except FileNotFoundError:
            fs.mkdir(parent, mode=0o700, owner=owner)
    record["updated_at"] = utc_now()
    fs.write_text(path, json.dumps(record, indent=2, sort_keys=True) + "\n", mode=0o600, owner=owner)


def _native(context: dict, hermes_binary: str, runuser_binary: str, args: list[str]) -> int:
    # Native output may contain credentials/configuration. Discard it, even on errors.
    argv = [runuser_binary, "--user", context["user"], "--", "/usr/bin/env", "-i",
            f"HOME={context['home']}", f"HERMES_HOME={context['hermes_home']}",
            "PATH=/usr/local/bin:/usr/bin:/bin", hermes_binary, *args]
    try:
        return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False, timeout=300).returncode
    except subprocess.TimeoutExpired:
        return 124
    except OSError:
        return 127


def install_os_runtime(source: Path, *, paths: LayoutPaths, zone: dict, project_id: str,
                       os_id: str, os_version: str, hermes_binary: str, runuser_binary: str) -> dict:
    os_id, os_version = validate_identifier(os_id, "OS id"), validate_version(os_version)
    context = _context(paths, zone, project_id)
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("OS installation requires the Station root authority")
    with install_lock(paths, new_operation_id()):
        path = _ledger_path(paths, zone["id"], os_id)
        try:
            record = _read_record(paths, context, os_id)
        except FileNotFoundError:
            # Missing published content is not permission to replace a present ledger.
            try:
                with _directory(path.parent) as fd:
                    os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                record = None
            else:
                raise ValidationError("Tracked OS bundle is missing; restore its immutable publication")
        except NotADirectoryError:
            raise SecurityError("Unsafe OS ledger directory") from None
        except OSError:
            raise
        else:
            if record["project_id"] != project_id or record["os_version"] != os_version:
                raise ValidationError("This OS is already bound to another Project/version in this Zone; explicit migration is required")
        # The first ledger may not exist yet; the dedicated helper distinguishes this
        # from a tracked ledger whose publication is missing.
        return _install_locked(source, paths, context, project_id, os_id, os_version,
                               hermes_binary, runuser_binary, record)


def _install_locked(source, paths, context, project_id, os_id, os_version, hermes_binary, runuser_binary, record):
    final = paths.software / "os-distributions" / context["zone"]["id"] / project_id / os_id / os_version
    fs, owner = SafeFS(paths.allowed_roots), _authority(paths)
    if not paths.test_mode:
        require_root_owned_directory_chain(paths.software)
    stage_parent = paths.staging / "os"
    _ensure_authority_directory(fs, stage_parent, paths, anchor=paths.software, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix="runtime-", dir=stage_parent))
    output = stage / "compiled"
    try:
        compiled = compile_os_to_hermes(source, output, project_root=context["project_root"])
        if compiled["os_id"] != os_id or compiled["os_version"] != os_version:
            raise ValidationError("Canonical OS source differs from requested package/version")
        digest = _digest(_tree(output, uid=owner[0]))
        if record is not None and digest != record["bundle_sha256"]:
            raise ValidationError("Same-version compiled bundle changed; explicit migration is required")
        profiles = compiled["profiles"]
        if not profiles or len(profiles) != len(set(profiles)) or compiled["nano_director"] not in profiles:
            raise ValidationError("Compiled team must contain one Director and unique native profiles")
        for profile in profiles:
            _profile_id(profile)
        if record is None:
            from .os_instances import check_instance_reservations
            check_instance_reservations(paths, context["zone"], profiles)
            for profile in profiles:
                if _profile_present(context, profile):
                    raise ValidationError("Untracked native profile already occupies an OS team name; explicit adoption/repair is required")
            ledger_root = _ledger_path(paths, context["zone"]["id"], os_id).parent
            try:
                with _directory(ledger_root, uid=owner[0], trusted_root=paths.varlib if paths.test_mode else None) as fd:
                    names = os.listdir(fd)
            except FileNotFoundError:
                names = []
            for name in names:
                if not name.endswith(".json"):
                    raise SecurityError("Unexpected OS reservation entry")
                other_id = validate_identifier(name[:-5], "reserved OS id")
                other = _read_record(paths, context, other_id)
                if set(other["expected_profiles"]) & set(profiles):
                    raise ValidationError("Another OS reserves the same native profile names in this Zone")
        _ensure_authority_directory(fs, final.parent, paths, anchor=paths.software, mode=0o755)
        if not paths.test_mode:
            require_root_owned_directory_chain(final.parent)
        try:
            published = _tree(final, uid=owner[0], immutable=True,
                              trusted_root=paths.software if paths.test_mode else None)
        except FileNotFoundError:
            fs.freeze_tree(output)
            # macOS requires owner-write on a moved directory; publication parents
            # are authority-only, so this never grants the Zone a writable bundle.
            fs.chmod(output, 0o755)
            os.replace(output, final)
            fs.chmod(final, 0o555)
        else:
            if _digest(published) != digest:
                raise ValidationError("Published same-version OS bundle differs; no overwrite is allowed")
        if record is None:
            record = {"schema_version": 2, "zone_id": context["zone"]["id"], "project_id": project_id,
                      "os_id": os_id, "os_version": os_version, "project_root": str(context["project_root"]),
                      "compiled_distribution": str(final), "bundle_sha256": digest,
                      "nano_director": compiled["nano_director"], "expected_profiles": profiles,
                      "profile_states": {p: {"state": "PENDING", "returncode": None, "reason": "Not attempted"} for p in profiles},
                      "state": "INSTALLABLE", "verification": {}, "operational": False,
                      "updated_at": utc_now(), "next_repair_action": "Resume OS install."}
        return _install_profiles(record, context, paths, hermes_binary, runuser_binary, save=_save)
    finally:
        fs.remove_tree_strict(stage)


def _install_profiles(record: dict, context: dict, paths: LayoutPaths, hermes_binary: str,
                      runuser_binary: str, *, save, validate_context=lambda: None) -> dict:
    """One native install/resume engine for validated legacy and instance targets.

    Callers hold install_lock and have validated the record, runtime target and
    immutable publication. The callback persists only that target's authority.
    """
    previously_configured = record["state"] in {"CONFIGURED", "VERIFIED", "DEGRADED"}
    record["verification"] = {}
    record["state"] = "INSTALLABLE"
    save(paths, record)
    for profile in record["expected_profiles"]:
        validate_context()
        checkpoint = record["profile_states"][profile]
        if _profile_present(context, profile):
            try:
                _readback(record, profile, context, paths)
            except (OSError, ValidationError, SecurityError):
                checkpoint.update(state="FAILED", reason="Existing profile failed local readback; explicit repair required")
                record.update(state="DEGRADED" if previously_configured else "INSTALLABLE", next_repair_action=REPAIR)
                save(paths, record)
                return record
            checkpoint.update(state="INSTALLED", reason="Complete native distribution read back")
            save(paths, record)
            continue
        checkpoint.update(state="INSTALLING", returncode=None, reason="Native install started")
        save(paths, record)
        code = _native(context, hermes_binary, runuser_binary,
                       ["--profile", "default", "profile", "install", str(Path(record["compiled_distribution"]) / "profiles" / profile), "--name", profile, "--yes"])
        checkpoint["returncode"] = code
        validate_context()
        try:
            _readback(record, profile, context, paths)
            complete = True
        except (OSError, ValidationError, SecurityError):
            complete = False
        if code != 0 or not complete:
            checkpoint.update(state="FAILED", reason="Native install failed" if code else "Native install returned success without complete local readback")
            record.update(state="DEGRADED" if previously_configured else "INSTALLABLE", next_repair_action=REPAIR)
            save(paths, record)
            return record
        checkpoint.update(state="INSTALLED", reason="Native install and complete local readback passed")
        save(paths, record)
    # A later startup can change an earlier profile: verify the final whole team.
    for profile in record["expected_profiles"]:
        validate_context()
        try:
            _readback(record, profile, context, paths)
        except (OSError, ValidationError, SecurityError):
            record["profile_states"][profile].update(state="FAILED", reason="Final complete-team readback failed")
            record.update(state="DEGRADED" if previously_configured else "INSTALLABLE", next_repair_action=REPAIR)
            save(paths, record)
            return record
    validate_context()
    record.update(state="CONFIGURED", next_repair_action=NEXT_GATE)
    save(paths, record)
    return record


def verify_os_runtime(paths: LayoutPaths, *, zone: dict, os_id: str,
                      hermes_binary: str, runuser_binary: str) -> dict:
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("OS verification requires the Station root authority")
    with install_lock(paths, new_operation_id()):
        record = load_os_runtime_record(paths, zone=zone, os_id=os_id, require_configured=True)
        context = _context(paths, zone, record["project_id"])
        return _verify_profiles(record, context, paths, hermes_binary, runuser_binary, save=_save)


def _verify_profiles(record: dict, context: dict, paths: LayoutPaths, hermes_binary: str,
                     runuser_binary: str, *, save, validate_context=lambda: None) -> dict:
    """Native full-team Doctor plus local file readback; no external acceptance."""
    checks, hashes, passed = {}, {}, True
    for profile in record["expected_profiles"]:
        validate_context()
        code = _native(context, hermes_binary, runuser_binary, ["--profile", profile, "doctor"])
        validate_context()
        try:
            hashes[profile] = _readback(record, profile, context, paths)
            complete = True
        except (OSError, ValidationError, SecurityError):
            complete = False
        checks[profile] = {"returncode": code, "reason": "Doctor and local readback passed" if code == 0 and complete else "Doctor or local readback failed"}
        passed = passed and code == 0 and complete
    for profile in record["expected_profiles"]:
        validate_context()
        try:
            hashes[profile] = _readback(record, profile, context, paths)
        except (OSError, ValidationError, SecurityError):
            passed = False
            checks[profile]["reason"] = "Final complete-team readback failed"
    validate_context()
    record["verification"] = {"state": "PASSED" if passed else "FAILED", "checked_at": utc_now(),
                              "profiles": checks, "config_sha256": hashes,
                              "claim": "LOCAL_PROFILE_DOCTOR_ONLY_NOT_EXTERNAL_ACCEPTANCE"}
    record.update(state="VERIFIED" if passed else "DEGRADED", operational=False,
                  next_repair_action="Prove fresh-session/provider/chat acceptance; no operational claim." if passed else REPAIR)
    save(paths, record)
    return record
