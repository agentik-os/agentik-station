"""Cross-surface declarations supplement, not replace, native installer probes."""
from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def resource():
    return json.loads((ROOT / "resources/chatbotx/RESOURCE.json").read_text())


def test_chatbotx_reviewed_pins_agree_across_installation_catalogs():
    pins = dict(line.split("=", 1) for line in (ROOT / "config/versions.lock").read_text().splitlines()
                if line and not line.startswith("#"))
    row = resource()
    catalog = json.loads((ROOT / "resources/CATALOG.json").read_text())
    declared = next(item for item in catalog["resources"] if item["id"] == "chatbotx")
    stack = yaml.safe_load((ROOT / "config/deps/stack.yaml").read_text())
    component = next(item for item in stack["components"] if item["id"] == "chatbotx")
    assert row["version"] == declared["version"] == component["version"] == pins["CHATBOTX_CLI_VERSION"]
    assert row["integrity"] == declared["integrity"] == pins["CHATBOTX_CLI_NPM_INTEGRITY"]
    assert row["entry_sha256"] == pins["CHATBOTX_CLI_ENTRY_SHA256"]
    assert row["commit"] == component["commit_pin"] == pins["CHATBOTX_REVIEW_COMMIT"]
    assert row["repository"] == "https://github.com/" + pins["CHATBOTX_REPOSITORY"]
    assert row["host_node"] == pins["NODE_VERSION"]


def test_chatbotx_is_default_software_but_not_an_account_or_application_claim():
    row = resource()
    modules = json.loads((ROOT / "modules/catalog.json").read_text())["modules"]
    module = next(item for item in modules if item["id"] == "chatbotx")
    assert module["maturity"] == "INSTALLABLE"
    assert module["binary_probes"] == []  # configured upstream --version can fetch a schema
    assert row["runtime_claim"] == "NOT_INSTALLED"
    assert row["connection_claim"] == "NOT_CONFIGURED"
    assert row["mcp"]["npm_published_at_review"] is False
    assert row["mcp"]["local_server_installed"] is False
    assert row["self_hosted_application"]["installed"] is False
    assert row["configuration"]["home_boundary"] == "Unix-HOME-not-HERMES_HOME"
    for key in ("automatic_account_enrollment", "automatic_mcp_connection", "automatic_message_sending",
                "automatic_self_hosting", "install_scripts"):
        assert row["security"][key] is False
    host = (ROOT / "scripts/station_toolchain_install.sh").read_text()
    portable = (ROOT / "installer/npm/runtime.mjs").read_text()
    assert "\ninstall_chatbotx_cli\n" in host
    assert "--global=false --ignore-scripts --bin-links=false" in host
    assert "['chatbotx', 'CHATBOTX_CLI_VERSION', 'CHATBOTX_CLI_NPM_INTEGRITY', 'chatbotx']" in portable
    assert "['install', '--ignore-scripts', '--no-audit', '--no-fund'" in portable
    assert "chatbotx-mcp-server@" not in host + portable
    assert "'--extra', 'mcp'" in portable
    assert "import hermes_cli.main, discord, nacl.secret, openai, yaml, mcp, httpx2" in portable
    assert "assert m.version('hermes-agent') and _ensure_mcp_sdk()" in portable
    bootstrap = (ROOT / "bootstrap.sh").read_text()
    assert "import mcp, httpx2" in bootstrap and "if not _ensure_mcp_sdk():" in bootstrap
    probe = bootstrap.split("with tempfile.TemporaryDirectory(prefix='station-hermes-mcp-check-')", 1)[1].split("print('Hermes shared Python", 1)[0]
    assert probe.index("os.environ.clear()") < probe.index("import mcp, httpx2")
    assert "HERMES_MANAGED_DIR=str(home / 'managed')" in probe


def test_chatbotx_mcp_template_defaults_to_no_connection_or_tools():
    template = yaml.safe_load((ROOT / "resources/chatbotx/hermes-mcp.example.yaml").read_text())
    assert set(template["mcp_servers"]) == {"chatbotx"}
    server = template["mcp_servers"]["chatbotx"]
    assert server["enabled"] is False
    assert server["lazy"] is False
    assert server["url"] == resource()["mcp"]["url"] == "https://app.chatbotx.io/mcp/sse"
    assert server["transport"] == "sse"
    assert server["strict_redirect_headers"] is True
    assert server["headers"] == {"x-workspace-token": "${CHATBOTX_API_KEY}"}
    assert server["tools"] == {"include": [], "resources": False, "prompts": False}
    assert server["sampling"]["enabled"] is False
    assert server["elicitation"]["enabled"] is False
    assert "command" not in server  # never fabricate an unpublished npm MCP dependency


def test_chatbotx_resources_and_notice_ship_in_npm_package():
    package = json.loads((ROOT / "package.json").read_text())
    assert "resources/" in package["files"]
    for name in ("RESOURCE.json", "README.md", "hermes-mcp.example.yaml", "LICENSE.upstream"):
        assert (ROOT / "resources/chatbotx" / name).is_file()
    notice = (ROOT / "resources/chatbotx/LICENSE.upstream").read_text()
    assert "MIT license" in notice and "Permission is hereby granted" in notice
    assert "resources/chatbotx/LICENSE.upstream" in (ROOT / "THIRD_PARTY.md").read_text()
