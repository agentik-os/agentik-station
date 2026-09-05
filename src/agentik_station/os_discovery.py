"""Read-only OS name resolution. A catalog match never grants execution authority."""
from __future__ import annotations

import json
from pathlib import Path

from .errors import ValidationError
from .identifiers import validate_identifier, validate_version
from .maturity import load_os_catalog


ALIASES = {
    "stepper": "stepper-os", "steper": "stepper-os", "steper-os": "stepper-os",
    "builder": "builder-os", "builderos": "builder-os", "build-os": "builder-os",
    "master-os-builder": "builder-os", "librarian": "librarian-os",
    "devops": "devops-os",
}


def _source_object(repo: Path, relative: str, filename: str) -> dict:
    """Read package metadata without accepting a substituted package directory."""
    directory = repo
    for part in Path(relative).parts:
        directory /= part
        if directory.is_symlink() or not directory.is_dir():
            raise ValidationError("OS source directory is missing or unsafe")
    path = directory / filename
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"OS source {filename} is missing or unsafe")
    try:
        if path.stat().st_size > 65536:
            raise ValidationError(f"OS source {filename} exceeds the metadata read limit")
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"OS source {filename} is not readable JSON") from exc
    if not isinstance(result, dict):
        raise ValidationError(f"OS source {filename} must be an object")
    return result


def resolve_package(repo: Path, name: str) -> dict:
    name = validate_identifier(name.lower().strip(), "OS name")
    os_id = ALIASES.get(name, name)
    catalog = load_os_catalog(repo / "os/CATALOG.json")
    package = next((entry for entry in catalog["packages"] if entry["id"] == os_id), None)
    if package is None:
        raise ValidationError(f"Unknown OS {name!r}; use station os catalog to list delivered packages")
    contract = _source_object(repo, package["path"], "CONTRACT.json")
    manifest = _source_object(repo, package["path"], "MANIFEST.json")
    if contract.get("os_id") != os_id or manifest.get("id") != os_id:
        raise ValidationError("OS source identity differs from the catalog")
    version = validate_version(package["version"])
    if contract.get("version") != version or manifest.get("version") != version:
        raise ValidationError("OS source version differs between catalog, CONTRACT.json and MANIFEST.json; repair the canonical release")
    if not isinstance(contract.get("nanoteam"), list):
        raise ValidationError("OS source must declare its complete team")
    roles = [contract.get("nano_director"), *contract["nanoteam"]]
    for role in roles:
        validate_identifier(role, "OS role")
    if len(roles) != len(set(roles)):
        raise ValidationError("OS source roles must be unique")
    return {"schema_version": 1, "query": name, "os_id": os_id,
            "name": contract["name"], "version": version, "current_version": version,
            "source": package["path"], "source_maturity": package["maturity"],
            "director_role": contract["nano_director"], "roles": roles,
            "aliases": sorted(key for key, value in ALIASES.items() if value == os_id),
            "runtime_state": "NOT_SELECTED", "operational": False,
            "access": {"package_available": True, "execution_authorized": False,
                       "required": ["owning Zone or personal Workstation", "installed instance/profile",
                                    "authenticated human and channel admitted by the gateway",
                                    "mission/account authority within the selected scope"],
                       "note": "Names identify capabilities, not people. No display-name or global-client fallback."},
            "next_action": "Select the owning Zone and instance; then resolve its native Director. No Project is required for OS-owned work."}


def runtime_source_status(package: dict, record: dict) -> dict:
    """Compare trusted runtime metadata, not user JSON, to the current package.

    The trusted lifecycle reader already validates the immutable distribution's
    complete bytes against bundle_sha256. A version match is not a recompile or
    a claim that current compiler output has the same bytes as that distribution.
    """
    if record["os_id"] != package["os_id"]:
        raise ValidationError("Selected instance belongs to another OS; select the matching instance")
    installed = validate_version(record.get("os_version"))
    mapping = record.get("role_profile_map")
    if mapping is not None:
        team_matches = (isinstance(mapping, dict) and set(mapping) == set(package["roles"])
                        and mapping.get(package["director_role"]) == record.get("nano_director"))
    else:
        # Schema-2 runtimes use canonical role names directly as native profiles.
        team_matches = (set(record.get("expected_profiles", [])) == set(package["roles"])
                        and record.get("nano_director") == package["director_role"])
    version_matches = installed == package["current_version"]
    current = version_matches and team_matches
    instance_id = record.get("instance_id")
    selector = (f"os instance show --zone {record['zone_id']} --instance {instance_id}" if instance_id else
                f"setup --zone {record['zone_id']} --os {record['os_id']} --json")
    repair = (f"Inspect `sudo station {selector}` and the canonical {package['source']} package. "
              "Preserve the existing profiles, credentials, sessions, workspace and immutable bundle; "
              "review a backed-up migration or select an explicitly installed current instance. "
              "Do not use forced profile replacement or assume a Station update migrated this team.")
    return {"current_version": package["current_version"], "installed_version": installed,
            "source": package["source"], "source_version_matches": version_matches,
            "source_roles_match": team_matches, "canonical_selection_current": current,
            "compiled_distribution": record.get("compiled_distribution"),
            "bundle_sha256": record.get("bundle_sha256"),
            "bundle_evidence": "TRUSTED_LEDGER_AND_IMMUTABLE_DISTRIBUTION_READBACK",
            "source_bytes_compared": False,
            "routing_state": "CURRENT_VERSION_SELECTED" if current else "MIGRATION_REQUIRED",
            "next_repair_action": None if current else repair}


def require_current_runtime(repo: Path, record: dict) -> dict:
    """Gate execution separately from verification, setup and live authority."""
    status = runtime_source_status(resolve_package(repo, record["os_id"]), record)
    if not status["canonical_selection_current"]:
        raise ValidationError(
            f"Selected {record['os_id']} runtime is not the current canonical Station package "
            f"(installed {status['installed_version']}; current {status['current_version']}; "
            f"team matches: {status['source_roles_match']}). {status['next_repair_action']}"
        )
    return status


def bind_instance(package: dict, record: dict) -> dict:
    """Caller must obtain record through the trusted instance reader, never user JSON."""
    status = runtime_source_status(package, record)
    mapping = record["role_profile_map"]
    return {**package, **status, "runtime_state": record["state"],
            "scope": {key: record[key] for key in ("zone_id", "instance_id", "organization_id", "allowed_project_ids")},
            "hermes_home": record["hermes_home"], "workspace_root": record["workspace_root"],
            "role_profile_map": mapping, "installed_director_profile": record["nano_director"],
            "director_profile": record["nano_director"] if status["canonical_selection_current"] else None,
            "next_action": ("Use this instance's exact native profile. Configure its provider/chat identity if absent; live authority and mission acceptance remain separate."
                            if status["canonical_selection_current"] else status["next_repair_action"])}
