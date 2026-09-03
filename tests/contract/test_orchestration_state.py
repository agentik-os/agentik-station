from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("station_orchestration_state", ROOT / "runtime" / "programs" / "orchestration_state.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_ui_labels_preserve_evidence_boundaries() -> None:
    assert MODULE.ui_label("plan", "prepared") == "Plan • not run"
    assert MODULE.ui_label("code", "observed") == "Code • running"
    assert MODULE.ui_label("code", "reported") == "Code • reported done"
    assert MODULE.ui_label("test", "verified") == "Test • verified"


def test_executor_report_never_becomes_verification() -> None:
    evidence = MODULE.Evidence(stage="reported", evidence_type="executor_report", observer="forge")
    assert MODULE.advance("observed", evidence, executor="forge") == "reported"
    assert evidence.stage != "verified"


def test_independent_verifier_required_when_contract_requires_it() -> None:
    evidence = MODULE.Evidence(stage="verified", evidence_type="tests", observer="forge", verifier="forge")
    try:
        MODULE.advance("reported", evidence, executor="forge", independent_required=True)
        raise AssertionError("expected independent verification failure")
    except MODULE.EvidenceError:
        pass


def test_independent_verification_advances_claim() -> None:
    evidence = MODULE.Evidence(stage="verified", evidence_type="tests", observer="sentinel", verifier="sentinel")
    assert MODULE.advance("reported", evidence, executor="forge", independent_required=True) == "verified"
