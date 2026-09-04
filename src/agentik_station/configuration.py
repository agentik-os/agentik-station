from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import CATEGORIES
from .errors import ValidationError
from .identifiers import normalize_environment, validate_identifier, validate_optional_identifier
from .models import InstallSpec, ROLES, ZoneSpec
from .maturity import load_os_catalog


@dataclass(frozen=True)
class ZoneTemplate:
    category: str
    name: str
    environment: str
    organization: str | None
    requested_os: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ZoneTemplate":
        if not isinstance(value, dict):
            raise ValidationError("Every Zone template must be an object")
        allowed = {"category", "name", "environment", "organization", "requested_os"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValidationError(f"Unknown Zone template fields: {', '.join(unknown)}")
        category = str(value.get("category", "")).upper()
        if category not in CATEGORIES:
            raise ValidationError(f"Unsupported Zone template category: {category!r}")
        name = validate_identifier(str(value.get("name", "")), "Zone template name")
        environment = normalize_environment(str(value.get("environment", "")))
        organization = validate_optional_identifier(value.get("organization"), "Zone template organization")
        requested = value.get("requested_os", [])
        if not isinstance(requested, list):
            raise ValidationError("requested_os must be an array")
        requested_os = tuple(validate_identifier(str(item), "OS package id") for item in requested)
        if len(requested_os) != len(set(requested_os)):
            raise ValidationError(f"Zone template {name!r} contains duplicate requested OS packages")
        # Reuse ZoneSpec for category/environment compatibility validation.
        ZoneSpec(category, name, environment, "validation-host", organization)
        return cls(category, name, environment, organization, requested_os)


@dataclass(frozen=True)
class StationConfig:
    schema_version: str
    station_id: str
    roles: dict[str, tuple[ZoneTemplate, ...]]
    policy: dict[str, Any]

    def templates_for(self, role: str) -> tuple[ZoneTemplate, ...]:
        try:
            return self.roles[role]
        except KeyError:
            raise ValidationError(f"No desired-state template exists for Host role {role!r}") from None


def _validate_supported_platform(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("supported_platform must be an object")
    allowed = {"os_ids", "requires_systemd", "package_manager"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValidationError(f"Unknown supported_platform fields: {', '.join(unknown)}")
    os_ids = value.get("os_ids")
    if not isinstance(os_ids, list) or not os_ids or any(item not in {"ubuntu", "debian"} for item in os_ids):
        raise ValidationError("supported_platform.os_ids must be a non-empty subset of ubuntu/debian")
    if value.get("requires_systemd") is not True:
        raise ValidationError("11.12 supported_platform.requires_systemd must be true")
    if value.get("package_manager") != "apt":
        raise ValidationError("11.12 supported_platform.package_manager must be apt")


def _validate_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("Canonical Station config policy must be an object")
    expected: dict[str, set[Any]] = {
        "cross_zone_mounts": {"deny"},
        "cross_zone_credentials": {"deny"},
        "remote_secrets_in_control": {False},
        "development_has_production_credentials": {False},
        "plan_first": {True},
        "evidence_before_claims": {True},
        "external_installers_require_approval": {True},
        "unresolved_context": {"block"},
        "production_mutation": {"explicit-approval"},
    }
    unknown = sorted(set(value) - set(expected))
    missing = sorted(set(expected) - set(value))
    if unknown:
        raise ValidationError(f"Unknown Station policy fields: {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"Missing Station policy fields: {', '.join(missing)}")
    for field, allowed in expected.items():
        if value[field] not in allowed:
            raise ValidationError(f"Unsafe or unsupported Station policy {field}={value[field]!r}")
    return dict(value)


def _load_os_ids(repo_root: Path) -> set[str]:
    payload = load_os_catalog(repo_root / "os" / "CATALOG.json")
    return {str(item["id"]) for item in payload["packages"]}


def load_station_config(repo_root: Path) -> StationConfig:
    repo_root = Path(repo_root)
    path = repo_root / "config" / "station.default.json"
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"Canonical Station config is missing or unsafe: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot parse canonical Station config: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Canonical Station config root must be an object")
    allowed_top = {"schema_version", "station_id", "supported_platform", "roles", "policy"}
    unknown_top = sorted(set(payload) - allowed_top)
    if unknown_top:
        raise ValidationError(f"Unknown canonical Station config fields: {', '.join(unknown_top)}")
    missing_top = sorted(allowed_top - set(payload))
    if missing_top:
        raise ValidationError(f"Missing canonical Station config fields: {', '.join(missing_top)}")

    schema_version = payload.get("schema_version")
    if schema_version != "station.config/v2":
        raise ValidationError(f"Unsupported Station config schema: {schema_version!r}")
    station_id = validate_identifier(str(payload.get("station_id", "")), "station_id")
    _validate_supported_platform(payload.get("supported_platform"))

    raw_roles = payload.get("roles")
    if not isinstance(raw_roles, dict):
        raise ValidationError("Canonical Station config requires a roles object")
    if set(raw_roles) != ROLES:
        missing = sorted(ROLES - set(raw_roles))
        unknown = sorted(set(raw_roles) - ROLES)
        raise ValidationError(f"Canonical Host roles mismatch; missing={missing}, unknown={unknown}")

    roles: dict[str, tuple[ZoneTemplate, ...]] = {}
    known_os = _load_os_ids(repo_root)
    for role, raw in raw_roles.items():
        if not isinstance(raw, dict) or set(raw) != {"zones"} or not isinstance(raw.get("zones"), list):
            raise ValidationError(f"Role {role!r} must contain only a zones array")
        templates = tuple(ZoneTemplate.from_dict(item) for item in raw["zones"])
        seen: set[tuple[str, str, str]] = set()
        for template in templates:
            key = (template.category, template.name, template.environment)
            if key in seen:
                raise ValidationError(f"Duplicate Zone template for role {role}: {key}")
            seen.add(key)
            unknown_os = sorted(set(template.requested_os) - known_os)
            if unknown_os:
                raise ValidationError(
                    f"Zone template {template.name!r} requests OS packages absent from the catalog: {unknown_os}"
                )
        roles[str(role)] = templates
    policy = _validate_policy(payload.get("policy"))
    return StationConfig(str(schema_version), station_id, roles, policy)


def compile_zones(spec: InstallSpec, config: StationConfig) -> tuple[list[ZoneSpec], dict[str, tuple[str, ...]]]:
    zones: list[ZoneSpec] = []
    desired_os: dict[str, tuple[str, ...]] = {}
    for template in config.templates_for(spec.role):
        zone = ZoneSpec(
            category=template.category,
            name=template.name,
            environment=template.environment,
            host_id=spec.host_id,
            organization=template.organization,
        )
        zones.append(zone)
        desired_os[zone.zone_id] = template.requested_os
    if spec.seed:
        zone = ZoneSpec(
            category=spec.seed.category,
            name=spec.seed.name,
            environment=spec.seed.environment,
            host_id=spec.host_id,
            organization=spec.seed.organization,
        )
        zones.append(zone)
        desired_os.setdefault(zone.zone_id, ())

    ordered: list[ZoneSpec] = []
    seen: set[str] = set()
    for zone in zones:
        if zone.zone_id in seen:
            continue
        seen.add(zone.zone_id)
        ordered.append(zone)
    return ordered, desired_os
