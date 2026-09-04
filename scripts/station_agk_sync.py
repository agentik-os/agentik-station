#!/usr/bin/env python3
"""Write a redacted Station↔AGK sync snapshot and best-effort `agk reconcile`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except Exception:
        return ""


def main() -> int:
    home = Path(os.environ.get("HOME") or Path.home())
    station_user = os.environ.get("USER") or home.name
    agentik = home / ".agentik"
    agentik.mkdir(mode=0o700, parents=True, exist_ok=True)

    tools = _read_json(Path("/etc/station/bootstrap-tools.json"))
    pin = _read_text(Path(__file__).resolve().parents[1] / "components" / "agk-tui" / "PIN")
    versions_lock = _read_text(Path(__file__).resolve().parents[1] / "config" / "versions.lock")

    # Discover lightweight Station receipts without inventing secrets.
    receipts = {}
    for candidate in (
        Path("/etc/station/status.json"),
        Path("/var/lib/station/status.json"),
        Path("/run/station/status.json"),
        Path("/etc/station/last-doctor.json"),
    ):
        if candidate.is_file():
            receipts[str(candidate)] = _read_json(candidate)

    snapshot = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "station_user": tools.get("station_user") or station_user,
        "mode": tools.get("mode"),
        "repository": tools.get("repository"),
        "tools": {
            "hermes": tools.get("hermes") or "",
            "codex": tools.get("codex") or "",
            "agk_tui": tools.get("agk_tui") or "",
            "claude": tools.get("claude") or "",
        },
        "agk_tui_pin": pin,
        "versions_lock": versions_lock,
        "paths": {
            "hermes_home": str(home / ".hermes"),
            "agentik": str(agentik),
            "local_bin": str(home / ".local" / "bin"),
        },
        "receipts": receipts,
        "commands": {
            "open_tui": ["agk", "station tui"],
            "sessions": "agk sessions",
            "reconcile": "agk reconcile",
        },
        "note": "Live Hermes/Codex/Claude/terminal sessions are owned by AGK-TUI+RMUX; this file is Station sync metadata only.",
    }
    out = agentik / "station-sync.json"
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    os.chmod(out, 0o600)
    print(f"Wrote {out}")

    agk = shutil.which("agk") or str(home / ".local" / "bin" / "agk")
    if Path(agk).exists():
        try:
            subprocess.run([agk, "reconcile"], check=False, timeout=120)
        except Exception as exc:
            print(f"WARN: agk reconcile skipped: {exc}", file=sys.stderr)
    else:
        print("WARN: agk not on PATH; sync file written only", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
