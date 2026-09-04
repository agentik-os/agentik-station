#!/usr/bin/env python3
"""Maintain a redacted, profile-local cache of Composio connections."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("HOME", ""))


def auth_path() -> Path:
    return home() / ".composio/user_data.json"


def cache_path() -> Path:
    return home() / ".agentik/composio-connections.json"


def authenticated() -> bool:
    try:
        key = json.loads(auth_path().read_text(encoding="utf-8")).get("api_key")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(key, str) and bool(key.strip())


def sanitize(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, dict):
        raise ValueError("Composio connections response must be an object")
    toolkits = []
    for name, connections in sorted(raw.items()):
        if not isinstance(name, str) or not isinstance(connections, list):
            continue
        statuses = sorted({
            str(connection.get("status") or "UNKNOWN").upper()
            for connection in connections
            if isinstance(connection, dict)
        })
        if "ACTIVE" in statuses:
            status = "active"
        elif statuses:
            status = ",".join(value.lower() for value in statuses)
        else:
            status = "unknown"
        toolkits.append({
            "name": name,
            "status": status,
            "connections": len([item for item in connections if isinstance(item, dict)]),
        })
    return toolkits


def write_cache(toolkits: list[dict[str, object]], *, is_authenticated: bool) -> dict[str, object]:
    document = {
        "schema_version": 1,
        "generated_at": int(time.time()),
        "authenticated": is_authenticated,
        "toolkits": toolkits,
    }
    path = cache_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    return document


def refresh() -> dict[str, object]:
    if not authenticated():
        return write_cache([], is_authenticated=False)
    try:
        result = subprocess.run(
            ["composio", "connections", "list"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Composio connections list timed out after 20 seconds") from error
    except OSError as error:
        raise RuntimeError("Composio CLI is unavailable in this profile") from error
    if result.returncode:
        # The CLI may include request details in stderr. Keep the AGK surface
        # useful without ever copying credentials or provider payloads into it.
        raise RuntimeError(
            f"Composio connections list failed with exit code {result.returncode}"
        )
    try:
        connections = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError("Composio returned invalid connection JSON") from error
    return write_cache(sanitize(connections), is_authenticated=True)


def read_cache() -> dict[str, object]:
    try:
        document = json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": 1, "authenticated": False, "toolkits": []}
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return {"schema_version": 1, "authenticated": False, "toolkits": []}
    return document


def print_human(document: dict[str, object]) -> None:
    state = "CONNECTED" if document.get("authenticated") else "SETUP REQUIRED"
    toolkits = document.get("toolkits") if isinstance(document.get("toolkits"), list) else []
    identity = os.environ.get("USER") or str(os.getuid())
    print(f"COMPOSIO · {identity} · {state} · {len(toolkits)} toolkits")
    for item in toolkits:
        if isinstance(item, dict):
            print(
                f"{str(item.get('status') or 'unknown'):<10} "
                f"{item.get('name')} · {item.get('connections', 0)} connection(s)"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("refresh", "show"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        document = refresh() if args.action == "refresh" else read_cache()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        print_human(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
