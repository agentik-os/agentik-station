from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from agentik_station.errors import ValidationError
from agentik_station.full_stack import COMPONENTS
from agentik_station.os_runtime import compile_os_to_hermes
from agentik_station.resources import build_os_resource_index, load_resource_catalog

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["stepper", "builder"])
def test_build_teams_receive_complete_real_catalog_without_live_readiness(tmp_path, name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "compiled"
    result = compile_os_to_hermes(ROOT / "os" / name, output, workspace_root=workspace,
                                  zone_id="os", instance_id=name)
    for profile in result["profiles"]:
        path = output / "profiles" / profile
        index = json.loads((path / "STATION_RESOURCES.json").read_text())
        assert index == build_os_resource_index(ROOT)
        assert index["catalog"] == load_resource_catalog(ROOT / "resources/CATALOG.json")
        assert {item["id"] for item in index["host_software_requirements"]} == {item.id for item in COMPONENTS}
        assert all(item["state"] == "NOT_PROBED" for item in index["host_software_requirements"])
        assert index["claim"] == "DECLARED_NOT_PROBED"
        assert index["operational"] is False and index["accounts_enrolled"] is False
        assert index["execution_authorized"] is False
        assert index["preferred_stack_plan"]["working_directory"] == "OWNING_PROJECT_REPOSITORY"
        assert index["preferred_stack_plan"]["claim"] == "PLAN_ONLY_NOT_INSTALLED"
        assert "STATION_RESOURCES.json" in yaml.safe_load((path / "distribution.yaml").read_text())["distribution_owned"]
        skill = (path / "skills/station-resources/SKILL.md").read_text()
        assert "Installed software is not a connected service" in index["integration_rule"]
        assert "or copy secrets" in skill.lower()
        assert "station-resources" in (path / "SOUL.md").read_text()


def test_resource_index_is_source_only_no_native_or_account_probe(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Source compilation executed a probe"))
    index = build_os_resource_index(ROOT)
    assert index["host_readback"]["argv"] == ["station", "deps", "full-check"]
    assert index["profile_tool_declarations"] == ["station_crawl4ai", "station_scrapegraph"]


@pytest.mark.parametrize("raw", ['{"schema_version":1,"schema_version":1}',
                                '{"schema_version":true}', '[]', '{"schema_version":'])
def test_resource_catalog_rejects_ambiguous_or_invalid_data(tmp_path, raw):
    path = tmp_path / "catalog.json"
    path.write_text(raw)
    with pytest.raises(ValidationError):
        load_resource_catalog(path)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "oversized", "fifo"])
def test_resource_catalog_never_follows_links_or_blocks_on_special_files(tmp_path, kind):
    path = tmp_path / "catalog.json"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink":
        path.symlink_to(ROOT / "resources/CATALOG.json")
    else:
        path.write_bytes((ROOT / "resources/CATALOG.json").read_bytes())
        if kind == "hardlink":
            os.link(path, tmp_path / "alias.json")
        else:
            path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValidationError):
        load_resource_catalog(path)
