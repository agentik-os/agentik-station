from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from .filesystem import SafeFS
from .paths import LayoutPaths


def _execute(binary: str, *args: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return {
            "argv": [*args],
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": [*args],
            "returncode": 124,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": "Hermes update command timed out",
        }


def run_check(paths: LayoutPaths, *, record: bool = False) -> dict[str, Any]:
    binary = shutil.which("hermes")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "binary": binary,
        "claim": "OBSERVED_UPDATE_PLAN_NOT_APPLIED",
        "applied": False,
        "promoted": False,
    }
    if not binary:
        payload.update(
            {
                "status": "NOT_INSTALLED",
                "commands": [],
                "next_repair_action": (
                    "Install and configure Hermes through the approved setup gate before enabling the watcher."
                ),
            }
        )
    else:
        check = _execute(binary, "update", "--check")
        commands = [check]
        if check["returncode"] == 0:
            plan = _execute(binary, "update", "--plan")
            commands.append(plan)
            status = "PLAN_READY" if plan["returncode"] == 0 else "PLAN_FAILED"
        else:
            status = "CHECK_FAILED"
        payload.update({"status": status, "commands": commands})
        if status == "PLAN_READY":
            payload["next_repair_action"] = (
                "Review the Hermes plan in LAB, run Station compatibility/regression gates, then promote through "
                "candidate and stable rings. This watcher never applies an update."
            )
        else:
            payload["next_repair_action"] = (
                "Inspect the Hermes command output; do not promote or update any Station release ring."
            )

    if record:
        fs = SafeFS(paths.allowed_roots)
        root = paths.varlib / "system" / "hermes-updates"
        fs.mkdir(root, 0o700)
        name = datetime.now(timezone.utc).strftime("check-%Y%m%d-%H%M%S.json")
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        fs.write_text(root / name, serialized, 0o640)
        fs.write_text(root / "latest.json", serialized, 0o640)
        payload["receipt"] = str(root / name)
    return payload
