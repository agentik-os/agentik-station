from __future__ import annotations

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]


def test_zone_schema_is_strict_and_supports_client_project_categories() -> None:
    schema = json.loads((ROOT / "config" / "schemas" / "zone.schema.json").read_text())
    assert schema.get("additionalProperties") is False
    assert "CLIENTS" in schema["properties"]["category"]["enum"]
    assert "PROJECTS" in schema["properties"]["category"]["enum"]


def test_install_spec_example_validates_against_schema() -> None:
    schema = json.loads((ROOT / "contracts" / "install-spec.schema.json").read_text())
    example = {
        "schema_version": 1,
        "release_version": "0.2.0-alpha.11",
        "operation_id": "op-schema-example",
        "host_id": "moonbase-prod-01",
        "role": "client",
        "install_system_packages": False,
        "configure_fail2ban": False,
        "enable_doctor_timer": False,
        "seed": {
            "category": "CLIENTS",
            "name": "moonbase",
            "environment": "production",
            "organization": "moonbase",
            "project": "platform",
        },
    }
    jsonschema.validate(example, schema)
