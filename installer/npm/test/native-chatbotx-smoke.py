"""Native Hermes MCP template acceptance with synthetic tools and no network."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import sys
import tempfile
from types import SimpleNamespace


def main() -> None:
    assert os.geteuid() != 0, "Run native acceptance as the ordinary Workstation owner"
    assert len(sys.argv) == 2, "usage: native-chatbotx-smoke.py <station-root>"
    root = Path(sys.argv[1])
    assert root.is_absolute() and root.resolve() == root
    identity = root.lstat()
    assert stat.S_ISDIR(identity.st_mode) and identity.st_uid == os.getuid() and not identity.st_mode & 0o077
    marker = json.loads((root / ".station-workstation.json").read_text())
    assert marker["root"] == str(root) and marker["uid"] == os.getuid() and marker["mode"] == "workstation"
    assert not (root / ".install.lock").exists(), "Finish installation before native acceptance"
    hermes = root / "tools/hermes"
    assert Path(sys.prefix).resolve() == (hermes / "venv").resolve(), "Use tools/hermes/venv/bin/python"
    template = root / "resources/chatbotx/hermes-mcp.example.yaml"
    template_info = template.lstat()
    assert stat.S_ISREG(template_info.st_mode) and template_info.st_nlink == 1
    assert template_info.st_uid == os.getuid() and not template_info.st_mode & 0o022
    template_bytes = template.read_bytes()
    network_attempts: list[str] = []
    process_attempts: list[str] = []

    def audit(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname",
                     "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg"}:
            network_attempts.append(event)
            raise RuntimeError("Native ChatbotX acceptance forbids network access")
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.exec", "os.fork"}:
            process_attempts.append(event)
            raise RuntimeError("Native ChatbotX acceptance forbids child processes")

    def timed_out(signum, frame):
        raise TimeoutError("Native ChatbotX acceptance exceeded its time limit")

    report = {"root": str(root), "scope": "native disabled MCP template and synthetic tool registration only",
              "checks": [], "operational": False}
    previous_cwd = Path.cwd()
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="native-chatbotx-", dir=root / "cache") as temporary:
        private = Path(temporary)
        for name in ("home", "hermes", "config", "cache", "data", "managed", "tmp"):
            (private / name).mkdir(mode=0o700)
        # Set every account/configuration namespace before importing Hermes or
        # the MCP SDK; the Workstation owner's real profile is never selected.
        os.environ.clear()
        os.environ.update({
            "HOME": str(private / "home"), "HERMES_HOME": str(private / "hermes"),
            "HERMES_MANAGED_DIR": str(private / "managed"),
            "XDG_CONFIG_HOME": str(private / "config"), "XDG_CACHE_HOME": str(private / "cache"),
            "XDG_DATA_HOME": str(private / "data"), "TMPDIR": str(private / "tmp"),
            "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
            "CHATBOTX_API_KEY": "SYNTHETIC_NOT_A_REAL_WORKSPACE_TOKEN",
        })
        shutil.copyfile(template, private / "hermes/config.yaml")
        (private / "hermes/config.yaml").chmod(0o600)
        os.chdir(private)
        sys.addaudithook(audit)
        signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(45)
        try:
            # Import the installed source with the installed Hermes environment.
            # Missing SDK support is a failed install gate, never a skipped test.
            sys.path.insert(0, str(hermes / "source"))
            import mcp
            import httpx2
            from mcp.types import Tool
            from hermes_cli.config import load_config_readonly
            from tools import mcp_tool
            from tools.registry import registry

            assert mcp is not None and httpx2 is not None
            assert mcp_tool._ensure_mcp_sdk() is True, "Installed Hermes MCP SDK is unavailable"
            report["checks"].append("native_mcp_sdk_available")
            config = load_config_readonly()["mcp_servers"]["chatbotx"]
            assert config["enabled"] is False and config["lazy"] is False
            assert mcp_tool._resolve_server_lazy("chatbotx", config) is False
            assert config["transport"] == "sse" and config["url"] == "https://app.chatbotx.io/mcp/sse"
            assert config["strict_redirect_headers"] is True
            assert config["headers"]["x-workspace-token"] == os.environ["CHATBOTX_API_KEY"]
            assert config["tools"] == {"include": [], "resources": False, "prompts": False}
            assert config["sampling"]["enabled"] is False and config["elicitation"]["enabled"] is False
            report["checks"].append("installed_template_and_native_header_interpolation")

            before = set(registry.get_all_tool_names())
            assert mcp_tool.register_mcp_servers({"chatbotx": config}) == []
            assert not mcp_tool._servers and not mcp_tool._server_connecting
            assert mcp_tool._mcp_thread is None and not mcp_tool._lazy_server_configs
            assert set(registry.get_all_tool_names()) == before
            report["checks"].append("disabled_server_has_no_connection_thread_or_registration")

            # Native registration sees an already-connected synthetic server;
            # no connection method is called and no real server is enabled.
            server = SimpleNamespace(
                _tools=[Tool(name="synthetic_read", description="Synthetic tool, never invoked",
                             inputSchema={"type": "object", "properties": {}})],
                tool_timeout=30, session=SimpleNamespace(),
                initialize_result=SimpleNamespace(capabilities=SimpleNamespace(resources=object(), prompts=object())),
            )
            enabled_fixture = copy.deepcopy(config)
            enabled_fixture["enabled"] = True
            assert mcp_tool._register_server_tools("chatbotx-native-synthetic", server, enabled_fixture) == []
            assert mcp_tool._select_utility_schemas("chatbotx-native-synthetic", server, enabled_fixture) == []
            assert set(registry.get_all_tool_names()) == before
            report["checks"].append("empty_native_tool_and_resource_prompt_registration")
            assert not network_attempts and not process_attempts
            assert template.read_bytes() == template_bytes
            report.update(network_attempts=0, child_process_attempts=0, registered_tools=0)
        finally:
            signal.alarm(0)
            os.chdir(previous_cwd)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
