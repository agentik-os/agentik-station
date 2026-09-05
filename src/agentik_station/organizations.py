"""Explicit Organization enrollment over existing, trusted client Zones.

This registry is ownership metadata, not a new Unix isolation boundary. It never
creates/relabels Zones, adopts untrusted files, or moves existing client data.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from .errors import SecurityError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_identifier
from .paths import LayoutPaths

FIELDS = {"schema_version", "id", "zone_ids"}
MAX_ZONES = 3
MAX_ORGANIZATIONS = 1000


def _owner(paths: LayoutPaths) -> tuple[int, int]:
    return (os.getuid(), os.getgid()) if paths.test_mode else (0, 0)


def _read_json(paths: LayoutPaths, path: Path) -> dict:
    # Lazy import: os_lifecycle already imports the kernel's install_lock.
    from .os_lifecycle import read_runtime_json

    return read_runtime_json(path, uid=_owner(paths)[0], immutable=True,
                             trusted_root=paths.config if paths.test_mode else None)


def _host_id(paths: LayoutPaths) -> str:
    host = _read_json(paths, paths.config / "station.json")
    if type(host.get("schema_version")) is not int or host["schema_version"] != 1:
        raise ValidationError("Organization enrollment requires a reconciled Host record")
    return validate_identifier(host.get("host_id"), "current Host id")


def _shape(value: dict, organization_id: str) -> dict:
    if (set(value) != FIELDS or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1 or value.get("id") != organization_id):
        raise ValidationError("Invalid Organization registry identity/schema")
    zones = value.get("zone_ids")
    if not isinstance(zones, list) or not 1 <= len(zones) <= MAX_ZONES:
        raise ValidationError("An Organization must explicitly bind one to three environment Zones")
    for zone_id in zones:
        validate_identifier(zone_id, "Organization Zone id")
    if len(set(zones)) != len(zones):
        raise ValidationError("Organization Zone bindings must be unique")
    return value


def _zone(paths: LayoutPaths, organization_id: str, zone_id: str, host_id: str) -> dict:
    from .doctor import _validate_local_zone_record

    path = paths.config / "zones.d" / f"{zone_id}.json"
    value = _read_json(paths, path)
    try:
        spec, _, _, _ = _validate_local_zone_record(
            value, record_path=path, paths=paths, expected_host_id=host_id)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValidationError("Organization Zone record is not canonical for this Host") from exc
    if (spec.category != "ORGANIZATIONS" or spec.name != organization_id
            or spec.organization != organization_id):
        raise ValidationError("Organization binding must match the Zone category, client name and organization identity")
    return value


def _validate_zones(paths: LayoutPaths, value: dict) -> None:
    host_id = _host_id(paths)
    environments: set[str] = set()
    for zone_id in value["zone_ids"]:
        zone = _zone(paths, value["id"], zone_id, host_id)
        if zone["environment"] in environments:
            raise ValidationError("An Organization may bind only one local Zone per environment")
        environments.add(zone["environment"])


def _registry(paths: LayoutPaths) -> dict[str, dict]:
    from .os_lifecycle import _directory

    root = paths.config / "organizations.d"
    try:
        with _directory(root, uid=_owner(paths)[0],
                        trusted_root=paths.config if paths.test_mode else None) as fd:
            names = os.listdir(fd)
            if len(names) > MAX_ORGANIZATIONS:
                raise ValidationError("Organization registry exceeds its entry limit")
            for name in names:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not name.endswith(".json") or not stat.S_ISREG(info.st_mode):
                    raise SecurityError("Unexpected Organization registry entry")
    except FileNotFoundError:
        return {}
    result = {}
    for name in sorted(names):
        organization_id = validate_identifier(name[:-5], "Organization id")
        result[organization_id] = _shape(_read_json(paths, root / name), organization_id)
    return result


def _check_conflicts(value: dict, records: dict[str, dict]) -> None:
    for other_id, other in records.items():
        if other_id != value["id"] and set(other["zone_ids"]) & set(value["zone_ids"]):
            raise ValidationError("A Zone is already bound to another Organization; explicit repair is required")


def load_organization(paths: LayoutPaths, *, organization_id: str) -> dict:
    """Read exact enrolled identity and current local bindings; no mutations."""
    organization_id = validate_identifier(organization_id, "Organization id")
    value = _shape(_read_json(paths, paths.config / "organizations.d" / f"{organization_id}.json"),
                   organization_id)
    _validate_zones(paths, value)
    _check_conflicts(value, _registry(paths))
    return value


def validate_organization_zone(paths: LayoutPaths, *, organization_id: str, zone: dict) -> dict:
    """Return the registered Organization only for this exact trusted Zone."""
    organization = load_organization(paths, organization_id=organization_id)
    zone_id = validate_identifier(zone.get("id"), "Zone id")
    if zone_id not in organization["zone_ids"]:
        raise ValidationError("Zone is not explicitly enrolled in this Organization")
    trusted = _zone(paths, organization["id"], zone_id, _host_id(paths))
    if trusted != zone:
        raise SecurityError("Supplied Zone differs from its trusted Organization binding")
    return organization


def register_organization(paths: LayoutPaths, *, organization_id: str, zone_ids: list[str],
                          plan: bool = False) -> dict:
    """Enroll existing client Zones, or read-only preview; no implicit migration."""
    organization_id = validate_identifier(organization_id, "Organization id")
    if not isinstance(zone_ids, list):
        raise ValidationError("Organization zone_ids must be an explicit list")
    desired = _shape({"schema_version": 1, "id": organization_id, "zone_ids": zone_ids}, organization_id)
    desired = {**desired, "zone_ids": sorted(zone_ids)}
    if not plan and not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("Organization registration requires the Station root authority")

    def inspect() -> bool:
        _validate_zones(paths, desired)
        records = _registry(paths)
        _check_conflicts(desired, records)
        existing = records.get(organization_id)
        if existing is not None and {**existing, "zone_ids": sorted(existing["zone_ids"])} != desired:
            raise ValidationError("Existing Organization bindings differ; explicit migration is required")
        return existing is not None

    existing = inspect()
    path = paths.config / "organizations.d" / f"{organization_id}.json"
    if plan:
        return {"kind": "OrganizationRegistrationPlan", "organization": desired,
                "registry_path": str(path), "already_registered": existing,
                "mutates": False, "operational": False}
    from .installer import install_lock
    from .models import new_operation_id

    with install_lock(paths, new_operation_id()):
        if inspect():
            return desired
        fs = SafeFS(paths.allowed_roots)
        fs.mkdir(path.parent, mode=0o700, owner=_owner(paths))
        fs.write_text(path, json.dumps(desired, indent=2, sort_keys=True) + "\n",
                      mode=0o600, owner=_owner(paths))
        return load_organization(paths, organization_id=organization_id)
