from __future__ import annotations

import json
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

    return result
