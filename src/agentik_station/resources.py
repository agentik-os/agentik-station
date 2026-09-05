from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .identifiers import validate_identifier
from .filesystem import SafeFS


def load_resource_catalog(path: Path) -> dict[str, Any]:
    path = Path(path)
    SafeFS._assert_existing_absolute_chain(path.absolute().parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024:
                raise ValidationError("Resource catalog must be a bounded, single-link regular file")
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValidationError("Resource catalog exceeds its size bound")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValidationError("Resource catalog contains duplicate keys")
                result[key] = value
            return result
        payload = json.loads(raw, object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError("Invalid resource catalog") from exc
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValidationError("Resource catalog must be a schema_version 1 object")
    if payload.get("open_to_other_stacks") is not True:
        raise ValidationError("Resource catalog must preserve the open-stack policy")
    resources = payload.get("resources")
    stacks = payload.get("stacks")
    if not isinstance(resources, list) or not isinstance(stacks, list):
        raise ValidationError("Resource catalog resources and stacks must be arrays")
    ids: set[str] = set()
    for item in [*resources, *stacks]:
        if not isinstance(item, dict):
            raise ValidationError("Every resource/stack catalog entry must be an object")
        item_id = validate_identifier(str(item.get("id", "")), "resource id")
        if item_id in ids:
            raise ValidationError(f"Duplicate resource/stack id: {item_id}")
        ids.add(item_id)
    default_stack = validate_identifier(str(payload.get("default_stack", "")), "default stack")
    if default_stack not in {str(item["id"]) for item in stacks}:
        raise ValidationError("Resource catalog default_stack is not declared")
    return payload


def build_os_resource_index(repo: Path) -> dict[str, Any]:
    """Deliver the real resource catalog and fixed Host checklist, never live state.

    This compiler input is pure source data. Do not inspect accounts, discover
    binaries, install dependencies or borrow a previous Host's readiness report.
    """
    from .full_stack import COMPONENTS

    catalog = load_resource_catalog(repo / "resources/CATALOG.json")
    return {
        "schema_version": 1,
        "claim": "DECLARED_NOT_PROBED",
        "execution_authorized": False,
        "accounts_enrolled": False,
        "operational": False,
        "catalog": catalog,
        "preferred_stack_plan": build_stack_plan(catalog),
        "host_software_requirements": [
            {"id": item.id, "members": list(item.members), "verification_scope": item.scope,
             "repair": item.repair, "state": "NOT_PROBED"}
            for item in COMPONENTS
        ],
        "host_readback": {
            "argv": ["station", "deps", "full-check"],
            "requires": "Authorized Linux Host operator; not an automatic sudo grant",
            "accounts_checked": False,
        },
        "workstation_readback": "Use the owning Workstation installer's verification report; Host-only services are not implied.",
        "profile_tool_declarations": ["station_crawl4ai", "station_scrapegraph"],
        "integration_rule": "Select only the capability needed by this mission; verify its owning account and actual readback before execution. Installed software is not a connected service.",
    }


def find_resource(catalog: dict[str, Any], item_id: str) -> dict[str, Any]:
    item_id = validate_identifier(item_id, "resource id")
    for item in [*catalog["resources"], *catalog["stacks"]]:
        if item["id"] == item_id:
            return item
    raise ValidationError(f"Unknown resource or stack: {item_id}")


def build_stack_plan(catalog: dict[str, Any], stack_id: str | None = None) -> dict[str, Any]:
    stack_id = validate_identifier(stack_id or str(catalog["default_stack"]), "stack id")
    stack = next((item for item in catalog["stacks"] if item["id"] == stack_id), None)
    if stack is None:
        raise ValidationError(f"Unknown stack: {stack_id}")
    runtime = stack.get("runtime_packages")
    development = stack.get("development_packages")
    initializers = stack.get("initializers")
    if not isinstance(runtime, list) or not runtime or not all(isinstance(item, str) and "@" in item for item in runtime):
        raise ValidationError(f"Stack {stack_id} has invalid runtime_packages")
    if not isinstance(development, list) or not all(isinstance(item, str) and "@" in item for item in development):
        raise ValidationError(f"Stack {stack_id} has invalid development_packages")
    if not isinstance(initializers, list) or not all(
        isinstance(argv, list) and argv and all(isinstance(value, str) and value for value in argv)
        for argv in initializers
    ):
        raise ValidationError(f"Stack {stack_id} has invalid initializers")
    return {
        "schema_version": 1,
        "stack_id": stack_id,
        "working_directory": "OWNING_PROJECT_REPOSITORY",
        "commands": [
            ["npm", "install", *runtime],
            ["npm", "install", "--save-dev", *development],
            *initializers,
        ],
        "external_setup_gates": stack.get("external_systems", []),
        "claim": "PLAN_ONLY_NOT_INSTALLED",
        "open_to_other_stacks": True,
    }
