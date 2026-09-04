from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import jsonschema
import yaml

from agentik_station.cli import build_parser
from agentik_station.os_contract import doctor_os_source


ROOT = Path(__file__).resolve().parents[2]
DEVOPS = ROOT / "os" / "devops"


def _runner_module():
    path = DEVOPS / "programs" / "runner.py"
    spec = importlib.util.spec_from_file_location("agk_devops_programs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_devops_os_has_executable_semantic_contract() -> None:
    result = doctor_os_source(DEVOPS, expected_id="devops-os")
    assert result.ok, result.issues
    checks = {check["name"] for check in result.checks}
    assert {
        "semantic:contract",
        "semantic:tools",
        "semantic:provider-routes",
        "semantic:workflow",
        "semantic:librarian",
        "semantic:recovery",
        "semantic:evals",
        "semantic:discord",
        "semantic:client-operations",
    } <= checks


def test_devops_doctor_fails_closed_when_semantics_are_incomplete(tmp_path: Path) -> None:
    copy = tmp_path / "devops"
    shutil.copytree(DEVOPS, copy)
    (copy / "tools" / "CONTRACTS.json").unlink()

    result = doctor_os_source(copy, expected_id="devops-os")

    assert not result.ok
    assert any(issue["name"] == "semantic:file:tools/CONTRACTS.json" for issue in result.issues)


def test_devops_programs_validate_evidence_and_report_drift_without_mutation() -> None:
    runner = _runner_module()
    evidence = {
        "evidence_id": "ev-1",
        "zone_id": "zone-a",
        "project_id": "project-a",
        "mission_id": "mission-a",
        "subject": "deployment",
        "claim": "verified",
        "stage": "ACCEPTED",
        "type": "test-report",
        "source": "ci",
        "actor": "sentinel",
        "created_at": "2026-09-04T00:00:00Z",
        "verification_status": "passed",
        "artifact_ref": "sha256:abc",
        "verifier": "release-engineer",
    }
    assert runner.validate_evidence(evidence)["valid"] is True
    before = json.dumps(evidence, sort_keys=True)
    report = runner.drift_report(evidence, {**evidence, "claim": "changed"})
    assert report["state"] == "DRIFT"
    assert report["mutation_performed"] is False
    assert json.dumps(evidence, sort_keys=True) == before
    assert runner.validate_package(DEVOPS)["valid"] is True


def test_client_operations_defaults_match_the_machine_schema() -> None:
    schema = json.loads((DEVOPS / "data" / "CLIENT_OPERATIONS.schema.json").read_text(encoding="utf-8"))
    operations = yaml.safe_load(
        (ROOT / "components" / "agk-tui" / "client" / "defaults" / "operations.yaml").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(operations, schema)


def test_station_exposes_client_and_composio_discord_facades() -> None:
    parser = build_parser()
    client = parser.parse_args(["client", "doctor", "acme"])
    assert client.client_args == ["doctor", "acme"]
    adapter = parser.parse_args(["provider", "composio-discord", "plan", "--zone", "acme-prod"])
    assert adapter.composio_discord_command == "plan"


def test_composio_discord_policy_and_discord_js_are_pinned() -> None:
    policy = json.loads((ROOT / "config" / "composio" / "discord-tool-policy.json").read_text())
    assert policy["defaults"]["execution"] == "deny"
    assert policy["identity"]["cross_zone_fallback"] == "deny"
    package = json.loads((ROOT / "resources" / "discord-js-sdk" / "package.json").read_text())
    lock = json.loads((ROOT / "resources" / "discord-js-sdk" / "package-lock.json").read_text())
    assert package["dependencies"]["discord.js"] == "14.27.0"
    assert lock["packages"]["node_modules/discord.js"]["version"] == "14.27.0"
    assert "gateway" in (ROOT / "resources" / "discord-js-sdk" / "README.md").read_text().lower()
