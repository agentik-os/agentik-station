from __future__ import annotations

import json
import hashlib
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .identifiers import validate_identifier, validate_version

REQUIRED_PATHS = [
    "OS.yaml",
    "CONTRACT.json",
    "MANIFEST.json",
    "MATURITY.json",
    "README.md",
    "1_MASTER/README.md",
    "director/PROFILE.md",
    "team/TEAM.yaml",
    "skills/ORDER.yaml",
    "programs/PROGRAMS.yaml",
    "capabilities/CAPABILITIES.yaml",
    "integrations/INTEGRATIONS.yaml",
    "knowledge/SCOPE.yaml",
    "memory/SCOPE.yaml",
    "data/SCHEMA.json",
    "missions/MISSION_SCHEMA.json",
    "workflows/WORKFLOWS.yaml",
    "automations/AUTOMATIONS.yaml",
    "providers/ROUTES.yaml",
    "harness/POLICY.yaml",
    "evals/EVALS.yaml",
    "evidence/SCHEMA.json",
    "discord/COMMANDS.yaml",
    "discord/EXPERIENCE.yaml",
    "discord/BOT.yaml",
    "views/VIEWS.yaml",
    "doctor/DOCTOR.yaml",
    "update/MIGRATIONS.yaml",
    "rollback/ROLLBACK.yaml",
    "recovery/RECOVERY.yaml",
    "governance/POLICY.yaml",
    "self_improvement/POLICY.yaml",
    "librarian/14_BUILDER_HANDOFF.md",
    "deployment/DEPLOYMENT.yaml",
    "orchestration/ORCHESTRATION.yaml",
    "orchestration/ACCEPTANCE.md",
    "hermes/distribution.yaml",
    "hermes/config.template.yaml",
]

@dataclass
class OSDoctorResult:
    os_id: str
    ok: bool = True
    checks: list[dict[str, str]] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)

    def passed(self, name: str, detail: str = "") -> None:
        item = {"name": name, "status": "PASS"}
        if detail:
            item["detail"] = detail
        self.checks.append(item)

    def failed(self, name: str, message: str, next_action: str) -> None:
        self.ok = False
        self.issues.append({"name": name, "status": "FAIL", "message": message, "next_repair_action": next_action})

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "os_id": self.os_id, "ok": self.ok, "checks": self.checks, "issues": self.issues}


def _safe_regular(path: Path, root: Path) -> bool:
    try:
        resolved_parent = path.parent.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
        if not resolved_parent.is_relative_to(root_resolved):
            return False
        st = os.lstat(path)
        return stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode)
    except (OSError, RuntimeError):
        return False


def _safe_json(path: Path, root: Path) -> dict[str, Any]:
    if not _safe_regular(path, root):
        raise ValueError(f"missing or unsafe semantic JSON: {path.relative_to(root)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"semantic JSON root must be an object: {path.relative_to(root)}")
    return value


def _doctor_devops_semantics(path: Path, result: OSDoctorResult) -> None:
    required = [
        "semantics/CONTRACT.json",
        "programs/runner.py",
        "tools/CONTRACTS.json",
        "providers/ROUTES.json",
        "workflows/STATE_MACHINE.json",
        "evals/SCENARIOS.json",
        "librarian/INPUTS.json",
        "recovery/BASELINE.json",
        "data/CLIENT_OPERATIONS.schema.json",
        "discord/COMPONENTS.json",
    ]
    for relative in required:
        if not _safe_regular(path / relative, path):
            result.failed(
                f"semantic:file:{relative}",
                f"Missing or unsafe DevOps semantic file: {relative}",
                "Restore the typed DevOps semantic contract file.",
            )
            return
    try:
        semantics = _safe_json(path / "semantics/CONTRACT.json", path)
        if semantics.get("schema_version") != "agk-devops-semantics/v1":
            raise ValueError("semantic contract version is invalid")
        team = semantics.get("team")
        expected_team = {"atlas", "architect", "forge", "sentinel", "release-engineer", "sre"}
        if not isinstance(team, list) or set(team) != expected_team or len(team) != 6:
            raise ValueError("semantic contract requires exactly six canonical identities")
        programs = semantics.get("programs")
        program_fields = {"id", "entrypoint", "inputs", "outputs", "authority", "idempotency", "recovery"}
        if not isinstance(programs, list) or len(programs) < 3:
            raise ValueError("semantic contract requires deterministic programs")
        if any(not isinstance(item, dict) or not program_fields <= set(item) for item in programs):
            raise ValueError("deterministic program contract is incomplete")
        for item in programs:
            entrypoint = path / str(item["entrypoint"])
            if not _safe_regular(entrypoint, path) or not os.access(entrypoint, os.X_OK):
                raise ValueError(f"program entrypoint is missing or not executable: {item['entrypoint']}")
        result.passed("semantic:contract", "six identities and typed programs")

        tools = _safe_json(path / "tools/CONTRACTS.json", path)
        contracts = tools.get("contracts")
        tool_fields = {"role", "tool", "class", "auth_owner", "timeout_seconds", "idempotency", "approval", "audit", "fallback"}
        if tools.get("default") != "deny" or not isinstance(contracts, list) or not contracts:
            raise ValueError("tool contract must be non-empty and default deny")
        if any(not isinstance(item, dict) or not tool_fields <= set(item) for item in contracts):
            raise ValueError("role tool contract is incomplete")
        if {str(item["role"]) for item in contracts} != expected_team:
            raise ValueError("every canonical identity must own an explicit tool contract")
        forbidden = set(tools.get("always_forbidden", []))
        if not {"database.delete", "secret.export", "cross-zone.default-account-fallback"} <= forbidden:
            raise ValueError("tool contract omits hard forbidden actions")
        result.passed("semantic:tools", f"{len(contracts)} explicit role contracts")

        routes = _safe_json(path / "providers/ROUTES.json", path)
        route_items = routes.get("routes")
        if not isinstance(route_items, list) or {str(item.get("role")) for item in route_items if isinstance(item, dict)} != expected_team:
            raise ValueError("provider routes must cover exactly the canonical team")
        if any(not item.get("fallback") or not item.get("budget") or not item.get("on_exhaustion") for item in route_items):
            raise ValueError("provider route fallback/budget/degraded behavior is incomplete")
        result.passed("semantic:provider-routes", "task routes, budgets and degraded behavior")

        workflow = _safe_json(path / "workflows/STATE_MACHINE.json", path)
        states = set(workflow.get("states", []))
        transitions = workflow.get("transitions")
        if workflow.get("protocol") != "agk-work-tracker/v1" or not isinstance(transitions, dict):
            raise ValueError("tracker-neutral state machine is invalid")
        if set(transitions) != states or any(not set(targets) <= states for targets in transitions.values()):
            raise ValueError("workflow transitions do not close over declared states")
        if workflow.get("authorization", {}).get("production_requires_distinct_human_approval") is not True:
            raise ValueError("production approval contract is not fail-closed")
        if set(workflow.get("receipts", {})) != {"start", "transition", "release", "completion"}:
            raise ValueError("workflow receipt contract is incomplete")
        result.passed("semantic:workflow", f"{len(states)} states with closed transitions")

        librarian = _safe_json(path / "librarian/INPUTS.json", path)
        inputs = librarian.get("inputs")
        if librarian.get("count") != 15 or not isinstance(inputs, list) or len(inputs) != 15:
            raise ValueError("Librarian ledger must contain exactly 15 inputs")
        ids = {str(item.get("id")) for item in inputs if isinstance(item, dict)}
        if len(ids) != 15 or any(not item.get("source_url") or not item.get("decision") or not item.get("mapped_to") or not item.get("limitation") for item in inputs):
            raise ValueError("Librarian source mapping is incomplete")
        result.passed("semantic:librarian", "15 sourced and mapped inputs")

        recovery = semantics.get("recovery_artifact", {})
        recovery_path = path / str(recovery.get("path") or "")
        digest = hashlib.sha256(recovery_path.read_bytes()).hexdigest() if _safe_regular(recovery_path, path) else ""
        if not digest or digest != recovery.get("sha256"):
            raise ValueError("recovery artifact checksum mismatch")
        result.passed("semantic:recovery", digest)

        scenarios = _safe_json(path / "evals/SCENARIOS.json", path).get("scenarios")
        scenario_types = {str(item.get("type")) for item in scenarios if isinstance(item, dict)} if isinstance(scenarios, list) else set()
        if not isinstance(scenarios, list) or len(scenarios) < 8 or not {"authority", "isolation", "authorization", "workflow", "release", "recovery"} <= scenario_types:
            raise ValueError("adversarial evaluation coverage is incomplete")
        result.passed("semantic:evals", f"{len(scenarios)} scenarios")

        discord = _safe_json(path / "discord/COMPONENTS.json", path)
        controls = discord.get("controls")
        if not isinstance(controls, list) or not {"approve-production", "deploy-production", "rollback", "provider-setup"} <= {str(item.get("id")) for item in controls if isinstance(item, dict)}:
            raise ValueError("Discord control surface lacks governed actions")
        if discord.get("security", {}).get("callback_identity_checked_outside_model") is not True:
            raise ValueError("Discord callback authorization is not fail-closed")
        result.passed("semantic:discord", f"{len(controls)} authorized controls")

        operations = _safe_json(path / "data/CLIENT_OPERATIONS.schema.json", path)
        operation_fields = set(operations.get("required", []))
        if not {"service_catalog", "environments", "pipelines", "reliability", "incidents", "backups", "dependencies", "costs", "access", "offboarding", "knowledge"} <= operation_fields:
            raise ValueError("client operations schema is incomplete")
        result.passed("semantic:client-operations", f"{len(operation_fields)} required sections")
    except Exception as exc:
        result.failed(
            "semantic:devops",
            str(exc),
            "Repair the typed DevOps semantic contract, program, workflow, evidence, or recovery artifact and rerun Doctor.",
        )


def doctor_os_source(path: Path, expected_id: str | None = None) -> OSDoctorResult:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValidationError(f"OS source must be a real directory: {path}")
    contract_path = path / "CONTRACT.json"
    os_id = expected_id or path.name
    result = OSDoctorResult(os_id=os_id)

    for relative in REQUIRED_PATHS:
        target = path / relative
        if _safe_regular(target, path):
            result.passed(f"file:{relative}")
        else:
            result.failed(f"file:{relative}", f"Missing or unsafe required OS file: {relative}", "Restore the canonical AGK OS v2 source contract file.")

    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract.get("schema_version") != "agk-os/v2":
            raise ValueError("CONTRACT.json schema_version must be agk-os/v2")
        contract_id = validate_identifier(str(contract["os_id"]), "OS id")
        if expected_id and contract_id != expected_id:
            raise ValueError(f"OS id {contract_id!r} differs from catalog id {expected_id!r}")
        validate_version(str(contract.get("version", "")))
        if not isinstance(contract.get("nanoteam"), list) or not contract["nanoteam"]:
            raise ValueError("CONTRACT.json requires a non-empty nanoteam")
        result.os_id = contract_id
        result.passed("contract:identity", contract_id)
    except Exception as exc:
        result.failed("contract:identity", str(exc), "Repair CONTRACT.json to the canonical AGK OS v2 schema.")

    try:
        manifest = json.loads((path / "MANIFEST.json").read_text(encoding="utf-8"))
        if manifest.get("contract") != "AGK OS v2" or manifest.get("id") != result.os_id:
            raise ValueError("MANIFEST.json identity/contract mismatch")
        result.passed("manifest")
    except Exception as exc:
        result.failed("manifest", str(exc), "Repair MANIFEST.json identity and AGK OS contract declaration.")

    try:
        maturity = json.loads((path / "MATURITY.json").read_text(encoding="utf-8"))
        if maturity.get("source_maturity") not in {"INSTALLABLE", "VERIFIED", "OPERATIONAL"}:
            raise ValueError("source_maturity must be INSTALLABLE or higher for a canonical release package")
        if maturity.get("runtime_state") not in {"NOT_INSTALLED", "INSTALLING", "CONFIGURED", "VERIFIED", "OPERATIONAL", "DEGRADED"}:
            raise ValueError("invalid runtime_state")
        result.passed("maturity", str(maturity.get("source_maturity")))
    except Exception as exc:
        result.failed("maturity", str(exc), "Repair MATURITY.json without overstating runtime evidence.")

    # Dedicated bot + plan-first/evidence checks are hard release invariants.
    for rel, needles in {
        "discord/BOT.yaml": ["dedicated", "profile:"],
        "harness/POLICY.yaml": ["plan_first: true", "evidence_before_claims: true"],
        "recovery/RECOVERY.yaml": ["restore_rehearsal_required_for_operational: true"],
    }.items():
        try:
            text = (path / rel).read_text(encoding="utf-8")
            missing = [needle for needle in needles if needle not in text]
            if missing:
                raise ValueError(f"missing {missing}")
            result.passed(f"invariant:{rel}")
        except Exception as exc:
            result.failed(f"invariant:{rel}", str(exc), "Restore the canonical OS invariant.")

    if result.os_id == "devops-os":
        _doctor_devops_semantics(path, result)

    return result
