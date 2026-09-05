#!/usr/bin/env python3
"""Account-free native dependency probes. No clients, devices or profiles opened."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import sys
import tempfile


def read_pins(repo: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in (repo / "config/versions.lock").read_text().splitlines()
                if re.fullmatch(r"[A-Z0-9_]+=[^\s]+", line))


def command(repo: Path, home: Path, mode: str, pins: dict[str, str]) -> list[str]:
    hermes = Path("/opt/station/tools/hermes/current/venv/bin/python")
    if mode in {"crawl4ai", "scrapegraphai"}:
        runtime = web_runtime(mode, pins)
        worker = repo / "components/agk-tui/hermes/plugins/agentik_os/scrapegraph_runner.py"
        request = json.dumps({"component": mode, "health": True})
        code = ("import io,runpy,sys\n" + f"sys.path.insert(0,{str(worker.parent)!r})\n"
                + f"sys.stdin=io.StringIO({request!r})\nrunpy.run_path({str(worker)!r},run_name='__main__')\n")
        return [str(runtime / "venv/bin/python"), "-I", "-B", "-c", code]
    if mode == "voice":
        return [str(hermes), "-I", "-B", str(repo / "scripts/station_voice_check.py")]
    if mode == "strix":
        runtime = Path("/opt/station/tools/security") / f"strix-{pins['STRIX_VERSION']}-py{pins['AI_PYTHON_VERSION']}"
        return [str(runtime / "venv/bin/strix"), "--version"]
    if mode == "hermes-clients":
        packages = {"honcho-ai": "2.2.0", "hindsight-client": "0.6.1", "mcp": "2.0.0",
                    "httpx2": "2.7.0", "starlette": "1.3.1", "langfuse": pins["LANGFUSE_PYTHON_VERSION"]}
        modules = ["honcho", "hindsight_client", "mcp", "httpx2", "starlette", "langfuse"]
        python = hermes
        extra = "\nassert sys.version_info[:2] == (3, 11)\nfrom langfuse import Langfuse, propagate_attributes\nfrom tools.mcp_tool import _ensure_mcp_sdk\nassert _ensure_mcp_sdk()\n"
    elif mode in {"honcho", "hindsight"}:
        package, module, version = (
            ("honcho-ai", "honcho", pins["HONCHO_PYTHON_VERSION"]) if mode == "honcho" else
            ("hindsight-client", "hindsight_client", pins["HINDSIGHT_PYTHON_VERSION"]))
        packages, modules, extra = {package: version}, [module], ""
        python = home / ".local/share/agentik-station/venvs" / f"{mode}-py{pins['AI_PYTHON_VERSION']}" / "bin/python"
    else:
        raise ValueError("Unknown dependency probe")
    code = ("import sys, importlib, importlib.metadata as m\n"
            f"expected={packages!r}\n"
            "assert all(m.version(k) == v for k,v in expected.items())\n"
            f"for name in {modules!r}: importlib.import_module(name)\n" + extra + "\nprint('SOFTWARE_IMPORT_OK')\n")
    return [str(python), "-I", "-B", "-c", code]


def web_runtime(mode: str, pins: dict[str, str]) -> Path:
    version = pins["CRAWL4AI_PYTHON_VERSION" if mode == "crawl4ai" else "SCRAPEGRAPHAI_VERSION"]
    return Path("/opt/station/tools/web") / f"{mode}-{version}-py{pins['AI_PYTHON_VERSION']}-pw{pins['PLAYWRIGHT_VERSION']}"


def main() -> int:
    if len(sys.argv) != 3 or sys.platform != "linux" or os.geteuid() == 0:
        print("Dependency checks require a non-root Linux operator and explicit repository/mode", file=sys.stderr)
        return 2
    try:
        repo = Path(sys.argv[1]).resolve(strict=True)
        mode = sys.argv[2]
        home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
        pins = read_pins(repo)
        argv = command(repo, home, mode, pins)
        sys.path.insert(0, str(repo / "src"))
        from agentik_station.native_process import run_bounded_native
        with tempfile.TemporaryDirectory(prefix="station-dependency-probe-", dir="/tmp") as temporary:
            private = Path(temporary)
            for child in ("hermes", "managed", "config", "cache", "data", "tmp"):
                (private / child).mkdir(mode=0o700)
            environment = {"HOME": temporary, "HERMES_HOME": str(private / "hermes"),
                           "HERMES_MANAGED_DIR": str(private / "managed"),
                           "XDG_CONFIG_HOME": str(private / "config"), "XDG_CACHE_HOME": str(private / "cache"),
                           "XDG_DATA_HOME": str(private / "data"), "TMPDIR": str(private / "tmp"),
                           "PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
                           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "DO_NOT_TRACK": "1"}
            if mode in {"crawl4ai", "scrapegraphai"}:
                runtime = web_runtime(mode, pins)
                environment.update(PLAYWRIGHT_BROWSERS_PATH=str(runtime / "browsers"),
                                   TIKTOKEN_CACHE_DIR=str(runtime / "tokenizers"),
                                   SCRAPEGRAPHAI_TELEMETRY_ENABLED="false")
            result = run_bounded_native(["/usr/bin/env", "-i", f"--chdir={temporary}",
                                         *(f"{key}={value}" for key, value in environment.items()), *argv],
                                        timeout=180, capture=True)
            passed = result.returncode == 0
            if mode == "strix":
                passed = passed and bool(re.search(r"(?<![0-9.])" + re.escape(pins["STRIX_VERSION"]) + r"(?![0-9.])",
                                                  result.stdout.decode("utf-8")))
            if mode in {"crawl4ai", "scrapegraphai"}:
                observed = json.loads(result.stdout)
                expected_version = pins["CRAWL4AI_PYTHON_VERSION" if mode == "crawl4ai" else "SCRAPEGRAPHAI_VERSION"]
                passed = (passed and observed.get("success") is True and observed.get("component") == mode
                          and observed.get("version") == expected_version and observed.get("browser") == "launch-passed")
        print(json.dumps({"component": mode, "software_verified": passed, "account_checked": False}))
        return 0 if passed else 1
    except Exception:
        # No native exception/output can reveal environment values or profile paths.
        print("Dependency probe failed; native diagnostics redacted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
