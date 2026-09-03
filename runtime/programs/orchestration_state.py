#!/usr/bin/env python3
"""Deterministic Station orchestration/evidence state helpers.

This module does not execute agents. It protects the semantic distinction between
prepared intent, observed runtime activity, executor reports, verification, external
readback, and final acceptance.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

STAGES = ("prepared","observed","reported","verified","read_back","accepted")
RANK = {s:i for i,s in enumerate(STAGES)}

@dataclass(frozen=True)
class Evidence:
    stage: str
    evidence_type: str
    observer: str
    source_locator: Optional[str] = None
    verifier: Optional[str] = None

class EvidenceError(ValueError):
    pass

def validate_evidence(e: Evidence, *, executor: Optional[str]=None, independent_required: bool=False) -> None:
    if e.stage not in RANK:
        raise EvidenceError(f"unknown evidence stage: {e.stage}")
    if e.stage in {"observed","verified","read_back","accepted"} and not e.observer:
        raise EvidenceError(f"{e.stage} requires an observer")
    if e.stage == "verified":
        if not e.verifier:
            raise EvidenceError("verified requires verifier")
        if independent_required and executor and e.verifier == executor:
            raise EvidenceError("independent verification cannot be satisfied by executor")

def can_advance(current: str, target: str) -> bool:
    if current not in RANK or target not in RANK:
        return False
    return RANK[target] >= RANK[current]

def advance(current: str, evidence: Evidence, *, executor: Optional[str]=None, independent_required: bool=False) -> str:
    validate_evidence(evidence, executor=executor, independent_required=independent_required)
    if not can_advance(current, evidence.stage):
        raise EvidenceError(f"cannot downgrade evidence {current} -> {evidence.stage}")
    return evidence.stage

def ui_label(work_kind: str, stage: str) -> str:
    noun={"plan":"Plan","code":"Code","test":"Test","ship":"Ship","mission":"Mission","research":"Research","artifact":"Artifact","connector":"Connector"}.get(work_kind,work_kind.title())
    suffix={"prepared":"not run","observed":"running","reported":"reported done","verified":"verified","read_back":"read back","accepted":"accepted"}[stage]
    return f"{noun} • {suffix}"
