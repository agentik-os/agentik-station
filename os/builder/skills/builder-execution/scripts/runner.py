"""Read-only Builder planning and evidence binding; no commands, network or writes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat


SKILL = Path(__file__).absolute().parents[1]
MAX_FILE = 1024 * 1024
MAX_TOTAL = 16 * MAX_FILE
ROLES = {"master-os-builder", "domain-scout", "os-architect", "program-engineer",
         "integration-engineer", "evaluation-engineer", "specification-reviewer",
         "test-engineer", "security-tenancy-reviewer", "recovery-auditor",
         "discord-experience-engineer"}
PROTECTED = {".env", "auth.json", "credentials.json", "secrets.json", "credentials",
             "secrets", "sessions", ".ssh", ".aws", ".git"}


class ProgramError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ProgramError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def decode(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda _value: (_ for _ in ()).throw(ProgramError("non-finite-json")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ProgramError("invalid-json") from error


def relative(value):
    require(isinstance(value, str) and 0 < len(value) <= 240 and not value.startswith("/"), "invalid-relative-path")
    parts = value.split("/")
    require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in {".", ".."}
                and part.lower() not in PROTECTED and not part.lower().startswith(".env")
                for part in parts), "unsafe-relative-path")
    return parts


@contextmanager
def directory(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "workspace-must-be-absolute")
    fds = []
    try:
        # Only traversal is needed. Canonical Zone ancestry can be execute-only
        # (0711), so Linux must not require directory-listing permission.
        flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open("/", flags)
        fds.append(fd)
        for part in path.parts[1:]:
            fd = os.open(part, flags, dir_fd=fd)
            fds.append(fd)
        yield fd
    finally:
        for fd in reversed(fds):
            os.close(fd)


class Workspace:
    def __init__(self, path):
        self.path = str(Path(path))
        self.total = 0

    def read(self, name):
        parts = relative(name)
        with directory(self.path) as root:
            opened = []
            parent = root
            try:
                for part in parts[:-1]:
                    parent = os.open(part, getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    opened.append(parent)
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                opened.append(fd)
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                        and before.st_size <= MAX_FILE, "unsafe-or-oversized-file")
                chunks, size = [], 0
                while size <= MAX_FILE:
                    chunk = os.read(fd, min(65536, MAX_FILE + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                self.total += size
                require(size == before.st_size and size <= MAX_FILE and self.total <= MAX_TOTAL, "read-bound-exceeded")
                signature = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                                          info.st_gid, info.st_nlink, info.st_size,
                                          info.st_mtime_ns, info.st_ctime_ns)
                require(signature(before) == signature(os.fstat(fd)) == signature(
                    os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)), "file-changed-during-read")
                return b"".join(chunks)
            finally:
                for fd in reversed(opened):
                    os.close(fd)

    def json(self, name):
        return decode(self.read(name))

    def bind(self, reference):
        data = self.read(reference["path"])
        require(bool(data.strip()), "empty-evidence-or-input")
        require(hashlib.sha256(data).hexdigest() == reference["sha256"], "artifact-hash-mismatch")
        return data


def validate(value, schema, root=None, depth=0):
    """Closed subset used by these two local schemas; never resolve remote refs."""
    require(depth <= 32, "document-too-deep")
    root = schema if root is None else root
    if "$ref" in schema:
        reference = schema["$ref"]
        require(reference.startswith("#/$defs/") and reference.count("/") == 2, "unsupported-schema-reference")
        return validate(value, root["$defs"][reference.rsplit("/", 1)[1]], root, depth + 1)
    kinds = schema.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    matches = {"object": type(value) is dict, "array": type(value) is list,
               "string": type(value) is str, "integer": type(value) is int,
               "boolean": type(value) is bool, "null": value is None}
    require(not kinds or any(matches[kind] for kind in kinds), "schema-type")
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"], "schema-constant")
    if "enum" in schema:
        require(any(type(value) is type(item) and value == item for item in schema["enum"]), "schema-enum")
    if type(value) is dict:
        properties = schema.get("properties", {})
        require(set(schema.get("required", [])) <= set(value), "missing-field")
        require(schema.get("additionalProperties") is not False or set(value) <= set(properties), "unknown-field")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], root, depth + 1)
    elif type(value) is list:
        require(schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000), "array-bound")
        if schema.get("uniqueItems"):
            require(len({canonical(item) for item in value}) == len(value), "duplicate-array-value")
        for item in value:
            validate(item, schema["items"], root, depth + 1)
    elif type(value) is str:
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10000), "string-bound")
        require(not value or bool(value.strip()), "blank-string")
        if "pattern" in schema:
            require(re.fullmatch(schema["pattern"], value) is not None, "string-pattern")
    elif type(value) is int:
        require(schema.get("minimum", -1000000) <= value <= schema.get("maximum", 1000000), "integer-bound")


def schema(name):
    return Workspace(SKILL).json("schemas/" + name + ".schema.json")


def _unique(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), "duplicate-identifier")
    return result


def _stepper(data):
    value = decode(data)
    fields = {"schema_version", "valid", "kind", "source_os", "target_os", "workflow", "workflow_sha256",
              "artifact_sha256", "claim", "execution_authorized", "source_verified", "user_accepted", "operational"}
    # The canonical envelope has no scope. Reject an added scope rather than
    # silently accepting a foreign client/Zone/instance or treating it as authority.
    require(type(value) is dict and set(value) == fields and value.get("valid") is True
            and value.get("kind") == "StepperHandoff"
            and type(value.get("schema_version")) is int and value["schema_version"] == 1
            and value.get("source_os") == "stepper-os" and value.get("target_os") == "builder-os"
            and value.get("claim") == "PREPARED_NOT_EXECUTED"
            and all(value.get(key) is False for key in ("execution_authorized", "source_verified", "user_accepted", "operational")),
            "invalid-stepper-handoff-envelope")
    require(type(value.get("workflow")) is dict and value.get("workflow_sha256") == digest(value["workflow"]),
            "stepper-workflow-hash-mismatch")
    artifacts = value["workflow"].get("artifacts")
    require(type(artifacts) is dict and set(artifacts) == {"story-map", "slice-thin", "shape-bet", "sequence-releases"}
            and value.get("artifact_sha256") == {name: digest(item) for name, item in artifacts.items()},
            "stepper-artifact-hash-mismatch")


def mission(workspace, value):
    validate(value, schema("mission"))
    require(value["scope"]["workspace"] == workspace.path, "workspace-binding-mismatch")
    scope = value["scope"]
    require((scope["mode"] == "zone" and scope["zone"] is not None)
            or (scope["mode"] == "personal-workstation" and scope["zone"] is None and scope["organization"] is None),
            "scope-boundary-mismatch")
    relative(value["target"]["package_root"])
    inputs = _unique(value["inputs"], "path")
    require(sum(item["kind"] == "librarian" for item in inputs.values()) == 1, "one-librarian-handoff-required")
    require(sum(item["kind"] == "stepper" for item in inputs.values()) <= 1, "ambiguous-stepper-handoff")
    for reference in inputs.values():
        data = workspace.bind(reference)
        if reference["kind"] == "stepper":
            _stepper(data)
    tasks = _unique(value["tasks"], "id")
    criteria = _unique(value["criteria"], "id")
    require({"deterministic", "independent-review", "recovery"} <= {row["kind"] for row in criteria.values()},
            "missing-delivery-gate-kind")
    covered, outputs = [], []
    require(sum(task["max_turns"] for task in tasks.values()) <= value["turn_budget"], "turn-allocation-exceeds-budget")
    for task in tasks.values():
        require(task["owner"] in ROLES and task["verifier"] in ROLES and task["owner"] != task["verifier"],
                "independent-canonical-verifier-required")
        require(set(task["depends_on"]) <= set(tasks) and task["id"] not in task["depends_on"], "invalid-dependency")
        require(set(task["criteria"]) <= set(criteria), "unknown-criterion")
        for criterion in task["criteria"]:
            require(criteria[criterion]["verifier"] == task["verifier"], "criterion-verifier-mismatch")
        covered += task["criteria"]
        for output in task["outputs"]:
            relative(output)
            require(output not in inputs, "output-overwrites-input")
            outputs.append(output)
    require(set(covered) == set(criteria) and len(covered) == len(criteria), "criteria-must-have-exactly-one-task")
    require(len(set(outputs)) == len(outputs) and all(not right.startswith(left + "/")
            for left in outputs for right in outputs if left != right), "overlapping-output-ownership")
    require(all(not output.startswith(path + "/") and not path.startswith(output + "/")
                for output in outputs for path in inputs), "output-overwrites-input")
    require(any(path.startswith(value["target"]["package_root"] + "/") for path in outputs), "no-package-deliverable")
    done, waves = set(), []
    while len(done) < len(tasks):
        ready = sorted(key for key, task in tasks.items() if key not in done and set(task["depends_on"]) <= done)
        require(bool(ready), "cyclic-task-graph")
        waves.append(ready)
        done.update(ready)
    package_tasks = {key for key, task in tasks.items() if any(
        path.startswith(value["target"]["package_root"] + "/") for path in task["outputs"])}
    ancestors = {}
    for wave in waves:
        for key in wave:
            task = tasks[key]
            ancestors[key] = set(task["depends_on"])
            for dependency in task["depends_on"]:
                ancestors[key].update(ancestors[dependency])
            kinds = {criteria[item]["kind"] for item in task["criteria"]}
            if "independent-review" in kinds:
                require(package_tasks <= ancestors[key], "review-must-follow-package-delivery")
                require(task["verifier"] not in {tasks[item]["owner"] for item in ancestors[key]},
                        "reviewer-authored-upstream-work")
    return tasks, criteria, waves


def prepare(workspace, value):
    tasks, criteria, waves = mission(workspace, value)
    packets = []
    for wave in waves:
        for key in wave:
            task = tasks[key]
            context = {"mission_id": value["mission_id"], "mission_sha256": digest(value),
                       "scope": value["scope"], "target": value["target"], "brief": value["brief"],
                       "inputs": value["inputs"], "task": task,
                       "acceptance": [criteria[item] for item in task["criteria"]]}
            packets.append({"task_id": key, "owner_role": task["owner"], "verifier_role": task["verifier"],
                            "max_turns": task["max_turns"], "native_profile": None,
                            "query": "Execute only this authorized scoped task after its dependencies pass. "
                                     "A canonical role label is not a native profile selector or authorization. "
                                     "Return declared artifacts, failures and evidence; never claim unrun checks.\n"
                                     + canonical(context).decode()})
    return {"schema_version": 1, "kind": "BuilderPlan", "mission_sha256": digest(value),
            "claim": "PREPARED_NOT_EXECUTED", "dependency_waves": waves, "packets": packets,
            "execution_authorized": False, "source_verified": False, "operational": False}


def verify(workspace, value, evidence):
    tasks, criteria, _waves = mission(workspace, value)
    validate(evidence, schema("evidence"))
    require(evidence["mission_sha256"] == digest(value), "stale-mission-evidence")
    reports = _unique(evidence["tasks"], "task_id")
    require(set(reports) == set(tasks), "incomplete-task-evidence")
    blockers, artifacts, evidence_paths = [], set(), set()
    for task_id, task in tasks.items():
        report = reports[task_id]
        require(report["owner"] == task["owner"] and report["verifier"] == task["verifier"], "evidence-role-mismatch")
        outputs = _unique(report["artifacts"], "path")
        require(set(outputs) <= set(task["outputs"]) and
                (report["status"] != "passed" or set(outputs) == set(task["outputs"])), "incomplete-artifact-evidence")
        for artifact in outputs.values():
            workspace.bind(artifact)
            artifacts.add(artifact["path"])
        checks = _unique(report["checks"], "criterion_id")
        require(set(checks) == set(task["criteria"]), "incomplete-criterion-evidence")
        for key, check in checks.items():
            workspace.bind(check["evidence"])
            evidence_paths.add(check["evidence"]["path"])
            if check["status"] != "passed":
                blockers.append({"task_id": task_id, "criterion_id": key, "status": check["status"]})
        require((report["status"] == "passed") == all(check["status"] == "passed" for check in checks.values()),
                "inconsistent-task-status")
    return {"schema_version": 1, "kind": "BuilderEvidenceCheck", "valid": True,
            "mission_sha256": digest(value), "claim": "EVIDENCE_BOUND_NOT_ACCEPTED",
            "all_reported_checks_passed": not blockers, "blockers": blockers,
            "artifact_files_bound": len(artifacts), "check_files_bound": len(evidence_paths),
            "reviewer_identity_verified": False, "execution_verified": False,
            "external_readback_verified": False, "user_accepted": False, "operational": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        child = commands.add_parser(name)
        child.add_argument("--workspace", required=True)
        child.add_argument("--mission", required=True, help="Relative workspace JSON; no secret inputs")
        if name == "verify":
            child.add_argument("--evidence", required=True, help="Relative workspace JSON; no commands are executed")
    args = parser.parse_args(argv)
    try:
        workspace = Workspace(args.workspace)
        value = workspace.json(args.mission)
        result = prepare(workspace, value) if args.command == "prepare" else verify(workspace, value, workspace.json(args.evidence))
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("all_reported_checks_passed", True) else 1
    except (ProgramError, OSError, UnicodeError, RecursionError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"valid": False, "code": str(error) if isinstance(error, ProgramError) else "unsafe-or-invalid-input",
                          "operational": False, "next_action": "Repair scoped inputs or evidence; nothing was executed."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
