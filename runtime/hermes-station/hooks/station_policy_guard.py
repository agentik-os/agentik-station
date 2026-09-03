#!/usr/bin/env python3
"""Defense-in-depth Hermes pre_tool_call shell hook.

This is not a replacement for Unix/container/Node isolation. It rejects obvious
cross-root file operations and requires context for high-risk tools.
"""
import json, os, sys, re
from pathlib import Path

FILE_KEYS = {"path","file_path","filepath","target","source","cwd","directory","workdir"}
SENSITIVE_TOOLS = {"terminal","write_file","patch","edit_file","execute_code"}

def norm(p):
    try: return str(Path(p).expanduser().resolve())
    except Exception: return str(p)

def inside(path, roots):
    p = norm(path)
    return any(p == r or p.startswith(r.rstrip("/") + "/") for r in roots)

def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name") or ""
    args = payload.get("tool_input") or {}
    cf = os.environ.get("STATION_CONTEXT_FILE", "")
    if not cf:
        if tool in SENSITIVE_TOOLS:
            print(json.dumps({"action":"block","message":"Station context envelope missing; sensitive tool blocked."}))
        return 0
    try:
        ctx = json.loads(Path(cf).read_text(encoding="utf-8"))
    except Exception:
        if tool in SENSITIVE_TOOLS:
            print(json.dumps({"action":"block","message":"Station context envelope unreadable; sensitive tool blocked."}))
        return 0
    roots = [norm(x) for x in ctx.get("allowed_roots", [])]
    deny = [norm(x) for x in ctx.get("deny_roots", [])]
    if tool in SENSITIVE_TOOLS and not roots:
        print(json.dumps({"action":"block","message":"No allowed filesystem roots declared in Station context."}))
        return 0

    # Inspect explicit path-like arguments.
    for k,v in args.items():
        if k in FILE_KEYS and isinstance(v,str) and v.startswith("/"):
            pv = norm(v)
            if any(pv == d or pv.startswith(d.rstrip("/")+"/") for d in deny):
                print(json.dumps({"action":"block","message":f"Station policy blocks denied root for {k}."}))
                return 0
            if roots and not inside(pv, roots):
                print(json.dumps({"action":"block","message":f"Station policy blocks path outside allowed roots: {pv}"}))
                return 0

    # Terminal commands can hide paths. Block explicit denied absolute roots and
    # require approval for sudo/system mutation from non-system zones.
    if tool == "terminal":
        cmd = str(args.get("command", ""))
        for d in deny:
            if d and d in cmd:
                print(json.dumps({"action":"block","message":"Station policy blocks terminal command referencing a denied trust-zone root."}))
                return 0
        zone = ctx.get("trust_zone")
        if zone != "station-system" and re.search(r"(^|\s)(sudo|systemctl|useradd|usermod|mount|umount)\b", cmd):
            print(json.dumps({"action":"approve","message":"Host/system mutation requested outside station-system trust zone.","rule_key":"station:host-mutation"}))
            return 0
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
