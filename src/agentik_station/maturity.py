from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import MATURITY_STATES
from .errors import ValidationError
from .identifiers import validate_identifier, validate_version

ORDER = {state: index for index, state in enumerate(MATURITY_STATES)}
MODULE_FIELDS = {"id", "maturity", "claim", "next_repair_action", "binary_probes"}
OS_FIELDS = {"id", "path", "maturity", "runtime_state", "claim", "next_repair_action"}
OS_RUNTIME_STATES = {
    "NOT_INSTALLED",
    "INSTALLING",
    "CONFIGURED",
    "VERIFIED",
    "OPERATIONAL",
    "DEGRADED",
}


def validate_state(value: str) -> str:
    if value not in ORDER:
        raise ValidationError(f"Unknown maturity/readiness state: {value!r}")
    return value


def at_least(value: str, threshold: str) -> bool:
    validate_state(value)
    validate_state(threshold)
    if value == "DEGRADED":
        return False
    return ORDER[value] >= ORDER[threshold]


def _load_object(path: Path, label: str) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"{label} must be a regular non-symlink JSON file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"{label} root must be an object: {path}")
    return payload


def load_catalog(path: Path) -> dict[str, Any]:
    payload = _load_object(path, "module catalog")
    allowed_top = {"schema_version", "release", "states", "modules"}
    unknown_top = sorted(set(payload) - allowed_top)
    if unknown_top:
        raise ValidationError(f"Unknown module catalog fields: {', '.join(unknown_top)}")
    if payload.get("schema_version") != 1:
        raise ValidationError("Module catalog schema_version must be 1")
    validate_version(str(payload.get("release", "")))
    if payload.get("states") != MATURITY_STATES:
        raise ValidationError("Module catalog states must exactly match the canonical maturity order")
    modules = payload.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValidationError(f"Module catalog must contain a non-empty modules list: {path}")
    seen: set[str] = set()
    for module in modules:
        if not isinstance(module, dict):
            raise ValidationError("Every module catalog entry must be an object")
        unknown = sorted(set(module) - MODULE_FIELDS)
        if unknown:
            raise ValidationError(f"Unknown module catalog fields: {', '.join(unknown)}")
        module_id = validate_identifier(str(module.get("id", "")), "module id")
        if module_id in seen:
            raise ValidationError(f"Duplicate module id: {module_id!r}")
        seen.add(module_id)
        state = validate_state(str(module.get("maturity", "")))
        claim = module.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            raise ValidationError(f"Module {module_id} requires a non-empty claim")
        probes = module.get("binary_probes")
        if not isinstance(probes, list) or any(
            not isinstance(item, str) or not item or any(ch.isspace() for ch in item) or "/" in item
            for item in probes
        ):
            raise ValidationError(f"Module {module_id} binary_probes must be simple command names")
        next_action = module.get("next_repair_action")
        if state in {"SPECIFIED", "SCAFFOLDED", "DEGRADED"} and (
            not isinstance(next_action, str) or not next_action.strip()
        ):
            raise ValidationError(f"Module {module_id} in state {state} requires next_repair_action")
    return payload


def load_os_catalog(path: Path) -> dict[str, Any]:
    payload = _load_object(path, "OS catalog")
    allowed_top = {"schema_version", "release", "contract", "packages"}
    unknown_top = sorted(set(payload) - allowed_top)
    if unknown_top:
        raise ValidationError(f"Unknown OS catalog fields: {', '.join(unknown_top)}")
    if payload.get("schema_version") != 1:
        raise ValidationError("OS catalog schema_version must be 1")
    validate_version(str(payload.get("release", "")))
    if payload.get("contract") != "AGK OS v2":
        raise ValidationError("OS catalog must declare the AGK OS v2 contract")
    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValidationError("OS catalog requires a non-empty packages array")
    seen: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise ValidationError("Every OS catalog entry must be an object")
        unknown = sorted(set(package) - OS_FIELDS)
        if unknown:
            raise ValidationError(f"Unknown OS catalog fields: {', '.join(unknown)}")
        package_id = validate_identifier(str(package.get("id", "")), "OS package id")
        if package_id in seen:
            raise ValidationError(f"Duplicate OS package id: {package_id}")
        seen.add(package_id)
        expected_path = f"packages/os/{package_id}"
        if package.get("path") != expected_path:
            raise ValidationError(f"OS package {package_id} path must be {expected_path!r}")
        state = validate_state(str(package.get("maturity", "")))
        runtime_state = package.get("runtime_state")
        if runtime_state not in OS_RUNTIME_STATES:
            raise ValidationError(f"OS package {package_id} has invalid runtime_state {runtime_state!r}")
        claim = package.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            raise ValidationError(f"OS package {package_id} requires a non-empty claim")
        if (state in {"SPECIFIED", "SCAFFOLDED", "DEGRADED"} or runtime_state == "DEGRADED") and not package.get(
            "next_repair_action"
        ):
            # Source packages may keep the repair action in their claim during migration;
            # v11 adds a deterministic default in the catalog upgrade below.
            raise ValidationError(
                f"OS package {package_id} in maturity/runtime state {state}/{runtime_state} requires next_repair_action"
            )
    return payload
