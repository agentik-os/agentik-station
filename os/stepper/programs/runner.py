#!/usr/bin/env python3
"""Read-only, standard-library Stepper artifact and workflow validation.

No model calls, network, subprocesses, account inspection or artifact writes.
Schema validity is not source verification, authorization or user acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("story-map", "slice-thin", "shape-bet", "sequence-releases")
MAX_BYTES = 1024 * 1024


class ProgramError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProgramError("Duplicate JSON field")
        result[key] = value
    return result


def load_json(path):
    path = Path(path).absolute()
    if len(path.parts) < 2 or ".." in path.parts:
        raise ProgramError("Input requires a canonical file path without parent traversal")
    # Resolve each component through the previously opened directory. A rename
    # or symlink substitution cannot redirect the final read to another tree.
    # O_PATH needs traversal, not directory-listing permission on Host 0711
    # anchors; the read-only fallback is for personal macOS paths.
    directory_flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory_fd = fd = None
    try:
        directory_fd = os.open(path.anchor, directory_flags)
        for part in path.parts[1:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            raise ProgramError("Input must be bounded, regular and not hard-linked")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ProgramError("Input exceeds size limit")
        def reject_constant(_):
            raise ProgramError("Non-finite JSON is unsupported")
        result = json.loads(data, object_pairs_hook=_unique, parse_constant=reject_constant)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 40 or isinstance(value, float) and not math.isfinite(value):
                raise ProgramError("Input exceeds depth or numeric limits")
            if isinstance(value, dict):
                pending.extend((v, depth + 1) for v in value.values())
            elif isinstance(value, list):
                pending.extend((v, depth + 1) for v in value)
        return result
    except OSError:
        raise ProgramError("Input path is unavailable or is not a real directory chain and regular file") from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_schema(value, schema, depth=0):
    """Implement only the reviewed JSON Schema subset used by this package."""
    known = {"$schema", "type", "properties", "required", "additionalProperties", "items", "enum", "const",
             "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems", "minimum", "maximum"}
    if depth > 40 or not isinstance(schema, dict) or set(schema) - known:
        raise ProgramError("Unsupported schema contract")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ProgramError("Constant field mismatch")
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        raise ProgramError("Value is outside the declared choices")
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    kind = schema.get("type")
    if kind is not None and (kind not in types or type(value) is not types[kind]):
        raise ProgramError("Field type mismatch")
    if kind == "object":
        fields = schema.get("properties", {})
        if not set(schema.get("required", [])) <= set(value):
            raise ProgramError("Required field missing")
        if schema.get("additionalProperties") is False and set(value) - set(fields):
            raise ProgramError("Unexpected field")
        for key in value.keys() & fields.keys():
            validate_schema(value[key], fields[key], depth + 1)
    elif kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 100):
            raise ProgramError("Array size outside declared limits")
        if schema.get("uniqueItems") and len({canonical(item) for item in value}) != len(value):
            raise ProgramError("Duplicate array item")
        for item in value:
            validate_schema(item, schema["items"], depth + 1)
    elif kind == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 4000):
            raise ProgramError("Text length outside declared limits")
        if schema.get("minLength", 0) and not value.strip():
            raise ProgramError("Required text must not be blank")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ProgramError("Text format mismatch")
    elif kind == "integer":
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ProgramError("Number outside declared limits")


def _validate_map(mapping):
    activities = mapping["activities"]
    ids = [item["id"] for item in activities]
    tasks = [task["id"] for item in activities for task in item["tasks"]]
    if len(set(ids)) != len(ids) or len(set(tasks)) != len(tasks):
        raise ProgramError("Map identities must be unique")


def _validate_slices(slices):
    ids = {item["id"] for item in slices}
    if len(ids) != len(slices):
        raise ProgramError("Slice identities must be unique")
    dependencies = {item["id"]: set(item["dependencies"]) for item in slices}
    if any(not deps <= ids or name in deps for name, deps in dependencies.items()):
        raise ProgramError("Slice dependencies contain unknown or self references")
    # Validate acyclicity without imposing delivery order on an input backlog.
    # This is a bounded consistency check, not a scheduler or execution plan.
    remaining, visited = set(ids), set()
    while remaining:
        ready = {name for name in remaining if dependencies[name] <= visited}
        if not ready:
            raise ProgramError("Slice dependency graph is cyclic")
        visited.update(ready)
        remaining.difference_update(ready)


def validate_artifact(skill, payload, kind="output"):
    if skill not in SKILLS or kind not in {"input", "output"}:
        raise ProgramError("Unknown skill or artifact kind")
    validate_schema(payload, load_json(ROOT / "skills" / skill / f"{kind}.schema.json"))
    if (kind, skill) in {("output", "story-map"), ("input", "slice-thin")}:
        _validate_map(payload["map"])
    if kind == "input" and skill == "sequence-releases":
        _validate_slices(payload["slices"])
    if kind == "output" and skill == "slice-thin" and payload["slice"]["id"] in payload["slice"]["dependencies"]:
        raise ProgramError("Selected slice must not depend on itself")
    if kind == "output" and skill == "sequence-releases":
        rows = payload["sequence"]
        if rows[0]["kind"] != "walking-skeleton":
            raise ProgramError("First release must be a walking skeleton")
        seen = set()
        for position, row in enumerate(rows, 1):
            if row["position"] != position or row["slice_id"] in seen or not set(row["depends_on"]) <= seen:
                raise ProgramError("Release sequence has duplicate, forward, cyclic or unknown dependencies")
            seen.add(row["slice_id"])
    return {"schema_version": 1, "skill": skill, "kind": kind, "valid": True,
            "state": "SCHEMA_VALIDATED", "input_sha256": content_hash(payload),
            "source_verified": False, "user_accepted": False, "operational": False}


def validate_transition(skill, source, output):
    validate_artifact(skill, source, "input")
    validate_artifact(skill, output)
    if skill == "story-map":
        if source["role"] != output["map"]["actor"] or source["journey"] != output["map"]["journey"]:
            raise ProgramError("Story map must preserve the supplied actor and journey")
    elif skill == "slice-thin":
        if source["outcome"] != output["slice"]["outcome"]:
            raise ProgramError("Slice must preserve the supplied outcome")
        if set(output["slice"]["activity_ids"]) != {row["id"] for row in source["map"]["activities"]}:
            raise ProgramError("Slice must cover the supplied journey activities")
    elif skill == "shape-bet":
        if source["problem"] != output["pitch"]["problem"]:
            raise ProgramError("Pitch must preserve the supplied problem")
        if source["appetite"] != output["pitch"]["appetite"]:
            raise ProgramError("Pitch must preserve the supplied appetite")
    else:
        slices = {row["id"]: row for row in source["slices"]}
        if set(slices) != {row["slice_id"] for row in output["sequence"]}:
            raise ProgramError("Release sequence must preserve the supplied slice inventory")
        for row in output["sequence"]:
            selected = slices[row["slice_id"]]
            if selected["strategy"] != row["kind"] or set(selected["dependencies"]) != set(row["depends_on"]):
                raise ProgramError("Release sequence must preserve each supplied slice strategy and dependencies")
    return {"schema_version": 1, "skill": skill, "valid": True, "state": "TRANSITION_VALIDATED",
            "input_sha256": content_hash(source), "output_sha256": content_hash(output),
            "source_verified": False, "user_accepted": False, "operational": False}


def validate_workflow(payload):
    if not isinstance(payload, dict) or set(payload) not in ({"workflow", "artifacts"}, {"workflow", "artifacts", "inputs"}):
        raise ProgramError("Workflow requires its identity and typed artifacts")
    definitions = load_json(ROOT / "workflows/WORKFLOWS.json")["workflows"]
    flow = next((item for item in definitions if item["id"] == payload["workflow"]), None)
    if flow is None or not isinstance(payload["artifacts"], dict):
        raise ProgramError("Unknown workflow")
    names = [step["skill"] for step in flow["steps"]]
    if set(payload["artifacts"]) != set(names):
        raise ProgramError("Workflow artifacts are incomplete or unexpected")
    receipts = [validate_artifact(name, payload["artifacts"][name]) for name in names]
    artifacts = payload["artifacts"]
    selected = artifacts["slice-thin"]["slice"]
    sequence = artifacts["sequence-releases"]["sequence"]
    release = next((row for row in sequence if row["slice_id"] == selected["id"]), None)
    if release is None:
        raise ProgramError("Selected slice is absent from the release sequence")
    # Dependencies are an unordered set of identities, but both independently
    # valid artifacts must describe the same handoff and delivery strategy.
    if set(selected["dependencies"]) != set(release["depends_on"]):
        raise ProgramError("Selected slice dependencies differ from the release sequence")
    if selected["strategy"] != release["kind"]:
        raise ProgramError("Selected slice strategy differs from the release sequence")
    if selected["strategy"] == "walking-skeleton" and (release["position"] != 1 or selected["dependencies"]):
        raise ProgramError("Selected walking skeleton must be the first dependency-free release")
    if payload["workflow"] == "step-loop":
        map_ids = {activity["id"] for activity in artifacts["story-map"]["map"]["activities"]}
        if set(selected["activity_ids"]) != map_ids:
            raise ProgramError("Walking skeleton must cover the declared journey activities")
    transitions = []
    if "inputs" in payload:
        inputs = payload["inputs"]
        if not isinstance(inputs, dict) or set(inputs) != set(names):
            raise ProgramError("Workflow inputs must cover every declared skill")
        transitions = [validate_transition(name, inputs[name], artifacts[name]) for name in names]
        if payload["workflow"] == "step-loop" and inputs["slice-thin"]["map"] != artifacts["story-map"]["map"]:
            raise ProgramError("Slicing input differs from the preceding story map")
        supplied_slice = next(row for row in inputs["sequence-releases"]["slices"] if row["id"] == selected["id"])
        if supplied_slice != selected:
            raise ProgramError("Sequencing input differs from the selected slice")
    return {"schema_version": 1, "workflow": payload["workflow"], "valid": True, "checks": receipts,
            "state": "ARTIFACTS_VALIDATED", "input_bound": "inputs" in payload, "transitions": transitions,
            "workflow_sha256": content_hash(payload), "source_verified": False, "user_accepted": False, "operational": False}


def prepare_handoff(workflow):
    receipt = validate_workflow(workflow)
    if workflow["workflow"] != "step-loop" or not receipt["input_bound"]:
        raise ProgramError("Builder handoff requires a complete input-bound step-loop")
    result = {"schema_version": 1, "kind": "StepperHandoff", "valid": True,
              "source_os": "stepper-os", "target_os": "builder-os",
              "workflow": json.loads(canonical(workflow)), "workflow_sha256": receipt["workflow_sha256"],
              "artifact_sha256": {name: content_hash(workflow["artifacts"][name]) for name in SKILLS},
              "claim": "PREPARED_NOT_EXECUTED", "execution_authorized": False,
              "source_verified": False, "user_accepted": False, "operational": False}
    validate_schema(result, load_json(ROOT / "data/HANDOFF.schema.json"))
    return result


def validate_handoff(payload):
    validate_schema(payload, load_json(ROOT / "data/HANDOFF.schema.json"))
    if payload != prepare_handoff(payload["workflow"]):
        raise ProgramError("Handoff hashes or declarations differ from its artifacts")
    return {"schema_version": 1, "program": "handoff-check", "valid": True,
            "handoff_sha256": content_hash(payload), "state": "HANDOFF_VALIDATED",
            "execution_authorized": False, "source_verified": False, "user_accepted": False, "operational": False}


def evaluate():
    cases = load_json(ROOT / "evals/CASES.json")["cases"]
    rows = []
    for case in cases:
        try:
            if case["kind"] == "workflow":
                validate_workflow(case["input"])
            elif case["kind"] == "transition":
                validate_transition(case["skill"], case["input"], case["output"])
            elif case["kind"] == "handoff":
                prepare_handoff(case["input"])
            else:
                validate_artifact(case["skill"], case["input"], case.get("artifact_kind", "output"))
            accepted = True
        except ProgramError:
            accepted = False
        rows.append({"id": case["id"], "passed": accepted is case["valid"]})
    return {"schema_version": 1, "program": "evaluate", "valid": bool(rows) and all(row["passed"] for row in rows),
            "cases": rows, "scope": "deterministic-contracts-not-model-behavior", "operational": False}


def validate_package():
    contract = load_json(ROOT / "semantics/CONTRACT.json")
    if contract.get("schema_version") != "station-stepper-semantics/v1" or contract.get("skills") != list(SKILLS):
        raise ProgramError("Invalid Stepper semantic contract")
    for relative in contract["required_files"]:
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ProgramError("Package path escapes canonical source")
        item = ROOT / relative
        if not item.is_file() or item.is_symlink():
            raise ProgramError("Required package file missing or unsafe")
    for skill in SKILLS:
        validate_transition(skill, load_json(ROOT / "examples" / f"{skill}.input.json"),
                            load_json(ROOT / "examples" / f"{skill}.json"))
    validate_handoff(load_json(ROOT / "examples/builder-handoff.json"))
    result = evaluate()
    if not result["valid"]:
        raise ProgramError("Deterministic evaluation failed")
    return {"schema_version": 1, "program": "validate-package", "valid": True,
            "os_id": "stepper-os", "profiles": ["map-steward", "shaper", "sequencer"],
            "skills": list(SKILLS), "evaluations": len(result["cases"]), "operational": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    artifact = sub.add_parser("validate")
    artifact.add_argument("--skill", choices=SKILLS, required=True)
    artifact.add_argument("--kind", choices=("input", "output"), default="output")
    artifact.add_argument("--input", type=Path, required=True)
    workflow = sub.add_parser("workflow")
    workflow.add_argument("--input", type=Path, required=True)
    transition = sub.add_parser("transition")
    transition.add_argument("--skill", choices=SKILLS, required=True)
    transition.add_argument("--input", type=Path, required=True)
    transition.add_argument("--output", type=Path, required=True)
    for command in ("handoff", "handoff-check"):
        handoff = sub.add_parser(command)
        handoff.add_argument("--input", type=Path, required=True)
    sub.add_parser("evaluate")
    sub.add_parser("validate-package")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_artifact(args.skill, load_json(args.input), args.kind)
        elif args.command == "workflow":
            result = validate_workflow(load_json(args.input))
        elif args.command == "transition":
            result = validate_transition(args.skill, load_json(args.input), load_json(args.output))
        elif args.command == "handoff":
            result = prepare_handoff(load_json(args.input))
        elif args.command == "handoff-check":
            result = validate_handoff(load_json(args.input))
        elif args.command == "evaluate":
            result = evaluate()
        else:
            result = validate_package()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 1
    except ProgramError as error:
        # ProgramError messages are reviewed static explanations, never payload
        # values, paths or native exception text. Preserve actionable failures.
        print(json.dumps({"valid": False, "error": "STEPPER_CONTRACT_REJECTED", "reason": str(error)[:240],
                          "operational": False}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print(json.dumps({"valid": False, "error": "Stepper input or contract validation failed", "operational": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
