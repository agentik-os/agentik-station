from __future__ import annotations

from pathlib import Path

import agentik_station.cli as cli

ROOT = Path(__file__).resolve().parents[2]


def test_versions_lock_pins_hermes_and_deps():
    lock = (ROOT / "config" / "versions.lock").read_text()
    assert "HERMES_RELEASE=" in lock
    assert "LANGFUSE_REPOSITORY=" in lock
    assert "CRAWL4AI_REPOSITORY=" in lock
    assert "PONYTAIL_REPOSITORY=" in lock


def test_deps_stack_yaml_exists():
    stack = (ROOT / "config" / "deps" / "stack.yaml").read_text()
    for name in ("ponytail", "langfuse", "honcho", "hindsight", "tigervnc", "crawl4ai"):
        assert name in stack


def test_hermes_update_and_deps_scripts_executable():
    for rel in ("scripts/station_hermes_update.sh", "scripts/station_deps_install.sh"):
        path = ROOT / rel
        assert path.is_file()
        assert path.stat().st_mode & 0o111


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
