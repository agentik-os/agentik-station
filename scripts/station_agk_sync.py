#!/usr/bin/env python3
"""Project protected Station metadata to the operator without sharing secrets."""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentik_station.errors import StationError
from agentik_station.filesystem import SafeFS
from agentik_station.os_lifecycle import read_runtime_json

TOOLS = Path("/etc/station/bootstrap-tools.json")
HOST = Path("/var/lib/station/observed/host.json")
DOCTOR = Path("/var/lib/station/doctor/latest.json")
OPERATOR = "agk-station"
REPOSITORY = "/home/agk-station/repos/agentik-station"
MAX_PROJECTION = 65536
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
TOOL_FIELDS = ("hermes", "codex", "agk_tui", "claude")


class SyncError(ValueError):
    pass


def _text(value, *, empty=False, limit=256):
    if (not isinstance(value, str) or len(value) > limit or (not empty and not value)
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise SyncError("Invalid metadata text field")
    return value


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise SyncError("Invalid metadata identity")
    return value


def _read_metadata(path: Path) -> dict:
    try:
        return read_runtime_json(path, uid=0, immutable=True, limit=1024 * 1024)
    except FileNotFoundError:
        raise SyncError(f"Required Station metadata is missing: {path}") from None
    except PermissionError:
        raise SyncError(f"Required Station metadata is unreadable: {path}") from None
    except (OSError, StationError):
        raise SyncError(f"Required Station metadata is invalid: {path}") from None


def export_projection() -> dict:
    """Read fixed root-owned sources; project version fields and receipt summaries."""
    tools, host, doctor = (_read_metadata(path) for path in (TOOLS, HOST, DOCTOR))
    if tools.get("station_user") != OPERATOR or tools.get("repository") != REPOSITORY:
        raise SyncError("Bootstrap metadata has an unexpected operator or repository")
    if tools.get("mode") not in {"full", "team"}:
        raise SyncError("Bootstrap metadata has an invalid installation mode")
    if (type(host.get("schema_version")) is not int or host["schema_version"] != 1
            or type(doctor.get("schema_version")) is not int or doctor["schema_version"] != 1):
        raise SyncError("Unsupported Station metadata schema")
    if host.get("role") not in {"core", "team"} or host.get("state") not in {
            "NOT_INSTALLED", "RECONCILING", "READY_FOR_SETUP", "DEGRADED", "OPERATIONAL"}:
        raise SyncError("Invalid observed Host state")
    zones = host.get("zones")
    if not isinstance(zones, list) or len(zones) > 1000:
        raise SyncError("Invalid observed Zone inventory")
    if type(doctor.get("ok")) is not bool or doctor.get("scope") not in {"station", "station-full"}:
        raise SyncError("Invalid Station Doctor result")
    counts = {}
    for field in ("checks", "issues", "warnings"):
        rows = doctor.get(field)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise SyncError("Invalid Station Doctor entries")
        counts[field] = len(rows)
    if doctor["ok"] != (counts["issues"] == 0):
        raise SyncError("Inconsistent Station Doctor result")
    projection = {
        "schema_version": 1,
        "station_user": OPERATOR,
        "mode": tools["mode"],
        "repository": REPOSITORY,
        "tools": {field: _text(tools.get(field, ""), empty=True) for field in TOOL_FIELDS},
        "receipts": {
            str(HOST): {
                "schema_version": 1, "host_id": _identifier(host.get("host_id")),
                "role": host["role"], "state": host["state"],
                "release_version": _text(host.get("release_version")),
                "zones": [_identifier(zone) for zone in zones],
            },
            str(DOCTOR): {
                "schema_version": 1, "scope": doctor["scope"], "ok": doctor["ok"],
                "checked_at": _text(doctor.get("checked_at")), **counts,
            },
        },
    }
    return validate_projection(projection)


def validate_projection(value) -> dict:
    """Accept only the deliberately small transport contract, never arbitrary JSON."""
    if (not isinstance(value, dict) or set(value) != {
            "schema_version", "station_user", "mode", "repository", "tools", "receipts"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["station_user"] != OPERATOR
            or value["repository"] != REPOSITORY or value["mode"] not in {"full", "team"}):
        raise SyncError("Invalid Station projection envelope")
    tools, receipts = value["tools"], value["receipts"]
    if not isinstance(tools, dict) or set(tools) != set(TOOL_FIELDS):
        raise SyncError("Invalid Station tool projection")
    for item in tools.values():
        _text(item, empty=True)
    if not isinstance(receipts, dict) or set(receipts) != {str(HOST), str(DOCTOR)}:
        raise SyncError("Invalid Station receipt projection")
    host, doctor = receipts[str(HOST)], receipts[str(DOCTOR)]
    if (not isinstance(host, dict) or set(host) != {
            "schema_version", "host_id", "role", "state", "release_version", "zones"}
            or type(host["schema_version"]) is not int or host["schema_version"] != 1
            or host["role"] != ("core" if value["mode"] == "full" else "team")
            or host["state"] not in {"NOT_INSTALLED", "RECONCILING", "READY_FOR_SETUP", "DEGRADED", "OPERATIONAL"}):
        raise SyncError("Invalid Host projection")
    _identifier(host["host_id"])
    _text(host["release_version"])
    if not isinstance(host["zones"], list) or len(host["zones"]) > 1000:
        raise SyncError("Invalid Zone projection")
    for zone in host["zones"]:
        _identifier(zone)
    if (not isinstance(doctor, dict) or set(doctor) != {
            "schema_version", "scope", "ok", "checked_at", "checks", "issues", "warnings"}
            or type(doctor["schema_version"]) is not int or doctor["schema_version"] != 1
            or type(doctor["ok"]) is not bool
            or doctor["scope"] not in {"station", "station-full"}):
        raise SyncError("Invalid Doctor projection")
    _text(doctor["checked_at"])
    for field in ("checks", "issues", "warnings"):
        if type(doctor[field]) is not int or not 0 <= doctor[field] <= 100000:
            raise SyncError("Invalid Doctor count")
    if doctor["ok"] != (doctor["issues"] == 0):
        raise SyncError("Inconsistent Doctor projection")
    return value


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SyncError("Duplicate projection field")
        value[key] = item
    return value


def write_snapshot(projection: dict) -> Path:
    if os.geteuid() == 0:
        raise SyncError("Station sync writes must run as the unprivileged operator")
    projection = validate_projection(projection)
    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir)
    if account.pw_name != projection["station_user"] or os.environ.get("HOME") != str(home):
        raise SyncError("Station sync writer identity or HOME does not match the operator")
    if home.is_symlink() or not home.is_dir() or home.stat().st_uid != os.getuid():
        raise SyncError("Station operator HOME is not an owned directory")
    snapshot = {
        **projection,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agk_tui_pin": (ROOT / "components/agk-tui/PIN").read_text().strip(),
        "versions_lock": (ROOT / "config/versions.lock").read_text().strip(),
        "paths": {"hermes_home": str(home / ".hermes"), "agentik": str(home / ".agentik"),
                  "local_bin": str(home / ".local/bin")},
        "commands": {"open_tui": ["agk", "station tui"], "sessions": "agk sessions", "reconcile": "agk reconcile"},
        "note": "Station metadata projection only; provider credentials and live account acceptance are not included.",
    }
    fs = SafeFS([home])
    agentik = fs.mkdir(home / ".agentik", 0o700)
    out = fs.write_text(agentik / "station-sync.json", json.dumps(snapshot, indent=2, sort_keys=True) + "\n", 0o600)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--export", action="store_true", help="Read and redact protected metadata as root")
    modes.add_argument("--from-stdin", action="store_true", help="Write the root projection as the operator")
    args = parser.parse_args(argv)
    try:
        if args.export:
            if os.geteuid() != 0:
                raise SyncError("Protected Station metadata export requires root")
            print(json.dumps(export_projection(), sort_keys=True))
            return 0
        if os.geteuid() == 0:
            raise SyncError("Station sync writes must run as the unprivileged operator")
        payload = sys.stdin.buffer.read(MAX_PROJECTION + 1)
        if len(payload) > MAX_PROJECTION:
            raise SyncError("Station projection exceeds its size limit")
        projection = json.loads(payload, object_pairs_hook=_unique_pairs)
        out = write_snapshot(projection)
    except SyncError as exc:
        print(f"ERROR: {exc}. No successful sync is claimed.", file=sys.stderr)
        return 1
    except (OSError, StationError, ValueError, TypeError, KeyError, RecursionError):
        print("ERROR: Station metadata sync failed; inspect protected metadata and the selected operator identity. No successful sync is claimed.", file=sys.stderr)
        return 1
    print(f"Wrote {out}")
    agk = shutil.which("agk") or str(out.parent.parent / ".local/bin/agk")
    if Path(agk).is_file():
        try:
            completed = subprocess.run([agk, "reconcile"], check=False, timeout=120,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if completed.returncode:
                print("WARN: AGK reconcile failed; Station metadata was synchronized.", file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired):
            print("WARN: AGK reconcile unavailable; Station metadata was synchronized.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
