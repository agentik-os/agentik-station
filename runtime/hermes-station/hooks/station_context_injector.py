#!/usr/bin/env python3
"""Hermes shell hook for pre_llm_call: inject the Station context envelope.

Reads Hermes hook JSON from stdin and STATION_CONTEXT_FILE from the environment.
Outputs {"context": ...} according to Hermes shell-hook protocol.
"""
import json, os, sys
from pathlib import Path

MAX = 3800

def main():
    try:
        json.load(sys.stdin)  # validate payload; event fields are not needed here
        path = os.environ.get("STATION_CONTEXT_FILE", "")
        if not path:
            print(json.dumps({"context": "STATION POLICY: context envelope missing. Do not perform sensitive actions until context is resolved."}))
            return 0
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fields = ["station_id","organization_id","trust_zone","project_id","os_id","profile_id","environment","capability_set","credential_namespace","memory_namespace","allowed_roots"]
        compact = {k:data.get(k) for k in fields if k in data}
        text = (
            "STATION CONTEXT (authoritative desired-state envelope):\n"
            + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
            + "\nINVARIANTS: never guess a different trust zone/organization/project; secrets are references only; "
              "cross-zone access requires explicit capability; durable work uses Mission/Kanban; "
              "code/deploy work follows the Engineering Constitution; unresolved security context blocks execution."
        )
        print(json.dumps({"context": text[:MAX]}))
        return 0
    except Exception as e:
        print(json.dumps({"context": f"STATION POLICY ERROR: {type(e).__name__}. Treat security context as unresolved and do not perform sensitive actions."}))
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
