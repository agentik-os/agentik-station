from __future__ import annotations

import json
import re
import time
from typing import Any

from . import state

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"success": True, **payload}, ensure_ascii=False, sort_keys=True)


def _error(message: str) -> str:
    return json.dumps({"success": False, "error": message}, ensure_ascii=False, sort_keys=True)


def mission_plan(args: dict[str, Any], **_: Any) -> str:
    mission_id = _require_id(args.get("mission_id"), "mission_id")
    objective = str(args.get("objective", "")).strip()
    if not objective:
        return _error("objective is required")
    nodes = args.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        return _error("at least one plan node is required")
    payload = {
        "mission_id": mission_id,
        "objective": objective,
        "acceptance": args.get("acceptance", []),
        "nodes": nodes,
        "status": "planning",
        "evidence_stage": "prepared",
        "plan_revision": 1,
        "current_node_id": None,
        "problems": [],
        "artifacts": [],
        "created_at": time.time(),
    }
    state.save(mission_id, payload, "plan_created")
    return _ok({"mission_id": mission_id, "plan_revision": 1, "evidence_stage": "prepared"})


def plan_update(args: dict[str, Any], **_: Any) -> str:
    mission_id = _require_id(args.get("mission_id"), "mission_id")
    current = state.load(mission_id)
    if not current:
        return _error("mission plan not found")
    current["nodes"] = args.get("nodes", current.get("nodes", []))
    current["plan_revision"] = int(current.get("plan_revision", 1)) + 1
    current["last_revision_reason"] = str(args.get("reason", "")).strip()
    state.save(mission_id, current, "plan_revised")
    return _ok({"mission_id": mission_id, "plan_revision": current["plan_revision"]})


def progress(args: dict[str, Any], **_: Any) -> str:
    mission_id = _require_id(args.get("mission_id"), "mission_id")
    current = state.load(mission_id)
    if not current:
        return _error("mission plan required before progress")
    event_type = str(args.get("event_type", ""))
    current["status"] = "running"
    current["current_node_id"] = args.get("node_id")
    current["last_summary"] = str(args.get("summary", ""))
    current["last_event_type"] = event_type
    if event_type == "executor_observed":
        current["evidence_stage"] = "observed"
    elif event_type == "executor_reported_done":
        current["evidence_stage"] = "reported"
    elif event_type == "verification_passed":
        current["evidence_stage"] = "verified"
    for node in current.get("nodes", []):
        if args.get("node_id") and node.get("id") == args["node_id"]:
            if event_type in {"node_completed", "verification_passed"}:
                node["status"] = "done"
            elif event_type in {"node_blocked", "verification_failed"}:
                node["status"] = "blocked"
            elif event_type in {"node_started", "verification_started"}:
                node["status"] = "running"
    state.save(mission_id, current, event_type or "progress")
    return _ok(
        {
            "mission_id": mission_id,
            "status": current["status"],
            "evidence_stage": current.get("evidence_stage"),
        }
    )


def close(args: dict[str, Any], **_: Any) -> str:
    mission_id = _require_id(args.get("mission_id"), "mission_id")
    current = state.load(mission_id)
    if not current:
        return _error("mission plan required before close")
    status = str(args.get("status", ""))
    if status not in {"done", "blocked", "failed", "cancelled"}:
        return _error("invalid terminal status")
    current["status"] = status
    current["outcome"] = str(args.get("outcome", ""))
    current["problems"] = args.get("problems", [])
    current["artifacts"] = args.get("artifacts", [])
    current["closed_at"] = time.time()
    if status == "done" and current.get("evidence_stage") not in {"verified", "read_back", "accepted"}:
        current["claim_warning"] = "Executor completion is not independent verification or acceptance."
    state.save(mission_id, current, "mission_" + status)
    return _ok(
        {
            "mission_id": mission_id,
            "status": status,
            "evidence_stage": current.get("evidence_stage"),
        }
    )
