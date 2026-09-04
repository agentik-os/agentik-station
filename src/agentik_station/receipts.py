from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .filesystem import SafeFS
from .models import InstallSpec


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Receipt:
    spec: InstallSpec
    status: str = "STARTED"
    state: str = "RECONCILING"
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, str] | None = None
    next_actions: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def step(self, name: str, status: str, detail: str | None = None) -> None:
        entry: dict[str, Any] = {"name": name, "status": status, "at": utc_now()}
        if detail:
            entry["detail"] = detail
        self.steps.append(entry)

    def complete(self, state: str, next_actions: list[str]) -> None:
        self.status = "COMPLETED"
        self.state = state
        self.finished_at = utc_now()
        self.next_actions = next_actions

    def fail(self, exc: BaseException, next_action: str) -> None:
        self.status = "FAILED"
        self.state = "DEGRADED"
        self.finished_at = utc_now()
        self.error = {"type": type(exc).__name__, "message": str(exc)}
        self.next_actions = [next_action]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "operation_id": self.spec.operation_id,
            "release_version": self.spec.release_version,
            "spec": self.spec.to_dict(),
            "status": self.status,
            "state": self.state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "steps": self.steps,
            "error": self.error,
            "next_actions": self.next_actions,
            "evidence": self.evidence,
        }

    def persist(self, fs: SafeFS, receipts_root: Path) -> Path:
        path = receipts_root / f"{self.spec.operation_id}.json"
        fs.write_text(path, json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", 0o640)
        return path
