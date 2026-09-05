"""Stepper source, typed execution and provenance; no accounts or archive code."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest
import yaml

from agentik_station.maturity import load_os_catalog
from agentik_station.os_contract import doctor_os_source
from agentik_station.os_runtime import compile_os_to_hermes


ROOT = Path(__file__).resolve().parents[2]
STEPPER = ROOT / "os/stepper"
SKILLS = ("story-map", "slice-thin", "shape-bet", "sequence-releases")


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location("stepper_program_contract", STEPPER / "programs/runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(relative):
    return json.loads((STEPPER / relative).read_text())


def test_stepper_is_complete_canonical_source_with_three_native_identities(runner):
    result = doctor_os_source(STEPPER, expected_id="stepper-os")
    assert result.ok, result.issues
    contract = read("CONTRACT.json")
    assert contract["nano_director"] == "map-steward"
    assert contract["nanoteam"] == ["shaper", "sequencer"]
    semantic = runner.validate_package()
    assert semantic["profiles"] == ["map-steward", "shaper", "sequencer"]
    assert semantic["skills"] == list(SKILLS)
    assert semantic["valid"] and semantic["operational"] is False
    assert read("MATURITY.json")["runtime_state"] == "NOT_INSTALLED"


def test_catalog_and_factory_default_deliver_stepper_without_implying_installation():
    packages = load_os_catalog(ROOT / "os/CATALOG.json")["packages"]
    entry = next(item for item in packages if item["id"] == "stepper-os")
    assert (entry["path"], entry["version"], entry["runtime_state"]) == ("os/stepper", "0.1.0", "NOT_INSTALLED")
    defaults = json.loads((ROOT / "config/station.default.json").read_text())
    factory = next(zone for zone in defaults["roles"]["core"]["zones"] if zone["category"] == "FACTORY")
    assert {"stepper-os", "builder-os", "librarian-os", "devops-os"} <= set(factory["requested_os"])


def test_archive_provenance_is_compact_complete_and_has_no_invented_license_or_verification():
    provenance = read("provenance/IMPORT.json")
    assert provenance["archive_sha256"] == "febc6254ddfd7496ba20ce1e26db951ba5e1705d1086fddffa2891264c42a5ad"
    assert len(provenance["members"]) == 52
    assert len({item["path"] for item in provenance["members"]}) == 52
    assert sum(item["bytes"] for item in provenance["members"]) == 260569
    assert provenance["archive_redistributed"] is provenance["archive_execution"] is False
    assert provenance["license"]["present_in_archive"] is provenance["license"]["grant_inferred"] is False
    assert provenance["accepted_quality_score"] is None
    assert provenance["research_verification"] == "NOT_VERIFIED"
    for member in provenance["members"]:
        assert len(member["sha256"]) == 64 and member["adapted_to"]
        assert all((STEPPER / relative).is_file() for relative in member["adapted_to"])
    assert not list(STEPPER.rglob("*.zip"))
    books, practices = read("knowledge/BOOKS.json"), read("knowledge/PRACTICES.json")
    assert books["book_count"] == len(books["books"]) == 49
    assert books["independently_verified"] is False
    assert practices["practice_count"] == sum(len(book["practices"]) for book in practices["books"]) == 150
    assert all(book["verification"] == "NOT_VERIFIED" for book in books["books"])
    assert "\\1" not in (STEPPER / "knowledge/ONTOLOGY.json").read_text()


@pytest.mark.parametrize("skill", SKILLS)
def test_each_skill_is_native_discoverable_and_its_output_is_strict_and_executable(skill, runner):
    skill_text = (STEPPER / "skills" / skill / "SKILL.md").read_text()
    assert skill_text.startswith(f"---\nname: {skill}\n")
    assert "PROFILE_ROOT/programs/runner.py" in skill_text
    assert "absolute path of this installed SKILL.md" in skill_text
    assert "third parent" in skill_text
    assert "python3 -I -B ABSOLUTE_RUNNER" in skill_text
    assert "Keep native cwd in the owning workspace" in skill_text
    assert "Do not guess from HERMES_HOME" in skill_text
    assert "knowledge/PRINCIPLES.md" in skill_text
    assert "oracle/ORACLE.md" not in skill_text
    for kind in ("input", "output"):
        schema = read(f"skills/{skill}/{kind}.schema.json")
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
    artifact = read(f"examples/{skill}.json")
    jsonschema.validate(artifact, read(f"skills/{skill}/output.schema.json"))
    before = copy.deepcopy(artifact)
    receipt = runner.validate_artifact(skill, artifact)
    assert receipt["valid"] and receipt["user_accepted"] is receipt["operational"] is False
    assert receipt["input_sha256"] == hashlib.sha256(runner.canonical(artifact).encode()).hexdigest()
    assert artifact == before
    for bad in ({**artifact, "undeclared": True}, {key: value for key, value in artifact.items() if key != "confidence"}, {**artifact, "confidence": "CERTAIN"}):
        with pytest.raises(runner.ProgramError):
            runner.validate_artifact(skill, bad)


def test_all_eighteen_declared_cases_run_without_behavior_or_live_acceptance_claims(runner):
    result = runner.evaluate()
    assert result["valid"] and len(result["cases"]) == 18
    assert all(row["passed"] for row in result["cases"])
    assert result["scope"] == "deterministic-contracts-not-model-behavior"
    assert result["operational"] is False


@pytest.mark.parametrize("workflow", ["step-loop", "unwedge"])
def test_workflow_receipts_validate_complete_artifacts_and_handoff_consistency(runner, workflow):
    request = read(f"examples/{workflow}.json")
    before = copy.deepcopy(request)
    assert runner.validate_workflow(request)["valid"] is True
    assert request == before
    request["artifacts"]["slice-thin"]["slice"]["id"] = "unsequenced"
    with pytest.raises(runner.ProgramError, match="absent"):
        runner.validate_workflow(request)


def later_slice_workflow(workflow):
    request = read(f"examples/{workflow}.json")
    selected = request["artifacts"]["slice-thin"]["slice"]
    sequence = request["artifacts"]["sequence-releases"]["sequence"]
    first = sequence[0]
    sequence += [{**first, "slice_id": "follow-up", "position": 2, "kind": "end-to-end", "depends_on": [first["slice_id"]]},
                 {**first, "slice_id": "selected-later", "position": 3, "kind": "end-to-end", "depends_on": [first["slice_id"], "follow-up"]}]
    selected.update(id="selected-later", strategy="end-to-end", dependencies=["follow-up", first["slice_id"]])
    return request


@pytest.mark.parametrize("workflow", ["step-loop", "unwedge"])
def test_later_end_to_end_slice_accepts_matching_dependencies_in_any_order(runner, workflow):
    request = later_slice_workflow(workflow)
    before = copy.deepcopy(request)
    assert runner.validate_workflow(request)["valid"] is True
    assert request == before


@pytest.mark.parametrize("workflow", ["step-loop", "unwedge"])
@pytest.mark.parametrize("defect", ["omitted-dependency", "extra-dependency", "strategy-mismatch", "later-walking-skeleton"])
def test_workflow_rejects_individually_valid_but_inconsistent_slice_and_sequence(runner, workflow, defect):
    request = later_slice_workflow(workflow)
    selected = request["artifacts"]["slice-thin"]["slice"]
    release = request["artifacts"]["sequence-releases"]["sequence"][-1]
    expected = "dependencies differ"
    if defect == "omitted-dependency":
        selected["dependencies"] = ["follow-up"]
    elif defect == "extra-dependency":
        release["depends_on"] = ["follow-up"]
    elif defect == "strategy-mismatch":
        selected["strategy"] = "walking-skeleton"
        expected = "strategy differs"
    else:
        selected.update(strategy="walking-skeleton", dependencies=[])
        release.update(kind="walking-skeleton", depends_on=[])
        expected = "first dependency-free release"
    for skill, artifact in request["artifacts"].items():
        assert runner.validate_artifact(skill, artifact)["valid"] is True
    before = copy.deepcopy(request)
    with pytest.raises(runner.ProgramError, match=expected):
        runner.validate_workflow(request)
    assert request == before


@pytest.mark.parametrize("defect", ["forward-dependency", "duplicate", "wrong-first", "bool-position"])
def test_sequence_semantics_fail_closed(runner, defect):
    artifact = read("examples/sequence-releases.json")
    row = artifact["sequence"][0]
    if defect == "forward-dependency":
        row["depends_on"] = ["later"]
    elif defect == "duplicate":
        artifact["sequence"].append({**row, "position": 2})
    elif defect == "wrong-first":
        row["kind"] = "end-to-end"
    else:
        row["position"] = True
    with pytest.raises(runner.ProgramError):
        runner.validate_artifact("sequence-releases", artifact)


def test_accessibility_scope_and_dependency_routes_do_not_invent_membership_or_external_integrations():
    routing = read("routing/ROUTING.json")
    assert routing["roles"] == {"map-steward": ["story-map", "slice-thin"], "shaper": ["shape-bet"], "sequencer": ["sequence-releases"]}
    assert routing["handoffs"] == {"research-os": "librarian-os", "evaluation-os": "builder-os", "builder-os": "builder-os", "release-os": "devops-os"}
    assert routing["membership"] == "not-inferred-from-role-name"
    assert yaml.safe_load((STEPPER / "integrations/INTEGRATIONS.yaml").read_text())["integrations"] == []
    experience = yaml.safe_load((STEPPER / "discord/EXPERIENCE.yaml").read_text())
    assert experience["accessibility"] == "text-first-no-color-only-meaning"
    for relative in ("director/PROFILE.md", "profiles/shaper/PROFILE.md", "profiles/sequencer/PROFILE.md"):
        text = (STEPPER / relative).read_text()
        assert "role_profile_map" in text and "Unknown membership or context blocks access" in text
        assert "Station rules and operator authority take precedence" in text


def test_all_three_instance_profiles_compile_with_four_skills_and_exact_role_map(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "compiled"
    compiled = compile_os_to_hermes(STEPPER, output, workspace_root=workspace,
                                    zone_id="factory-os", instance_id="stepper-fixture", organization_id="agentik")
    assert compiled["claim"] == "COMPILED_NOT_INSTALLED"
    assert set(compiled["role_profile_map"]) == {"map-steward", "shaper", "sequencer"}
    assert len(set(compiled["profiles"])) == 3
    for profile in compiled["profiles"]:
        generated = output / "profiles" / profile
        assert all((generated / "skills" / skill / "SKILL.md").is_file() for skill in SKILLS)
        soul = (generated / "SOUL.md").read_text()
        assert "Station universal agent rules" in soul
        assert all(mapped in soul for mapped in compiled["profiles"])


@pytest.mark.parametrize("content", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'])
def test_strict_input_rejects_duplicate_and_nonfinite_json(runner, tmp_path, content):
    path = tmp_path / "input.json"
    path.write_text(content)
    with pytest.raises(runner.ProgramError):
        runner.load_json(path)


def test_runner_refuses_linked_inputs_and_does_not_emit_secret_values(runner, tmp_path):
    target = tmp_path / "secret.json"
    target.write_text('{"synthetic-secret":"never-echo-this-value"}')
    link = tmp_path / "input.json"
    link.symlink_to(target)
    with pytest.raises(runner.ProgramError):
        runner.load_json(link)
    result = subprocess.run([sys.executable, str(STEPPER / "programs/runner.py"), "validate", "--skill", "story-map", "--input", str(target)],
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "never-echo-this-value" not in result.stdout + result.stderr
    assert target.read_text() == '{"synthetic-secret":"never-echo-this-value"}'


def test_package_validator_rejects_missing_domain_asset(runner, monkeypatch, tmp_path):
    import shutil
    destination = tmp_path / "stepper"
    shutil.copytree(STEPPER, destination)
    (destination / "knowledge/PRACTICES.json").unlink()
    monkeypatch.setattr(runner, "ROOT", destination)
    with pytest.raises(runner.ProgramError, match="Required package file"):
        runner.validate_package()
