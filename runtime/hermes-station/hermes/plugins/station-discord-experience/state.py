from __future__ import annotations

import json
import os
import sqlite3
import stat
import time
from pathlib import Path
from typing import Any


def _assert_no_symlink_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeError(f"Symlink is forbidden in Station mission-state path: {current}")


def database_path() -> Path:
    root_raw = os.environ.get("STATION_ZONE_STATE_ROOT", "").strip()
    if not root_raw:
        raise RuntimeError("STATION_ZONE_STATE_ROOT is required; shared global mission state is forbidden")
    root = Path(os.path.abspath(root_raw))
    candidate_raw = os.environ.get("STATION_DISCORD_EXPERIENCE_DB", "").strip()
    candidate = Path(os.path.abspath(candidate_raw)) if candidate_raw else root / "mission-state" / "discord-experience.db"
    if os.path.commonpath([str(candidate), str(root)]) != str(root):
        raise RuntimeError("Discord Experience DB must remain inside the current Zone state root")
    _assert_no_symlink_chain(candidate.parent)
    return candidate


def _db() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_chain(path.parent)
    con = sqlite3.connect(path)
    con.execute("pragma foreign_keys=on")
    con.execute("pragma journal_mode=wal")
    con.execute(
        "create table if not exists mission_state "
        "(mission_id text primary key, payload text not null, updated real not null)"
    )
    con.execute(
        "create table if not exists events "
        "(id integer primary key autoincrement, mission_id text not null, kind text not null, "
        "payload text not null, created real not null)"
    )
    try:
        os.chmod(path, 0o600, follow_symlinks=False)
    except FileNotFoundError:
        pass
    return con


def load(mission_id: str) -> dict[str, Any] | None:
    con = _db()
    try:
        row = con.execute("select payload from mission_state where mission_id=?", (mission_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        con.close()


def save(mission_id: str, payload: dict[str, Any], kind: str = "state") -> dict[str, Any]:
    now = time.time()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    con = _db()
    try:
        con.execute(
            "insert into mission_state(mission_id,payload,updated) values(?,?,?) "
            "on conflict(mission_id) do update set payload=excluded.payload,updated=excluded.updated",
            (mission_id, raw, now),
        )
        con.execute(
            "insert into events(mission_id,kind,payload,created) values(?,?,?,?)",
            (mission_id, kind, raw, now),
        )
        con.commit()
    finally:
        con.close()
    return payload
