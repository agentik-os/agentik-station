"""Hermes tool adapter for the Zone-local ScrapeGraphAI worker.

The worker is deliberately a subprocess in its own Python environment. Hermes
owns the tool contract and policy; ScrapeGraphAI never becomes a gateway or a
credential store.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.registry import tool_error, tool_result


SCRAPEGRAPH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "minLength": 1, "maxLength": 2000},
        "source": {"type": "string", "minLength": 8, "maxLength": 4096},
        "model": {"type": "string", "pattern": "^[a-z0-9_-]+/[a-z0-9._:-]+$", "maxLength": 160},
    },
    "required": ["prompt", "source"],
    "additionalProperties": False,
}

_MODEL = re.compile(r"^[a-z0-9_-]+/[a-z0-9._:-]+$")


def _safe_source(source: Any) -> str:
    if not isinstance(source, str) or len(source) > 4096:
        raise ValueError("source must be a bounded URL")
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source must be an HTTP(S) URL without embedded credentials")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("non-standard URL ports are not allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("local hostnames are not allowed")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise ValueError("source hostname could not be resolved safely") from exc
    if any(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast for address in addresses):
        raise ValueError("private or reserved source addresses are not allowed")
    return source


def _worker() -> Path:
    configured = os.environ.get("STATION_SCRAPEGRAPHAI_PYTHON", "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path.home() / ".local/share/agentik-station/venvs/scrapegraphai-py3.13/bin/python"
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError("ScrapeGraphAI worker is not installed; run station deps install --component scrapegraphai")
    return path


def handle_scrapegraph(args: dict[str, Any], **_: Any) -> str:
    try:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
            return tool_error("prompt must contain 1-2000 characters")
        source = _safe_source(args.get("source"))
        model = args.get("model") or os.environ.get("SCRAPEGRAPHAI_MODEL", "openai/gpt-4o-mini")
        if not isinstance(model, str) or not _MODEL.fullmatch(model):
            return tool_error("model must use provider/name syntax")
        runner = Path(__file__).with_name("scrapegraph_runner.py")
        result = subprocess.run(
            [_worker(), str(runner)],
            input=json.dumps({"prompt": prompt.strip(), "source": source, "model": model}),
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode != 0:
            return tool_error((result.stderr or result.stdout or "ScrapeGraphAI worker failed").strip()[-4000:])
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict) or payload.get("success") is not True:
            return tool_error("ScrapeGraphAI returned an invalid result")
        return tool_result({"success": True, "source": source, "model": model, "data": payload.get("data")})
    except subprocess.TimeoutExpired:
        return tool_error("ScrapeGraphAI timed out after 180 seconds")
    except Exception as exc:
        return tool_error(f"ScrapeGraphAI request blocked safely: {exc}")

