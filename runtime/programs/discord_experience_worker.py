#!/usr/bin/env python3
"""Host-owned Discord Mission Progress transport.

This adapter is intentionally outside the Hermes agent tool surface. Hermes writes
Zone-local mission display state; the Station host adapter resolves an existing
root/operator-approved binding and creates/edits exactly one Discord message.

No model chooses a bot token, channel, guild, or credential path.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentik_station.providers.discord import DiscordTransport, verify_binding

PLUGIN = ROOT / "runtime" / "hermes-station" / "hermes" / "plugins" / "station-discord-experience"
_RENDERER = PLUGIN / "renderer.py"
_spec = importlib.util.spec_from_file_location("station_discord_renderer", _RENDERER)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load canonical Discord renderer: {_RENDERER}")
_renderer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_renderer)
components_v2 = _renderer.components_v2

DEFAULT_BINDINGS = Path("/var/lib/station/discord/mission-message-bindings.json")


def pending_states(db: Path):
    if db.is_symlink() or not db.is_file():
        return []
    con = sqlite3.connect(db)
    try:
        rows = con.execute("select mission_id,payload,updated from mission_state order by updated").fetchall()
        return [(m, json.loads(p), u) for m, p, u in rows]
    finally:
        con.close()


def load_bindings(path: Path) -> dict:
    if path.is_symlink():
        raise RuntimeError(f"Bindings path may not be a symlink: {path}")
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Discord bindings root must be an object")
    return payload


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlink bindings path: {path}")
    fd, name = tempfile.mkstemp(prefix=".bindings-", suffix=".json", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Zone-local discord-experience.db")
    ap.add_argument("--bindings", default=str(DEFAULT_BINDINGS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = Path(args.db)
    bindings_path = Path(args.bindings)
    states = pending_states(db)
    bindings = load_bindings(bindings_path)
    results = []
    changed = False

    for mission_id, state, updated in states:
        raw = bindings.get(mission_id)
        if not isinstance(raw, dict):
            results.append({"mission_id": mission_id, "state": "UNBOUND"})
            continue
        binding = verify_binding(raw)
        payload = components_v2(state)
        if args.dry_run:
            results.append({"mission_id": mission_id, "state": "PLAN_READY", "payload": payload})
            continue
        transport = DiscordTransport(Path(binding["token_file"]))
        message_id = str(binding.get("message_id") or "")
        if message_id:
            response = transport.edit_message(str(binding["channel_id"]), message_id, payload)
            state_label = "EDITED"
        else:
            response = transport.create_message(str(binding["channel_id"]), payload)
            returned_id = str(response.get("id") or "")
            if not returned_id.isdigit():
                raise RuntimeError(f"Discord create did not return a message id for mission {mission_id}")
            raw["message_id"] = returned_id
            raw["last_projected_update"] = updated
            bindings[mission_id] = raw
            changed = True
            state_label = "CREATED"
        results.append({"mission_id": mission_id, "state": state_label, "message_id": response.get("id")})

    if changed:
        atomic_write(bindings_path, bindings)
    print(json.dumps({"schema_version": 1, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
