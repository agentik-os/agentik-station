"""Read-only OS name resolution. A catalog match never grants execution authority."""
from __future__ import annotations

import json
from pathlib import Path

from .errors import ValidationError
from .identifiers import validate_identifier
from .maturity import load_os_catalog


ALIASES = {
    "stepper": "stepper-os", "steper": "stepper-os", "steper-os": "stepper-os",
    "builder": "builder-os", "builderos": "builder-os", "build-os": "builder-os",
    "master-os-builder": "builder-os", "librarian": "librarian-os",
    "devops": "devops-os",
}


def resolve_package(repo: Path, name: str) -> dict:
    name = validate_identifier(name.lower().strip(), "OS name")
    os_id = ALIASES.get(name, name)
    catalog = load_os_catalog(repo / "os/CATALOG.json")
    package = next((entry for entry in catalog["packages"] if entry["id"] == os_id), None)
    if package is None:
        raise ValidationError(f"Unknown OS {name!r}; use station os catalog to list delivered packages")
    contract_path = repo / package["path"] / "CONTRACT.json"
    if contract_path.is_symlink() or not contract_path.is_file():
        raise ValidationError("OS source contract is missing or unsafe")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("os_id") != os_id:
        raise ValidationError("OS source identity differs from the catalog")
    roles = [contract["nano_director"], *contract["nanoteam"]]
    for role in roles:
        validate_identifier(role, "OS role")
    return {"schema_version": 1, "query": name, "os_id": os_id,
            "name": contract["name"], "version": package["version"],
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


def bind_instance(package: dict, record: dict) -> dict:
    """Caller must obtain record through the trusted instance reader, never user JSON."""
    if record["os_id"] != package["os_id"]:
        raise ValidationError("Selected instance belongs to another OS; select the matching instance")
    mapping = record["role_profile_map"]
    if set(mapping) != set(package["roles"]):
        raise ValidationError("Installed team differs from the current package; inspect its version before routing")
    return {**package, "runtime_state": record["state"],
            "scope": {key: record[key] for key in ("zone_id", "instance_id", "organization_id", "allowed_project_ids")},
            "hermes_home": record["hermes_home"], "workspace_root": record["workspace_root"],
            "role_profile_map": mapping, "director_profile": mapping[package["director_role"]],
            "installed_version": record["os_version"],
            "next_action": "Use this instance's exact native profile. Configure its provider/chat identity if absent; live authority and mission acceptance remain separate."}
