from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .identifiers import validate_identifier


def load_resource_catalog(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"Resource catalog must be a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid resource catalog: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
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
