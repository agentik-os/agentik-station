"""Allowlisted Operator diagnostics for the Agentik OS command layer."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


ENV_PORTS = {"operator": 8460, "agentik": 8461, "mission": 8462, "private": 8463}
COMMANDS = ("machine", "system", "service", "gateway", "docker", "security", "tailscale", "backup", "hermes")


def _run(argv: list[str], timeout: int = 12) -> tuple[int, str]:
    """Run a fixed argv command without a shell and return bounded output."""
    try:
        result = subprocess.run(
            argv, check=False, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    output = (result.stdout or result.stderr or "").strip()
    return result.returncode, output[:12000]


def _api_health(port: int) -> str:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/state")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return f"healthy (HTTP {response.status})"
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return f"healthy (HTTP {exc.code}, protected)"
        return f"unhealthy (HTTP {exc.code})"
    except OSError as exc:
        return f"unreachable ({exc.__class__.__name__})"


class OperatorCommandService:
    descriptions = {
        "machine": "Inspect AGK Core machine identity and health.",
        "system": "Inspect system health, resources and operating system information.",
        "service": "Inspect allowlisted Agentik OS services.",
        "gateway": "Inspect Hermes gateways and control API health.",
        "docker": "Inspect Docker runtime and containers.",
        "security": "Inspect listening ports and security posture without exposing secrets.",
        "tailscale": "Inspect Tailscale connectivity and devices.",
        "backup": "Inspect Agentik OS backup status and snapshots.",
        "hermes": "Inspect Hermes release, deployment and rollback status.",
    }

    def dispatch(self, command: str, argv: list[str]) -> str:
        action = argv[0].lower() if argv else "status"
        if command == "machine":
            return self._machine(action)
        if command == "system":
            return self._system(action)
        if command == "gateway":
            return self._gateway(action, argv[1:])
        if command == "hermes":
            return self._hermes(action)
        if command == "docker":
            return self._docker(action, argv[1:])
        if command == "tailscale":
            return self._tailscale(action)
        if command == "security":
            return self._security(action)
        if command == "backup":
            return self._backup(action)
        if command == "service":
            return self._service(action, argv[1:])
        return f"Unknown Operator command: {command}"

    @staticmethod
    def _mutation_guard(command: str) -> str:
        return (
            f"Approval required for `{command}`. Operator mutations must pass "
            "the typed approval service; arbitrary sudo execution is disabled."
        )

    def _machine(self, action: str) -> str:
        if action not in {"status", "info", "health", "list", "inspect"}:
            return self._mutation_guard(f"/machine {action}")
        return "\n".join((
            "MACHINE · AGK Core",
            f"Hostname: {platform.node()}",
            f"OS: {platform.system()} {platform.release()}",
            f"Architecture: {platform.machine()}",
            f"Python: {platform.python_version()}",
        ))

    def _system(self, action: str) -> str:
        if action not in {"status", "health", "doctor", "info", "resources"}:
            return self._mutation_guard(f"/system {action}")
        load = os.getloadavg()
        disk = shutil.disk_usage("/")
        mem_total = mem_available = 0
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) * 1024
        return "\n".join((
            "SYSTEM HEALTH",
            f"Load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}",
            f"Memory: {(mem_total-mem_available)/2**30:.1f} / {mem_total/2**30:.1f} GiB",
            f"Disk: {(disk.total-disk.free)/2**30:.1f} / {disk.total/2**30:.1f} GiB",
        ))

    def _gateway(self, action: str, rest: list[str]) -> str:
        if action in {"restart", "start", "stop"}:
            return self._mutation_guard(f"/gateway {action} {' '.join(rest)}".strip())
        if action not in {"status", "list", "health", "doctor", "logs"}:
            return "Usage: /gateway list|status [environment]|health|doctor"
        targets = rest[:1] if rest and rest[0] in ENV_PORTS else list(ENV_PORTS)
        lines = ["HERMES GATEWAYS"]
        lines.extend(f"{'●' if 'healthy' in _api_health(ENV_PORTS[name]) else '○'} {name}: {_api_health(ENV_PORTS[name])}" for name in targets)
        return "\n".join(lines)

    def _hermes(self, action: str) -> str:
        if action in {"deploy", "rollback", "update"}:
            return self._mutation_guard(f"/hermes {action}")
        if action in {"status", "version", "releases", "doctor", "check-update"}:
            code, output = _run(["/usr/local/bin/agentik-hermes-status"])
            return output if output else f"Hermes status unavailable (exit {code})."
        return "Usage: /hermes version|status|check-update|releases|doctor|deploy|rollback"

    def _docker(self, action: str, rest: list[str]) -> str:
        if action in {"restart", "prune", "stop", "start"}:
            return self._mutation_guard(f"/docker {action} {' '.join(rest)}".strip())
        argv = ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}"]
        code, output = _run(argv)
        return output or f"Docker unavailable or not permitted (exit {code})."

    def _tailscale(self, action: str) -> str:
        if action not in {"status", "devices", "ip", "doctor"}:
            return "Usage: /tailscale status|devices|ip|doctor"
        code, output = _run(["tailscale", "status"] if action != "ip" else ["tailscale", "ip"])
        return output or f"Tailscale unavailable (exit {code})."

    def _security(self, action: str) -> str:
        if action not in {"status", "audit", "scan", "permissions", "ports", "firewall", "ssh", "tailscale", "fail2ban", "secrets"}:
            return "Usage: /security status|audit|ports|firewall|ssh|tailscale|fail2ban|secrets"
        if action == "ports":
            code, output = _run(["ss", "-lntup"])
            return output or f"Port inspection unavailable (exit {code})."
        return "Security inspection is read-only. No secret values are ever returned. Use `/system doctor` and `/security ports` for live diagnostics."

    def _backup(self, action: str) -> str:
        if action in {"now", "restore"}:
            return self._mutation_guard(f"/backup {action}")
        root = Path("/var/agentik/backups")
        try:
            snapshots = sorted((p for p in root.iterdir()), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        except OSError as exc:
            return f"Backup inventory unavailable: {exc}"
        lines = ["BACKUPS", f"Root: {root}", f"Entries: {len(snapshots)}"]
        lines.extend(f"• {p.name}" for p in snapshots)
        return "\n".join(lines)

    def _service(self, action: str, rest: list[str]) -> str:
        if action in {"restart", "start", "stop"}:
            return self._mutation_guard(f"/service {action} {' '.join(rest)}".strip())
        return self._gateway("status", rest)
