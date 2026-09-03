#!/usr/bin/env python3
"""Station Discord Experience worker scaffold.

Reads durable mission display state and host-owned bindings, renders Components V2 payloads,
and edits the one bound Discord progress message. Network transport is intentionally separated
from Hermes agent tool calls so authorization/destination cannot be model-selected.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, time
from pathlib import Path

DEFAULT_DB=Path('/var/lib/station/discord-experience/state.db')
DEFAULT_BINDINGS=Path('/var/lib/agentik/discord/mission-message-bindings.json')

def load_bindings(path):
    if not path.exists(): return {}
    return json.loads(path.read_text())

def pending_states(db):
    if not db.exists(): return []
    con=sqlite3.connect(db); rows=con.execute('select mission_id,payload,updated from mission_state order by updated').fetchall(); con.close()
    return [(m,json.loads(p),u) for m,p,u in rows]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--once',action='store_true'); ap.add_argument('--db',default=str(DEFAULT_DB)); ap.add_argument('--bindings',default=str(DEFAULT_BINDINGS)); a=ap.parse_args()
    states=pending_states(Path(a.db)); bindings=load_bindings(Path(a.bindings))
    unresolved=[m for m,_,_ in states if m not in bindings]
    print(json.dumps({'missions':len(states),'bound':len(states)-len(unresolved),'unresolved':unresolved},indent=2))
    # Real Discord edit transport is implemented by the Station adapter using the bot token that owns each OS binding.
    return 0
if __name__=='__main__': raise SystemExit(main())
