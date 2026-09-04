from __future__ import annotations

from pathlib import Path

import agentik_station.cli as cli

ROOT = Path(__file__).resolve().parents[2]


def test_versions_lock_pins_hermes_and_deps():
    lock = (ROOT / "config" / "versions.lock").read_text()
    for pin in (
        "HERMES_RELEASE=v2026.8.31",
        "HERMES_COMMIT=29112bef099274229cadff79cdff7bf7b99c4b77",
        "HERMES_INSTALL_SHA256=5854b15670b51a8daae8f59ddfa917062de9f74be261eb73b4b8d719710f8968",
        "PYTHON_VERSION=3.14.7",
        "AI_PYTHON_VERSION=3.13.15",
        "NODE_VERSION=24.20.0",
        "GITHUB_CLI_VERSION=2.100.0",
        "VERCEL_CLI_VERSION=59.11.2",
        "CODEX_CLI_VERSION=0.153.2",
        "COMPOSIO_CLI_VERSION=0.4.0",
        "COMPOSIO_INSTALL_SHA256=7a63922b75d206d16c790cdf683edac23f536903a28e13e94bfe3e55690b7a63",
        "LANGFUSE_RELEASE=v4.28.1",
        "CRAWL4AI_PYTHON_VERSION=0.9.3",
        "PONYTAIL_RELEASE=v4.9.0",
        "PONYTAIL_COMMIT=0a4dd63ad4541f4f655c4108a295916f3c1d8fda",
    ):
        assert pin in lock


def test_deps_stack_yaml_exists():
    stack = (ROOT / "config" / "deps" / "stack.yaml").read_text()
    for name in ("ponytail", "langfuse", "honcho", "hindsight", "tigervnc", "crawl4ai"):
        assert name in stack


def test_hermes_update_and_deps_scripts_executable():
    for rel in (
        "scripts/station_hermes_update.sh",
        "scripts/station_deps_install.sh",
        "scripts/station_toolchain_install.sh",
    ):
        path = ROOT / rel
        assert path.is_file()
        assert path.stat().st_mode & 0o111


def test_ponytail_install_uses_immutable_hermes_plugin_ref():
    script = (ROOT / "scripts" / "station_deps_install.sh").read_text()
    assert 'plugins install "$PONYTAIL_REPOSITORY" --ref "$PONYTAIL_COMMIT" --enable' in script


def test_catalog_includes_new_modules():
    import json
    catalog = json.loads((ROOT / "modules" / "catalog.json").read_text())
    ids = {m["id"] for m in catalog["modules"]}
    for mid in ("hermes-platforms", "ponytail", "langfuse", "honcho", "hindsight", "crawl4ai", "tigervnc"):
        assert mid in ids


def test_cli_registers_deps_and_hermes_update():
    parser = cli.build_parser()
    parser.parse_args(["hermes", "update", "--check-only"])
    parser.parse_args(["deps", "list"])
    parser.parse_args(["deps", "platforms"])
    parser.parse_args(["deps", "toolchain-plan"])
    parser.parse_args(["deps", "toolchain-check"])
    parser.parse_args(["platform", "setup", "--zone", "organization-alpha-dev", "--platform", "slack", "--plan"])
