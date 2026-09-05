"""First-class OS instances on native Hermes; the Zone remains the Unix boundary.

Instance declarations and checkpoints are root-owned. Instance files share their
Zone UID; allowed Projects are declared scope, not a new filesystem sandbox.
Legacy schema-2 Project-owned OS records are never adopted or rewritten here.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import os_lifecycle as lifecycle
from .errors import SecurityError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_identifier, validate_version
from .installer import install_lock
from .models import new_operation_id
from .os_runtime import compile_os_to_hermes, instance_profile_map
from .paths import LayoutPaths
from .receipts import utc_now

FIELDS = (lifecycle.FIELDS - {"project_id", "project_root"}) | {
    "instance_id", "organization_id", "allowed_project_ids", "workspace_root", "hermes_home",
    "role_profile_map", "runtime_roots", "runtime_state",
}
ROOT_REPAIR = "Inspect the instance's exact human/runtime roots and ledger; partial or replaced roots are never adopted or overwritten."
RUNTIME_DIRECTORIES = ("human", "state", "workspace_root", "hermes_home")


def instance_paths(paths: LayoutPaths, zone: dict, instance_id: str) -> dict[str, Path]:
    """Derive paths only from a canonically validated Zone (never arbitrary overrides)."""
    instance_id = validate_identifier(instance_id, "OS instance id")
    zone_id = validate_identifier(zone.get("id"), "Zone id")
    human = Path(zone["human_root"]) / "os/instances" / instance_id
    state = paths.zones_state / zone_id / "os-instances" / instance_id
    return {"human": human, "state": state, "workspace_root": human / "workspace",
            "hermes_home": state / "hermes",
            "ledger": paths.varlib / "registry/os-instances" / zone_id / f"{instance_id}.json"}


def _declaration(paths: LayoutPaths, zone: dict, organization_id, project_ids) -> tuple[dict, list[str]]:
    context = lifecycle._context(paths, zone)
    if context["spec"].category == "ORGANIZATIONS":
        if organization_id is None:
            raise ValidationError("Organization-owned OS instances require an explicit organization_id")
        organization_id = validate_identifier(organization_id, "Organization id")
        from .organizations import validate_organization_zone
        validate_organization_zone(paths, organization_id=organization_id, zone=zone)
    elif organization_id is not None:
        raise ValidationError("A non-Organization Zone cannot claim an Organization owner")
    if not isinstance(project_ids, (list, tuple)) or len(project_ids) > 100:
        raise ValidationError("Allowed Projects must be a bounded explicit list")
    projects = [validate_identifier(value, "allowed Project id") for value in project_ids]
    if len(set(projects)) != len(projects):
        raise ValidationError("Allowed Project declarations must be unique")
    for project in projects:
        lifecycle._context(paths, zone, project)
    return context, sorted(projects)


def _shape(record: dict, paths: LayoutPaths, zone: dict) -> dict[str, Path]:
    if (set(record) != FIELDS or record.get("schema_version") != 3
            or record.get("zone_id") != zone["id"] or record.get("operational") is not False):
        raise ValidationError("Invalid OS instance authority record")
    locations = instance_paths(paths, zone, record.get("instance_id"))
    os_id = validate_identifier(record.get("os_id"), "OS id")
    version = validate_version(record.get("os_version"))
    compiled = paths.software / "os-instance-distributions" / zone["id"] / record["instance_id"] / os_id / version
    if (record.get("workspace_root") != str(locations["workspace_root"])
            or record.get("hermes_home") != str(locations["hermes_home"])
            or record.get("compiled_distribution") != str(compiled)):
        raise SecurityError("OS instance paths differ from canonical Zone/instance scope")
    roles = record.get("role_profile_map")
    profiles = record.get("expected_profiles")
    if (not isinstance(roles, dict) or not roles or len(roles) > 100
            or roles != instance_profile_map(zone["id"], record["instance_id"], list(roles))
            or not isinstance(profiles, list) or not all(isinstance(value, str) for value in profiles)
            or len(profiles) != len(set(profiles)) or set(profiles) != set(roles.values())
            or record.get("nano_director") not in profiles):
        raise ValidationError("OS instance must contain its exact instance-qualified native team")
    states = record.get("profile_states")
    if (not isinstance(states, dict) or set(states) != set(profiles)
            or record.get("state") not in {"INSTALLABLE", "CONFIGURED", "VERIFIED", "DEGRADED"}
            or not isinstance(record.get("verification"), dict)):
        raise ValidationError("OS instance contains invalid lifecycle checkpoints")
    for profile in profiles:
        lifecycle._profile_id(profile)
        item = states[profile]
        if (not isinstance(item, dict) or set(item) != {"state", "returncode", "reason"}
                or item["state"] not in {"PENDING", "INSTALLING", "INSTALLED", "FAILED"}
                or (item["returncode"] is not None and type(item["returncode"]) is not int)
                or not isinstance(item["reason"], str)):
            raise ValidationError("OS instance contains an invalid native profile checkpoint")
    roots = record.get("runtime_roots")
    if (not isinstance(roots, dict) or set(roots) not in (set(), set(RUNTIME_DIRECTORIES))
            or record.get("runtime_state") not in {"PENDING", "READY", "REPAIR_REQUIRED"}
            or (record["runtime_state"] == "READY" and set(roots) != set(RUNTIME_DIRECTORIES))):
        raise ValidationError("Invalid OS instance runtime-root checkpoint")
    for value in roots.values():
        if (not isinstance(value, dict) or set(value) != {"device", "inode"}
                or any(type(number) is not int or number < 0 for number in value.values())):
            raise ValidationError("Invalid OS instance root identity evidence")
    return locations


def _signature(info) -> dict:
    return {"device": info.st_dev, "inode": info.st_ino}


def _runtime_context(paths: LayoutPaths, zone: dict, record: dict, context: dict) -> dict:
    locations = _shape(record, paths, zone)
    if record["runtime_state"] != "READY":
        raise ValidationError("OS instance runtime directories require install or explicit repair")
    for key in RUNTIME_DIRECTORIES:
        with lifecycle._directory(locations[key]) as fd:
            info = os.fstat(fd)
            if info.st_uid != context["uid"] or info.st_gid != context["gid"] or info.st_mode & 0o022:
                raise SecurityError("OS instance directory does not belong exclusively to its Zone")
            if key in record["runtime_roots"] and record["runtime_roots"][key] != _signature(info):
                raise SecurityError("OS instance root was replaced; explicit repair is required")
    return {**context, "hermes_home": locations["hermes_home"], "workspace_root": locations["workspace_root"]}


def _read_record(paths: LayoutPaths, zone: dict, instance_id: str) -> dict:
    locations = instance_paths(paths, zone, instance_id)
    record = lifecycle._trusted_json(locations["ledger"], paths, paths.varlib)
    if record.get("instance_id") != instance_id:
        raise SecurityError("OS instance ledger filename and identity differ")
    _shape(record, paths, zone)
    _, projects = _declaration(paths, zone, record["organization_id"], record["allowed_project_ids"])
    if projects != record["allowed_project_ids"]:
        raise ValidationError("OS instance Project declarations must be canonical")
    lifecycle._manifest(Path(record["compiled_distribution"]), paths, record)
    return record


def load_os_instance_record(paths: LayoutPaths, *, zone: dict, instance_id: str,
                            require_configured: bool = False) -> dict:
    """Pure local evidence reads; no commands, writes, credential inspection or adoption."""
    instance_id = validate_identifier(instance_id, "OS instance id")
    context = lifecycle._context(paths, zone)
    record = _read_record(paths, zone, instance_id)
    if require_configured:
        context = _runtime_context(paths, zone, record, context)
        if record["state"] not in {"CONFIGURED", "VERIFIED", "DEGRADED"} or any(
                item["state"] != "INSTALLED" for item in record["profile_states"].values()):
            raise ValidationError("OS instance team is not completely installed; resume instance install first")
        hashes = {profile: lifecycle._readback(record, profile, context, paths) for profile in record["expected_profiles"]}
        if record["state"] == "VERIFIED" and record["verification"].get("config_sha256") != hashes:
            record.update(state="CONFIGURED", verification={"state": "STALE", "reason": "Native configuration changed; rerun instance verify."},
                          next_repair_action=lifecycle.NEXT_GATE)
    return record


def _save(paths: LayoutPaths, record: dict) -> None:
    path = paths.varlib / "registry/os-instances" / validate_identifier(record["zone_id"]) / f"{validate_identifier(record['instance_id'])}.json"
    fs = SafeFS(paths.allowed_roots)
    lifecycle._ensure_authority_directory(fs, path.parent, paths, anchor=paths.varlib, mode=0o700)
    record["updated_at"] = utc_now()
    fs.write_text(path, json.dumps(record, indent=2, sort_keys=True) + "\n", mode=0o600, owner=lifecycle._authority(paths))


def _directory_exists(path: Path) -> bool:
    try:
        with lifecycle._directory(path.parent) as fd:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _owned_container(path: Path, anchor: Path, paths: LayoutPaths, context: dict) -> None:
    """Create only an absent namespace container through private staged publication."""
    from .projects import _NewProjectFS

    if _directory_exists(path):
        with lifecycle._directory(path) as fd:
            info = os.fstat(fd)
            if (info.st_uid, info.st_gid) != (context["uid"], context["gid"]) or info.st_mode & 0o022:
                raise SecurityError("Instance namespace parent is not a safe Zone-owned directory")
        return
    fs = _NewProjectFS([path], staging_roots=[anchor], operation_id=new_operation_id(), authority_uid=lifecycle._authority(paths)[0])
    try:
        fs.reserve()
        fs.mkdir(path, mode=0o700, owner=(context["uid"], context["gid"]))
        fs.publish()
        fs.handoff()
    except BaseException:
        fs.rollback_new()
        raise
    finally:
        fs.close()


def _create_runtime(paths: LayoutPaths, zone: dict, record: dict, context: dict) -> None:
    from .projects import _NewProjectFS

    locations = instance_paths(paths, zone, record["instance_id"])
    if record["runtime_state"] == "READY":
        _runtime_context(paths, zone, record, context)
        return
    if record["runtime_state"] != "PENDING" or any(_directory_exists(locations[key]) for key in ("human", "state")):
        raise ValidationError(ROOT_REPAIR)
    # The Zone's os directory is a pre-existing canonical container; only the
    # new shared instance containers and exclusive instance roots are created.
    for path in (Path(zone["human_root"]) / "os", Path(zone["state_root"])):
        with lifecycle._directory(path) as fd:
            info = os.fstat(fd)
            if (info.st_uid, info.st_gid) != (context["uid"], context["gid"]) or info.st_mode & 0o022:
                raise SecurityError("Instance parent must be a reconciled Zone directory")
    _owned_container(locations["human"].parent, paths.runtime, paths, context)
    _owned_container(locations["state"].parent, paths.varlib, paths, context)
    roots = [locations["human"], locations["state"]]
    fs = _NewProjectFS(roots, staging_roots=[paths.runtime, paths.varlib], operation_id=new_operation_id(), authority_uid=lifecycle._authority(paths)[0])
    try:
        fs.reserve()
        for root in roots:
            fs.mkdir(root, mode=0o700, owner=(context["uid"], context["gid"]))
        fs.mkdir(locations["workspace_root"], mode=0o700, owner=(context["uid"], context["gid"]))
        fs.mkdir(locations["hermes_home"], mode=0o700, owner=(context["uid"], context["gid"]))
        signatures = {key: _signature(os.fstat(fs.fds[locations[key]])) for key in ("human", "state")}
        for key in ("workspace_root", "hermes_home"):
            parent = fs._parent(locations[key])
            try:
                signatures[key] = _signature(os.stat(locations[key].name, dir_fd=parent, follow_symlinks=False))
            finally:
                os.close(parent)
        fs.publish()
        fs.handoff()
        record["runtime_roots"] = signatures
        record["runtime_state"] = "READY"
        _save(paths, record)
    except BaseException:
        rollback = fs.rollback_new()
        record.update(runtime_state="PENDING" if rollback else "REPAIR_REQUIRED", next_repair_action=ROOT_REPAIR)
        _save(paths, record)
        raise
    finally:
        fs.close()


def _reservations(paths: LayoutPaths, zone: dict, context: dict, instance_id: str, profiles: list[str]) -> None:
    """One Zone UID has one service namespace, including legacy and partial installs."""
    desired = set(profiles)
    for root, legacy in ((paths.varlib / "registry/os" / zone["id"], True),
                         (paths.varlib / "registry/os-instances" / zone["id"], False)):
        try:
            with lifecycle._directory(root, uid=lifecycle._authority(paths)[0], trusted_root=paths.varlib if paths.test_mode else None) as fd:
                names = os.listdir(fd)
                if len(names) > 1000:
                    raise ValidationError("OS reservation registry exceeds its entry limit")
        except FileNotFoundError:
            continue
        for name in names:
            if not name.endswith(".json"):
                raise SecurityError("Unexpected OS reservation entry")
            identifier = validate_identifier(name[:-5], "OS reservation")
            if not legacy and identifier == instance_id:
                continue
            other = lifecycle._read_record(paths, context, identifier) if legacy else _read_record(paths, zone, identifier)
            if desired & set(other["expected_profiles"]):
                raise ValidationError("Native profile/service name is reserved by another OS installation")
    for profile in profiles:
        if lifecycle._profile_present(context, profile):
            raise ValidationError("An existing Zone-default profile occupies an instance native name")
        service = context["home"] / ".config/systemd/user" / f"hermes-gateway-{profile}.service"
        if _directory_exists(service):
            raise ValidationError("An existing native service occupies the new instance identity")


def check_instance_reservations(paths: LayoutPaths, zone: dict, profiles: list[str]) -> None:
    """Legacy installs must respect instance reservations in the same service namespace."""
    root = paths.varlib / "registry/os-instances" / zone["id"]
    try:
        with lifecycle._directory(root, uid=lifecycle._authority(paths)[0], trusted_root=paths.varlib if paths.test_mode else None) as fd:
            names = os.listdir(fd)
            if len(names) > 1000:
                raise ValidationError("OS reservation registry exceeds its entry limit")
    except FileNotFoundError:
        return
    for name in names:
        if not name.endswith(".json"):
            raise SecurityError("Unexpected OS instance reservation entry")
        other = _read_record(paths, zone, validate_identifier(name[:-5], "OS instance id"))
        if set(profiles) & set(other["expected_profiles"]):
            raise ValidationError("An OS instance reserves the same native profile/service identity")


def _guard(paths: LayoutPaths, zone: dict, record: dict, context: dict, *,
           previously_configured: bool) -> None:
    try:
        _runtime_context(paths, zone, record, context)
    except (OSError, SecurityError, ValidationError):
        configured = previously_configured or record["state"] in {"CONFIGURED", "VERIFIED", "DEGRADED"}
        record.update(state="DEGRADED" if configured else "INSTALLABLE",
                      runtime_state="REPAIR_REQUIRED", verification={},
                      next_repair_action=ROOT_REPAIR)
        _save(paths, record)
        raise SecurityError("OS instance roots changed during native work; explicit repair is required") from None


def install_os_instance(source: Path, *, paths: LayoutPaths, zone: dict, instance_id: str,
                        organization_id: str | None = None, allowed_project_ids=(), os_id: str,
                        os_version: str, hermes_binary: str, runuser_binary: str) -> dict:
    instance_id, os_id = validate_identifier(instance_id, "OS instance id"), validate_identifier(os_id, "OS id")
    os_version = validate_version(os_version)
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("OS instance installation requires Station root authority")
    context, projects = _declaration(paths, zone, organization_id, allowed_project_ids)
    locations = instance_paths(paths, zone, instance_id)
    with install_lock(paths, new_operation_id()):
        # Resolve again under the installation lock before any declaration write.
        context, projects = _declaration(paths, zone, organization_id, projects)
        if _directory_exists(locations["ledger"]):
            record = _read_record(paths, zone, instance_id)
            expected = {"organization_id": organization_id, "allowed_project_ids": projects, "os_id": os_id, "os_version": os_version}
            if any(record[field] != value for field, value in expected.items()):
                raise ValidationError("OS instance declaration is immutable; explicit migration is required")
            if record["runtime_state"] == "READY":
                _runtime_context(paths, zone, record, context)
        else:
            record = None
            if any(_directory_exists(locations[key]) for key in ("human", "state")):
                raise ValidationError("Untracked instance roots already exist; no adoption or overwrite is allowed")
        fs = SafeFS(paths.allowed_roots)
        stage_parent = paths.staging / "os-instances"
        lifecycle._ensure_authority_directory(fs, stage_parent, paths, anchor=paths.software, mode=0o700)
        stage = Path(tempfile.mkdtemp(prefix="instance-", dir=stage_parent))
        output = stage / "compiled"
        try:
            compiled = compile_os_to_hermes(source, output, workspace_root=locations["workspace_root"],
                zone_id=zone["id"], instance_id=instance_id, organization_id=organization_id, allowed_project_ids=tuple(projects))
            if compiled["os_id"] != os_id or compiled["os_version"] != os_version:
                raise ValidationError("Instance package differs from requested canonical OS/version")
            digest = lifecycle._digest(lifecycle._tree(output, uid=lifecycle._authority(paths)[0]))
            if record is not None and record["bundle_sha256"] != digest:
                raise ValidationError("Same-version instance bundle changed; explicit migration is required")
            if record is None:
                _reservations(paths, zone, context, instance_id, compiled["profiles"])
            final = paths.software / "os-instance-distributions" / zone["id"] / instance_id / os_id / os_version
            lifecycle._ensure_authority_directory(fs, final.parent, paths, anchor=paths.software, mode=0o755)
            if _directory_exists(final):
                existing = lifecycle._tree(final, uid=lifecycle._authority(paths)[0], immutable=True,
                    trusted_root=paths.software if paths.test_mode else None)
                if lifecycle._digest(existing) != digest:
                    raise ValidationError("Published instance bundle differs; no overwrite is permitted")
            else:
                fs.freeze_tree(output)
                fs.chmod(output, 0o755)
                os.replace(output, final)
                fs.chmod(final, 0o555)
            if record is None:
                record = {"schema_version": 3, "zone_id": zone["id"], "instance_id": instance_id,
                    "organization_id": organization_id, "allowed_project_ids": projects,
                    "os_id": os_id, "os_version": os_version, "workspace_root": str(locations["workspace_root"]),
                    "hermes_home": str(locations["hermes_home"]), "compiled_distribution": str(final), "bundle_sha256": digest,
                    "role_profile_map": compiled["role_profile_map"], "nano_director": compiled["nano_director"],
                    "expected_profiles": compiled["profiles"],
                    "profile_states": {profile: {"state": "PENDING", "returncode": None, "reason": "Not attempted"} for profile in compiled["profiles"]},
                    "state": "INSTALLABLE", "verification": {}, "operational": False, "updated_at": utc_now(),
                    "next_repair_action": "Resume this OS instance installation.", "runtime_roots": {}, "runtime_state": "PENDING"}
                _save(paths, record)
            _create_runtime(paths, zone, record, context)
            target = _runtime_context(paths, zone, record, context)
            previously_configured = record["state"] in {"CONFIGURED", "VERIFIED", "DEGRADED"}
            guard = lambda: _guard(paths, zone, record, context,
                                   previously_configured=previously_configured)
            result = lifecycle._install_profiles(record, target, paths, hermes_binary, runuser_binary, save=_save, validate_context=guard)
            guard()
            return result
        finally:
            fs.remove_tree_strict(stage)


def verify_os_instance(paths: LayoutPaths, *, zone: dict, instance_id: str,
                       hermes_binary: str, runuser_binary: str) -> dict:
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("OS instance verification requires Station root authority")
    with install_lock(paths, new_operation_id()):
        record = load_os_instance_record(paths, zone=zone, instance_id=instance_id, require_configured=True)
        context = _runtime_context(paths, zone, record, lifecycle._context(paths, zone))
        guard = lambda: _guard(paths, zone, record, context, previously_configured=True)
        result = lifecycle._verify_profiles(record, context, paths, hermes_binary, runuser_binary, save=_save, validate_context=guard)
        guard()
        return result
