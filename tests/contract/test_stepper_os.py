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
    assert (entry["path"], entry["version"], entry["runtime_state"]) == ("os/stepper", read("CONTRACT.json")["version"], "NOT_INSTALLED")
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


def test_all_twenty_seven_declared_cases_run_without_behavior_or_live_acceptance_claims(runner):
    result = runner.evaluate()
    assert result["valid"] and len(result["cases"]) == 27
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


@pytest.mark.parametrize("skill", SKILLS)
def test_transition_binds_original_input_to_output_without_mutating_either(runner, skill):
    source, output = read(f"examples/{skill}.input.json"), read(f"examples/{skill}.json")
    before = copy.deepcopy((source, output))
    result = runner.validate_transition(skill, source, output)
    assert result["state"] == "TRANSITION_VALIDATED"
    assert result["input_sha256"] == runner.content_hash(source)
    assert result["output_sha256"] == runner.content_hash(output)
    assert result["source_verified"] is result["user_accepted"] is result["operational"] is False
    assert (source, output) == before
    assert f"transition --skill {skill}" in (STEPPER / "skills" / skill / "SKILL.md").read_text()


@pytest.mark.parametrize("defect", ["duplicate-activity", "duplicate-task"])
def test_input_map_rejects_ambiguous_identifiers_before_slicing(runner, defect):
    source = read("examples/slice-thin.input.json")
    activities = source["map"]["activities"]
    if defect == "duplicate-activity":
        activities[1]["id"] = activities[0]["id"]
    else:
        activities[1]["tasks"][0]["id"] = activities[0]["tasks"][0]["id"]
    jsonschema.validate(source, read("skills/slice-thin/input.schema.json"))
    with pytest.raises(runner.ProgramError, match="identities must be unique"):
        runner.validate_artifact("slice-thin", source, "input")


def sequence_transition():
    source, output = read("examples/sequence-releases.input.json"), read("examples/sequence-releases.json")
    first = source["slices"][0]
    source["slices"].append({**first, "id": "follow-up", "strategy": "end-to-end", "dependencies": [first["id"]]})
    output["sequence"].append({**output["sequence"][0], "slice_id": "follow-up", "position": 2,
                               "kind": "end-to-end", "depends_on": [first["id"]]})
    return source, output


@pytest.mark.parametrize("defect", ["duplicate-id", "self", "unknown", "cycle"])
def test_input_slice_graph_rejects_unschedulable_identity_and_dependencies(runner, defect):
    source, _ = sequence_transition()
    first, second = source["slices"]
    if defect == "duplicate-id":
        second["id"] = first["id"]
    elif defect == "self":
        first["dependencies"] = [first["id"]]
    elif defect == "unknown":
        first["dependencies"] = ["not-supplied"]
    else:
        first["dependencies"] = [second["id"]]
    jsonschema.validate(source, read("skills/sequence-releases/input.schema.json"))
    with pytest.raises(runner.ProgramError):
        runner.validate_artifact("sequence-releases", source, "input")


def test_unordered_acyclic_backlog_is_valid_and_does_not_become_a_scheduler(runner):
    source, output = sequence_transition()
    source["slices"].reverse()
    before = copy.deepcopy(source)
    assert runner.validate_transition("sequence-releases", source, output)["valid"]
    assert source == before


@pytest.mark.parametrize("defect", ["changed-actor", "changed-journey", "missing-activity", "foreign-activity",
                                   "changed-problem", "changed-outcome", "changed-appetite-amount", "changed-appetite-unit", "dropped-slice", "invented-slice",
                                   "changed-strategy", "removed-dependency"])
def test_transition_rejects_plausible_outputs_that_change_the_supplied_work(runner, defect):
    if defect in {"changed-problem", "changed-appetite-amount", "changed-appetite-unit"}:
        skill = "shape-bet"
    elif defect in {"changed-actor", "changed-journey"}:
        skill = "story-map"
    elif defect in {"changed-outcome", "missing-activity", "foreign-activity"}:
        skill = "slice-thin"
    else:
        skill = "sequence-releases"
    source, output = (sequence_transition() if skill == "sequence-releases" else
                      (read(f"examples/{skill}.input.json"), read(f"examples/{skill}.json")))
    if defect == "changed-actor":
        output["map"]["actor"] = "Another client"
    elif defect == "changed-journey":
        output["map"]["journey"] = "A different unrequested journey"
    elif defect == "missing-activity":
        output["slice"]["activity_ids"].pop()
    elif defect == "foreign-activity":
        output["slice"]["activity_ids"][-1] = "foreign"
    elif defect == "changed-problem":
        output["pitch"]["problem"] = "An unrelated product"
    elif defect == "changed-outcome":
        output["slice"]["outcome"] = "An unrelated result"
    elif defect == "changed-appetite-amount":
        output["pitch"]["appetite"]["amount"] += 1
    elif defect == "changed-appetite-unit":
        output["pitch"]["appetite"]["unit"] = "days"
    elif defect == "dropped-slice":
        output["sequence"].pop()
    elif defect == "invented-slice":
        output["sequence"][-1]["slice_id"] = "invented"
    elif defect == "changed-strategy":
        output["sequence"][-1]["kind"] = "walking-skeleton"
    else:
        output["sequence"][-1]["depends_on"] = []
    # Both artifacts pass on their own; only the source/output relation fails.
    assert runner.validate_artifact(skill, source, "input")["valid"]
    assert runner.validate_artifact(skill, output)["valid"]
    with pytest.raises(runner.ProgramError):
        runner.validate_transition(skill, source, output)


def test_complete_workflow_preserves_sources_and_detects_cross_step_substitution(runner):
    bound = read("examples/step-loop-bound.json")
    result = runner.validate_workflow(bound)
    assert result["input_bound"] is True and len(result["transitions"]) == 4
    assert result["workflow_sha256"] == runner.content_hash(bound)
    assert runner.validate_workflow(read("examples/step-loop.json"))["input_bound"] is False
    changed = copy.deepcopy(bound)
    changed["inputs"]["slice-thin"]["map"]["activities"][0]["label"] = "Substituted source task"
    with pytest.raises(runner.ProgramError, match="preceding story map"):
        runner.validate_workflow(changed)
    changed = copy.deepcopy(bound)
    changed["inputs"]["sequence-releases"]["slices"][0]["outcome"] = "Substituted source outcome"
    with pytest.raises(runner.ProgramError, match="selected slice"):
        runner.validate_workflow(changed)
    changed = copy.deepcopy(bound)
    del changed["inputs"]["shape-bet"]
    with pytest.raises(runner.ProgramError, match="every declared skill"):
        runner.validate_workflow(changed)


def test_builder_handoff_is_exact_hash_bound_work_not_execution_or_authority(runner):
    source = read("examples/step-loop-bound.json")
    before = copy.deepcopy(source)
    handoff = runner.prepare_handoff(source)
    assert handoff == read("examples/builder-handoff.json")
    assert source == before
    jsonschema.Draft202012Validator.check_schema(read("data/HANDOFF.schema.json"))
    jsonschema.validate(handoff, read("data/HANDOFF.schema.json"))
    assert handoff["claim"] == "PREPARED_NOT_EXECUTED"
    assert handoff["execution_authorized"] is handoff["user_accepted"] is handoff["operational"] is False
    assert handoff["workflow_sha256"] == runner.content_hash(source)
    assert handoff["artifact_sha256"] == {skill: runner.content_hash(source["artifacts"][skill]) for skill in SKILLS}
    checked = runner.validate_handoff(handoff)
    assert checked["handoff_sha256"] == runner.content_hash(handoff)
    handoff["workflow"]["artifacts"]["shape-bet"]["pitch"]["solution"] = "Changed only in returned copy"
    assert source == before


@pytest.mark.parametrize("defect", ["changed-bytes", "workflow-digest", "artifact-digest", "authority", "acceptance", "unknown-field", "wrong-target"])
def test_handoff_rejects_tampering_and_false_authority_claims(runner, defect):
    handoff = read("examples/builder-handoff.json")
    if defect == "changed-bytes":
        handoff["workflow"]["artifacts"]["shape-bet"]["pitch"]["solution"] = "Modified after handoff"
        assert runner.validate_workflow(handoff["workflow"])["valid"]
    elif defect == "workflow-digest":
        handoff["workflow_sha256"] = "0" * 64
    elif defect == "artifact-digest":
        handoff["artifact_sha256"]["story-map"] = "0" * 64
    elif defect == "authority":
        handoff["execution_authorized"] = True
    elif defect == "acceptance":
        handoff["user_accepted"] = True
    elif defect == "unknown-field":
        handoff["run_command"] = "never execute supplied commands"
    else:
        handoff["target_os"] = "devops-os"
    with pytest.raises(runner.ProgramError):
        runner.validate_handoff(handoff)


@pytest.mark.parametrize("example", ["step-loop", "unwedge"])
def test_partial_or_output_only_workflows_cannot_be_promoted_to_builder_handoff(runner, example):
    with pytest.raises(runner.ProgramError, match="complete input-bound"):
        runner.prepare_handoff(read(f"examples/{example}.json"))


@pytest.mark.parametrize("field", ["problem", "outcome"])
def test_builder_handoff_cannot_replace_original_scope_with_a_consistent_but_unrequested_product(runner, field):
    workflow = read("examples/step-loop-bound.json")
    if field == "problem":
        workflow["artifacts"]["shape-bet"]["pitch"]["problem"] = "Another product"
    else:
        workflow["artifacts"]["slice-thin"]["slice"]["outcome"] = "Another outcome"
        workflow["inputs"]["sequence-releases"]["slices"][0]["outcome"] = "Another outcome"
    with pytest.raises(runner.ProgramError, match=f"supplied {field}"):
        runner.prepare_handoff(workflow)


@pytest.mark.parametrize("timing", ["before-directory-open", "before-file-open"])
def test_json_read_cannot_follow_a_substituted_parent_link(runner, tmp_path, monkeypatch, timing):
    directory, saved, foreign = tmp_path / "input-parent", tmp_path / "saved-parent", tmp_path / "foreign"
    directory.mkdir()
    foreign.mkdir()
    (directory / "payload.json").write_text('{"value":"original"}')
    (foreign / "payload.json").write_text('{"value":"foreign-private-value"}')
    original_open = runner.os.open
    swapped = False
    def replace_parent(path, flags, *args, **kwargs):
        nonlocal swapped
        when = "input-parent" if timing == "before-directory-open" else "payload.json"
        if path == when and not swapped:
            swapped = True
            directory.rename(saved)
            directory.symlink_to(foreign, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(runner.os, "open", replace_parent)
    if timing == "before-directory-open":
        with pytest.raises(runner.ProgramError, match="real directory chain"):
            runner.load_json(directory / "payload.json")
    else:
        assert runner.load_json(directory / "payload.json") == {"value": "original"}
    assert swapped


@pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="Linux O_PATH is required for traverse-only Host ancestors")
def test_linux_json_read_traverses_unlistable_directory_without_needing_read_permission(runner, tmp_path):
    directory = tmp_path / "traverse-only"
    directory.mkdir()
    target = directory / "payload.json"
    target.write_text('{"valid":true}')
    directory.chmod(0o111)
    try:
        assert runner.load_json(target) == {"valid": True}
    finally:
        directory.chmod(0o700)


def test_cli_reports_static_actionable_mismatch_without_echoing_input_secrets(tmp_path):
    source, proposed = read("examples/shape-bet.input.json"), read("examples/shape-bet.json")
    source["problem"] = proposed["pitch"]["problem"] = "SYNTHETIC_PRIVATE_NEVER_ECHO"
    proposed["pitch"]["appetite"]["amount"] += 1
    input_path, output_path = tmp_path / "input.json", tmp_path / "output.json"
    input_path.write_text(json.dumps(source))
    output_path.write_text(json.dumps(proposed))
    result = subprocess.run([sys.executable, "-I", "-B", str(STEPPER / "programs/runner.py"), "transition", "--skill", "shape-bet",
                             "--input", str(input_path), "--output", str(output_path)],
                            cwd=tmp_path, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and result.stdout == ""
    error = json.loads(result.stderr)
    assert error["error"] == "STEPPER_CONTRACT_REJECTED"
    assert error["reason"] == "Pitch must preserve the supplied appetite"
    assert "SYNTHETIC_PRIVATE_NEVER_ECHO" not in result.stdout + result.stderr


def test_installed_profile_executes_transition_and_handoff_in_workspace_with_clean_home(tmp_path):
    workspace, home, output = tmp_path / "workspace", tmp_path / "home", tmp_path / "compiled"
    workspace.mkdir()
    home.mkdir()
    compiled = compile_os_to_hermes(STEPPER, output, workspace_root=workspace,
                                    zone_id="os", instance_id="stepper-fixture")
    profile = output / "profiles" / compiled["nano_director"]
    executable = profile / "programs/runner.py"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "HERMES_HOME": str(home / "hermes"), "PYTHONDONTWRITEBYTECODE": "1"}
    for skill in SKILLS:
        source, proposed = workspace / f"{skill}-input.json", workspace / f"{skill}-output.json"
        source.write_text((profile / "examples" / f"{skill}.input.json").read_text())
        proposed.write_text((profile / "examples" / f"{skill}.json").read_text())
        done = subprocess.run([sys.executable, "-I", "-B", str(executable), "transition", "--skill", skill,
                               "--input", str(source), "--output", str(proposed)], cwd=workspace, env=env,
                              capture_output=True, text=True, timeout=10)
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["state"] == "TRANSITION_VALIDATED"
    source = workspace / "workflow.json"
    source.write_text((profile / "examples/step-loop-bound.json").read_text())
    done = subprocess.run([sys.executable, "-I", "-B", str(executable), "handoff", "--input", str(source)],
                          cwd=workspace, env=env, capture_output=True, text=True, timeout=10)
    assert done.returncode == 0, done.stderr
    handoff = workspace / "builder-handoff.json"
    handoff.write_text(done.stdout)
    checked = subprocess.run([sys.executable, "-I", "-B", str(executable), "handoff-check", "--input", str(handoff)],
                             cwd=workspace, env=env, capture_output=True, text=True, timeout=10)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["execution_authorized"] is False
    assert list(home.iterdir()) == []
    assert not list(output.rglob("__pycache__"))
