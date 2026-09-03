from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "runtime" / "hermes-station" / "hermes" / "plugins" / "station-discord-experience"


def _load_plugin():
    name = "station_discord_experience_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(
        name,
        PLUGIN / "__init__.py",
        submodule_search_locations=[str(PLUGIN)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_declares_tools_hooks_and_non_operational_maturity() -> None:
    manifest = yaml.safe_load((PLUGIN / "plugin.yaml").read_text())
    assert set(manifest["provides_tools"]) == {
        "station_mission_plan",
        "station_plan_update",
        "station_progress",
        "station_mission_close",
    }
    assert "pre_tool_call" in manifest["provides_hooks"]
    assert manifest["maturity"] == "SCAFFOLDED"
    assert manifest["runtime_state"] == "NOT_INSTALLED"


def test_plan_first_hook_fails_closed_without_bound_mission(monkeypatch) -> None:
    plugin = _load_plugin()
    monkeypatch.delenv("STATION_CURRENT_MISSION_ID", raising=False)
    result = plugin._pre_tool(tool_name="write_file", args={}, task_id="task-1")
    assert result["action"] == "block"
    assert "unresolved" in result["message"].lower()


def test_plan_first_hook_blocks_until_plan_exists(tmp_path: Path, monkeypatch) -> None:
    plugin = _load_plugin()
    monkeypatch.setenv("STATION_ZONE_STATE_ROOT", str(tmp_path / "zone"))
    monkeypatch.setenv("STATION_CURRENT_MISSION_ID", "mission-1")
    blocked = plugin._pre_tool(tool_name="terminal_execute", args={}, task_id="task-1")
    assert blocked["action"] == "block"
    response = json.loads(
        plugin.tools.mission_plan(
            {
                "mission_id": "mission-1",
                "objective": "Build safely",
                "nodes": [{"id": "plan", "label": "Plan", "status": "ready"}],
                "acceptance": ["verified"],
            }
        )
    )
    assert response["success"] is True
    assert plugin._pre_tool(tool_name="terminal_execute", args={}, task_id="task-1") is None


def test_discord_state_database_cannot_escape_zone(tmp_path: Path, monkeypatch) -> None:
    plugin = _load_plugin()
    zone = tmp_path / "zone"
    monkeypatch.setenv("STATION_ZONE_STATE_ROOT", str(zone))
    monkeypatch.setenv("STATION_DISCORD_EXPERIENCE_DB", str(tmp_path / "outside.db"))
    try:
        plugin.state.database_path()
        raise AssertionError("expected containment failure")
    except RuntimeError as exc:
        assert "inside" in str(exc)
