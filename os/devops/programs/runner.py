#!/usr/bin/env python3
"""Deterministic DevOps OS programs with no network or provider dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 2 * 1024 * 1024
EVIDENCE_STAGES = {"PREPARED", "OBSERVED", "REPORTED", "VERIFIED", "READ_BACK", "ACCEPTED"}


class ProgramError(ValueError):
    pass


def _regular_file(path: Path) -> bool:
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and not stat.S_ISLNK(mode)


def load_json(path: Path) -> Any:
    path = Path(path)
    if not _regular_file(path):
        raise ProgramError(f"unsafe or missing JSON input: {path}")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ProgramError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProgramError(f"invalid JSON input: {path}") from exc


def file_sha256(path: Path) -> str:
    if not _regular_file(path):
        raise ProgramError(f"unsafe or missing artifact: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_evidence(payload: Any) -> dict[str, Any]:
    required = {
        "evidence_id", "zone_id", "project_id", "mission_id", "subject",
        "claim", "stage", "type", "source", "actor", "created_at",
        "verification_status", "artifact_ref",
    }
    if not isinstance(payload, dict):
        raise ProgramError("evidence root must be an object")
    missing = sorted(required - {key for key, value in payload.items() if value not in (None, "", [], {})})
    if missing:
        raise ProgramError("evidence is missing: " + ", ".join(missing))
    if payload["stage"] not in EVIDENCE_STAGES:
        raise ProgramError("evidence stage is invalid")
    if payload["stage"] in {"READ_BACK", "ACCEPTED"} and not payload.get("verifier"):
        raise ProgramError("read-back and accepted evidence require an independent verifier")
    if payload["stage"] == "ACCEPTED" and payload.get("verification_status") != "passed":
        raise ProgramError("accepted evidence requires passed verification")
    return {
        "schema_version": 1,
        "program": "evidence-ledger-validation",
        "valid": True,
        "evidence_id": payload["evidence_id"],
        "stage": payload["stage"],
        "input_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _diff(expected: Any, observed: Any, prefix: str = "$") -> list[dict[str, Any]]:
    if type(expected) is not type(observed):
        return [{"path": prefix, "kind": "type", "expected": type(expected).__name__, "observed": type(observed).__name__}]
    if isinstance(expected, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(expected) | set(observed)):
            path = f"{prefix}.{key}"
            if key not in expected:
                changes.append({"path": path, "kind": "unexpected"})
            elif key not in observed:
                changes.append({"path": path, "kind": "missing"})
            else:
                changes.extend(_diff(expected[key], observed[key], path))
        return changes
    if isinstance(expected, list):
        changes = []
        if len(expected) != len(observed):
            changes.append({"path": prefix, "kind": "length", "expected": len(expected), "observed": len(observed)})
        for index, pair in enumerate(zip(expected, observed)):
            changes.extend(_diff(pair[0], pair[1], f"{prefix}[{index}]"))
        return changes
    if expected != observed:
        return [{"path": prefix, "kind": "value", "expected": expected, "observed": observed}]
    return []


def drift_report(expected: Any, observed: Any) -> dict[str, Any]:
    differences = _diff(expected, observed)
    return {
        "schema_version": 1,
        "program": "drift-report",
        "state": "IN_SYNC" if not differences else "DRIFT",
        "mutation_performed": False,
        "differences": differences,
        "next_repair_action": None if not differences else "Review the drift and run an explicit versioned reconciliation; do not overwrite runtime state automatically.",
    }


def validate_package(root: Path) -> dict[str, Any]:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ProgramError("package root must be a real directory")
    root = root.resolve()
    semantics = load_json(root / "semantics" / "CONTRACT.json")
    if not isinstance(semantics, dict) or semantics.get("schema_version") != "agk-devops-semantics/v1":
        raise ProgramError("semantic contract version is invalid")
    missing = []
    for relative in semantics.get("required_files", []):
        target = root / str(relative)
        try:
            target.resolve().relative_to(root)
        except (OSError, ValueError) as exc:
            raise ProgramError(f"required path escapes package: {relative}") from exc
        if not _regular_file(target):
            missing.append(str(relative))
    if missing:
        raise ProgramError("package is missing required semantic files: " + ", ".join(missing))
    programs = semantics.get("programs", [])
    required_program_fields = {"id", "entrypoint", "inputs", "outputs", "authority", "idempotency", "recovery"}
    if not isinstance(programs, list) or len(programs) < 3:
        raise ProgramError("semantic contract requires at least three deterministic programs")
    for program in programs:
        if not isinstance(program, dict) or not required_program_fields <= set(program):
            raise ProgramError("deterministic program contract is incomplete")
        if not _regular_file(root / str(program["entrypoint"])):
            raise ProgramError(f"program entrypoint is missing: {program.get('entrypoint')}")
    inputs = load_json(root / "librarian" / "INPUTS.json")
    if not isinstance(inputs, dict) or inputs.get("count") != 15 or len(inputs.get("inputs", [])) != 15:
        raise ProgramError("Librarian ledger must contain exactly 15 inputs")
    if any(not item.get("source_url") or not item.get("decision") or not item.get("mapped_to") for item in inputs["inputs"]):
        raise ProgramError("Librarian input mapping is incomplete")
    recovery = semantics.get("recovery_artifact", {})
    recovery_path = root / str(recovery.get("path") or "")
    if file_sha256(recovery_path) != recovery.get("sha256"):
        raise ProgramError("recovery artifact checksum does not match the semantic contract")
    scenarios = load_json(root / "evals" / "SCENARIOS.json")
    if not isinstance(scenarios, dict) or len(scenarios.get("scenarios", [])) < 8:
        raise ProgramError("semantic contract requires adversarial workflow evaluations")
    return {
        "schema_version": 1,
        "program": "package-validation",
        "valid": True,
        "os_id": semantics.get("os_id"),
        "program_count": len(programs),
        "librarian_inputs": 15,
        "eval_scenarios": len(scenarios["scenarios"]),
        "recovery_sha256": recovery["sha256"],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="devops-program")
    commands = result.add_subparsers(dest="command", required=True)
    package = commands.add_parser("validate-package")
    package.add_argument("--source", type=Path, required=True)
    evidence = commands.add_parser("validate-evidence")
    evidence.add_argument("--input", type=Path, required=True)
    drift = commands.add_parser("drift-report")
    drift.add_argument("--expected", type=Path, required=True)
    drift.add_argument("--observed", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate-package":
            result = validate_package(args.source)
        elif args.command == "validate-evidence":
            result = validate_evidence(load_json(args.input))
        else:
            result = drift_report(load_json(args.expected), load_json(args.observed))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if result.get("state") == "DRIFT" else 0
    except ProgramError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
