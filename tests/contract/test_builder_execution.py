"""Builder's real native skill: scoped packets and byte-bound evidence, no accounts."""
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

from agentik_station.os_contract import doctor_os_source
from agentik_station.os_runtime import compile_os_to_hermes


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "os/builder"
SKILL = BUILDER / "skills/builder-execution"
RUNNER = SKILL / "scripts/runner.py"


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location("builder_execution_fixture", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text())


def put(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest()}


@pytest.fixture
def mission(tmp_path):
    value = read(SKILL / "examples/mission.json")
    value["scope"]["workspace"] = str(tmp_path)
    put(tmp_path, "research/librarian.md", (SKILL / "examples/librarian.md").read_bytes())
    return value


def evidence(tmp_path, runner, mission):
    tasks = []
    for task in mission["tasks"]:
        tasks.append({"task_id": task["id"], "owner": task["owner"], "verifier": task["verifier"],
                      "status": "passed", "artifacts": [put(tmp_path, path, b"synthetic artifact\n") for path in task["outputs"]],
                      "checks": [{"criterion_id": key, "status": "passed", "evidence": put(
                          tmp_path, f"evidence/{key}.txt", b"Synthetic check report, not a live verification.\n")}
                                 for key in task["criteria"]]})
    return {"schema_version": "station-builder-evidence/v1", "mission_sha256": runner.digest(mission), "tasks": tasks}


def cli(runner_path, workspace, command):
    return subprocess.run([sys.executable, "-I", "-B", str(runner_path), *command, "--workspace", str(workspace)],
                          cwd=workspace, env={"PATH": "/usr/bin:/bin", "HOME": str(workspace)},
                          capture_output=True, timeout=15)


def test_native_entrypoint_schemas_and_source_doctor():
    assert doctor_os_source(BUILDER).ok
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: builder-execution\n")
    for instruction in ("absolute path of this installed", "Do not guess from", "--oneshot", "--query-file", "--max-turns"):
        assert instruction in text
    for name in ("mission", "evidence"):
        jsonschema.Draft202012Validator.check_schema(read(SKILL / f"schemas/{name}.schema.json"))
    programs = yaml.safe_load((BUILDER / "programs/PROGRAMS.yaml").read_text())
    assert len(programs["programs"]) == 2
    assert all((BUILDER / item["entrypoint"]).is_file() for item in programs["programs"])
    assert len(yaml.safe_load((BUILDER / "ORDERED_SKILLS.yaml").read_text())["ordered_skills"]) == 18


def test_prepare_produces_deterministic_scoped_packets_not_dispatch(tmp_path, runner, mission):
    before = copy.deepcopy(mission)
    jsonschema.validate(mission, runner.schema("mission"))
    result = runner.prepare(runner.Workspace(tmp_path), mission)
    assert result["dependency_waves"] == [["build"], ["recover", "review"]]
    assert result["mission_sha256"] == runner.digest(mission)
    assert result["claim"] == "PREPARED_NOT_EXECUTED"
    assert result["execution_authorized"] is result["source_verified"] is result["operational"] is False
    assert all(item["native_profile"] is None and str(tmp_path) in item["query"] for item in result["packets"])
    assert mission == before
    mission["tasks"].reverse()
    assert runner.prepare(runner.Workspace(tmp_path), mission)["dependency_waves"] == result["dependency_waves"]


@pytest.mark.parametrize("defect", ["unknown", "blank", "tasks-empty", "criteria-empty", "no-librarian", "duplicate-task",
                                  "duplicate-criterion", "duplicate-output", "overlap", "overlap-nonadjacent",
                                  "input-overwrite", "input-parent", "cycle", "missing-dependency", "same-verifier",
                                  "unknown-role", "reviewer-authored-build", "orphan-review", "budget", "bool-turns",
                                  "missing-kind", "uncovered-criterion", "wrong-verifier", "wrong-workspace", "personal-zone"])
def test_preparation_rejects_unsafe_or_unusable_graphs(tmp_path, runner, mission, defect):
    if defect == "unknown":
        mission["command"] = "not executed"
    elif defect == "blank":
        mission["brief"]["goal"] = "   "
    elif defect == "tasks-empty":
        mission["tasks"] = []
    elif defect == "criteria-empty":
        mission["criteria"] = []
    elif defect == "no-librarian":
        mission["inputs"][0]["kind"] = "reference"
    elif defect == "duplicate-task":
        mission["tasks"].append(copy.deepcopy(mission["tasks"][0]))
    elif defect == "duplicate-criterion":
        mission["criteria"].append(copy.deepcopy(mission["criteria"][0]))
    elif defect == "duplicate-output":
        mission["tasks"][1]["outputs"] = mission["tasks"][0]["outputs"][:]
    elif defect in {"overlap", "overlap-nonadjacent"}:
        mission["tasks"][0]["outputs"] += ["owned", "owned/file.md"]
        if defect == "overlap-nonadjacent":
            mission["tasks"][0]["outputs"].append("owned-sibling")
    elif defect == "input-overwrite":
        mission["tasks"][0]["outputs"].append("research/librarian.md")
    elif defect == "input-parent":
        mission["tasks"][0]["outputs"].append("research")
    elif defect == "cycle":
        mission["tasks"][0]["depends_on"] = ["review"]
    elif defect == "missing-dependency":
        mission["tasks"][0]["depends_on"] = ["missing"]
    elif defect == "same-verifier":
        mission["tasks"][0]["owner"] = mission["tasks"][0]["verifier"]
    elif defect == "unknown-role":
        mission["tasks"][0]["owner"] = "external-admin"
    elif defect == "reviewer-authored-build":
        mission["tasks"][1]["verifier"] = mission["criteria"][1]["verifier"] = "program-engineer"
    elif defect == "orphan-review":
        mission["tasks"][1]["depends_on"] = []
    elif defect == "budget":
        mission["turn_budget"] = 1
    elif defect == "bool-turns":
        mission["tasks"][0]["max_turns"] = True
    elif defect == "missing-kind":
        mission["criteria"][2]["kind"] = "deterministic"
    elif defect == "uncovered-criterion":
        mission["criteria"].append({**mission["criteria"][0], "id": "uncovered"})
    elif defect == "wrong-verifier":
        mission["criteria"][0]["verifier"] = "recovery-auditor"
    elif defect == "wrong-workspace":
        mission["scope"]["workspace"] = "/another/workspace"
    elif defect == "personal-zone":
        mission["scope"]["mode"] = "personal-workstation"
    with pytest.raises(runner.ProgramError):
        runner.prepare(runner.Workspace(tmp_path), mission)


def test_evidence_checks_bytes_and_coverage_without_claiming_live_acceptance(tmp_path, runner, mission):
    report = evidence(tmp_path, runner, mission)
    before = copy.deepcopy(report)
    jsonschema.validate(report, runner.schema("evidence"))
    result = runner.verify(runner.Workspace(tmp_path), mission, report)
    assert result["valid"] and result["all_reported_checks_passed"]
    assert result["artifact_files_bound"] == result["check_files_bound"] == 3
    assert result["claim"] == "EVIDENCE_BOUND_NOT_ACCEPTED"
    assert all(result[key] is False for key in ("operational", "user_accepted", "reviewer_identity_verified",
                                               "execution_verified", "external_readback_verified"))
    assert report == before


@pytest.mark.parametrize("defect", ["no-tasks", "missing-task", "missing-artifact", "missing-check", "stale",
                                  "role", "tampered-output", "tampered-check", "empty-check", "duplicate-check", "status", "command"])
def test_evidence_fails_closed_without_vacuous_green(tmp_path, runner, mission, defect):
    report = evidence(tmp_path, runner, mission)
    row = report["tasks"][0]
    if defect == "no-tasks":
        report["tasks"] = []
    elif defect == "missing-task":
        report["tasks"].pop()
    elif defect == "missing-artifact":
        row["artifacts"] = []
    elif defect == "missing-check":
        row["checks"] = []
    elif defect == "stale":
        report["mission_sha256"] = "0" * 64
    elif defect == "role":
        row["owner"] = "master-os-builder"
    elif defect == "tampered-output":
        (tmp_path / row["artifacts"][0]["path"]).write_text("different")
    elif defect == "tampered-check":
        (tmp_path / row["checks"][0]["evidence"]["path"]).write_text("different")
    elif defect == "empty-check":
        row["checks"][0]["evidence"] = put(tmp_path, "evidence/empty.txt", b"   ")
    elif defect == "duplicate-check":
        row["checks"].append(copy.deepcopy(row["checks"][0]))
    elif defect == "status":
        row["checks"][0]["status"] = "failed"
    elif defect == "command":
        row["checks"][0]["command"] = ["touch", "never-created"]
    with pytest.raises(runner.ProgramError):
        runner.verify(runner.Workspace(tmp_path), mission, report)
    assert not (tmp_path / "never-created").exists()


def test_blocked_tasks_can_report_missing_outputs_but_cannot_pass(tmp_path, runner, mission):
    report = evidence(tmp_path, runner, mission)
    row = report["tasks"][0]
    row.update(status="blocked", artifacts=[])
    row["checks"][0]["status"] = "blocked"
    result = runner.verify(runner.Workspace(tmp_path), mission, report)
    assert result["valid"] and result["all_reported_checks_passed"] is False
    assert result["blockers"] == [{"task_id": "build", "criterion_id": "contract-tests", "status": "blocked"}]


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../b", "a//b", "a\\b", ".env", "a/.env.local", "credentials/key", ".git/config"])
def test_sensitive_and_escaping_paths_are_rejected_before_read(tmp_path, runner, name):
    with pytest.raises(runner.ProgramError):
        runner.Workspace(tmp_path).read(name)


@pytest.mark.parametrize("kind", ["leaf-symlink", "parent-symlink", "hardlink", "fifo", "oversized", "workspace-symlink"])
def test_reading_rejects_unsafe_files_without_blocking(tmp_path, runner, kind):
    source = tmp_path / "source"
    source.write_text("not secret")
    name, workspace = "input", tmp_path
    if kind == "leaf-symlink":
        (tmp_path / name).symlink_to(source)
    elif kind == "parent-symlink":
        (tmp_path / name).symlink_to(tmp_path, target_is_directory=True)
        name += "/source"
    elif kind == "hardlink":
        os.link(source, tmp_path / name)
    elif kind == "fifo":
        os.mkfifo(tmp_path / name)
    elif kind == "oversized":
        (tmp_path / name).write_bytes(b"x" * (runner.MAX_FILE + 1))
    else:
        (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
        workspace, name = tmp_path / "alias", "source"
    with pytest.raises((runner.ProgramError, OSError)):
        runner.Workspace(workspace).read(name)


@pytest.mark.skipif(not hasattr(os, "O_PATH") or os.geteuid() == 0,
                    reason="Linux non-root regression requires real execute-only ancestry")
def test_native_read_traverses_execute_only_zone_ancestors(tmp_path, runner):
    ancestor = tmp_path / "zone-ancestor"
    workspace = ancestor / "workspace"
    workspace.mkdir(parents=True)
    nested = workspace / "traverse-only"
    nested.mkdir()
    (nested / "input").write_bytes(b"scoped payload")
    ancestor.chmod(0o111)
    nested.chmod(0o111)
    try:
        with pytest.raises(PermissionError):
            os.open(ancestor, os.O_RDONLY | os.O_DIRECTORY)
        assert runner.Workspace(workspace).read("traverse-only/input") == b"scoped payload"
    finally:
        ancestor.chmod(0o700)
        nested.chmod(0o700)


@pytest.mark.parametrize("data", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'\xff', b'[' * 1500])
def test_ambiguous_nonfinite_or_deep_json_is_rejected(runner, data):
    with pytest.raises(runner.ProgramError):
        runner.decode(data)


def test_file_change_during_read_and_total_byte_bound_are_rejected(tmp_path, runner, monkeypatch):
    (tmp_path / "input").write_bytes(b"content")
    native = runner.os.read
    changed = False

    def modifying_read(fd, size):
        nonlocal changed
        result = native(fd, size)
        if not changed:
            changed = True
            (tmp_path / "input").write_bytes(b"changed")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(runner.os, "read", modifying_read)
        with pytest.raises(runner.ProgramError, match="changed-during-read"):
            runner.Workspace(tmp_path).read("input")
    workspace = runner.Workspace(tmp_path)
    workspace.total = runner.MAX_TOTAL
    with pytest.raises(runner.ProgramError, match="read-bound"):
        workspace.read("input")


def test_personal_scope_is_a_namespace_not_a_zone(tmp_path, runner, mission):
    mission["scope"].update(mode="personal-workstation", zone=None, organization=None)
    assert runner.prepare(runner.Workspace(tmp_path), mission)["execution_authorized"] is False


def test_stepper_handoff_is_digest_bound_not_an_authority_grant(tmp_path, runner, mission):
    source = ROOT / "os/stepper/examples/builder-handoff.json"
    handoff = read(source)
    mission["inputs"].append({"kind": "stepper", **put(tmp_path, "inputs/stepper.json", source.read_bytes())})
    assert runner.prepare(runner.Workspace(tmp_path), mission)["execution_authorized"] is False
    for key in ("execution_authorized", "source_verified", "user_accepted", "operational"):
        changed = {**handoff, key: True}
        mission["inputs"][-1].update(put(tmp_path, "inputs/stepper.json", json.dumps(changed).encode()))
        with pytest.raises(runner.ProgramError, match="envelope"):
            runner.prepare(runner.Workspace(tmp_path), mission)
    foreign = {**handoff, "scope": {"zone": "another-client", "instance": "foreign", "organization": "foreign"}}
    mission["inputs"][-1].update(put(tmp_path, "inputs/stepper.json", json.dumps(foreign).encode()))
    with pytest.raises(runner.ProgramError, match="envelope"):
        runner.prepare(runner.Workspace(tmp_path), mission)
    handoff["workflow_sha256"] = "0" * 64
    mission["inputs"][-1].update(put(tmp_path, "inputs/stepper.json", json.dumps(handoff).encode()))
    with pytest.raises(runner.ProgramError, match="workflow-hash"):
        runner.prepare(runner.Workspace(tmp_path), mission)


def test_compiled_all_eleven_profiles_deliver_and_execute_real_skill(tmp_path, runner):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "compiled"
    result = compile_os_to_hermes(BUILDER, output, workspace_root=workspace, zone_id="os", instance_id="builder")
    mission = read(SKILL / "examples/mission.json")
    mission["scope"]["workspace"] = str(workspace)
    put(workspace, "research/librarian.md", (SKILL / "examples/librarian.md").read_bytes())
    put(workspace, "mission.json", json.dumps(mission).encode())
    report = evidence(workspace, runner, mission)
    put(workspace, "evidence.json", json.dumps(report).encode())
    assert len(result["profiles"]) == 11
    for name in result["profiles"]:
        profile = output / "profiles" / name
        native = profile / "skills/builder-execution"
        for source in SKILL.rglob("*"):
            if source.is_file():
                assert (native / source.relative_to(SKILL)).read_bytes() == source.read_bytes()
        assert "skills/" in yaml.safe_load((profile / "distribution.yaml").read_text())["distribution_owned"]
        prepared = cli(native / "scripts/runner.py", workspace, ["prepare", "--mission", "mission.json"])
        assert prepared.returncode == 0, prepared.stderr + prepared.stdout
        assert json.loads(prepared.stdout)["claim"] == "PREPARED_NOT_EXECUTED"
        checked = cli(native / "scripts/runner.py", workspace, ["verify", "--mission", "mission.json", "--evidence", "evidence.json"])
        assert checked.returncode == 0, checked.stderr + checked.stdout
        assert json.loads(checked.stdout)["operational"] is False
    assert not list(output.rglob("__pycache__"))


def test_cli_exit_codes_redaction_and_read_only_files(tmp_path, runner, mission):
    report = evidence(tmp_path, runner, mission)
    put(tmp_path, "mission.json", json.dumps(mission).encode())
    put(tmp_path, "evidence.json", json.dumps(report).encode())
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert cli(RUNNER, tmp_path, ["verify", "--mission", "mission.json", "--evidence", "evidence.json"]).returncode == 0
    assert before == {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    report["tasks"][0]["status"] = report["tasks"][0]["checks"][0]["status"] = "failed"
    put(tmp_path, "evidence.json", json.dumps(report).encode())
    failed = cli(RUNNER, tmp_path, ["verify", "--mission", "mission.json", "--evidence", "evidence.json"])
    assert failed.returncode == 1 and not json.loads(failed.stdout)["all_reported_checks_passed"]
    put(tmp_path, "mission.json", b'{"private-marker-never-echo":"sensitive-fixture"}')
    invalid = cli(RUNNER, tmp_path, ["prepare", "--mission", "mission.json"])
    assert invalid.returncode == 2 and invalid.stderr == b""
    assert b"private-marker" not in invalid.stdout and b"sensitive-fixture" not in invalid.stdout
