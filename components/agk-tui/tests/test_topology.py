import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agk_topology", ROOT / "scripts/topology.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_repository_topology_has_stable_product_profiles_and_exact_layouts():
    manager = MODULE.TopologyManager(ROOT / "config/topology.yaml")
    assert manager.mode == "multi-user"
    assert tuple(manager.profiles) == ("operator", "agentik", "mission", "private")
    assert manager.profiles["operator"].workspace_layout == (
        "infrastructure", "security", "deployments", "monitoring",
        "automation", "deposit", "docs",
    )
    assert manager.profiles["agentik"].workspace_layout == (
        "projects", "products", "missions", "research", "content",
        "growth", "community", "knowledge", "artifacts",
    )
    assert manager.profiles["mission"].client_layout == MODULE.CLIENT_LAYOUT
    assert manager.profiles["private"].workspace_layout == (
        "projects", "journal", "goals", "learning", "research", "knowledge", "artifacts",
    )


def test_detection_is_read_only_and_reports_runtime_mapping(tmp_path):
    home = Path.home()
    config = {
        "schema_version": 1,
        "mode": "multi-user",
        "machine_id": "test-core",
        "shared": {
            "hermes_code": str(home / "missing-hermes-code"),
            "hermes_alias": str(home / "missing-hermes-alias"),
            "os_registry": str(home / "missing-os-registry"),
        },
        "profiles": {
            "operator": {
                "runtime": {"driver": "linux-user", "linux_user": os.environ["USER"]},
                "workspace": str(home / "missing-workspace"),
                "hermes_home": str(home / "missing-hermes-home"),
                "workspace_layout": ["infrastructure"],
            }
        },
    }
    path = tmp_path / "topology.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    status = MODULE.TopologyManager(path).detect()
    assert status["machine_id"] == "test-core"
    assert status["profiles"][0]["profile_id"] == "operator"
    assert status["profiles"][0]["runtime_driver"] == "linux-user"
    assert status["profiles"][0]["missing_workspace_dirs"] == ["infrastructure"]
    assert not (home / "missing-workspace").exists()


def test_unsafe_topology_is_rejected(tmp_path):
    config = {
        "schema_version": 1,
        "mode": "multi-user",
        "shared": {"hermes_code": "/", "hermes_alias": "/tmp/alias", "os_registry": "/tmp/os"},
        "profiles": {"operator": {}},
    }
    path = tmp_path / "topology.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="specific absolute path"):
        MODULE.TopologyManager(path)


def test_apply_requires_root(monkeypatch):
    manager = MODULE.TopologyManager(ROOT / "config/topology.yaml")
    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="root"):
        manager.apply()


def test_cached_status_round_trip(tmp_path, monkeypatch):
    cache = tmp_path / "topology-status.json"
    monkeypatch.setenv("AGK_TOPOLOGY_STATUS", str(cache))
    expected = {"schema_version": 1, "recommended": True, "profiles": []}
    cache.write_text(json.dumps(expected), encoding="utf-8")

    manager = MODULE.TopologyManager(ROOT / "config/topology.yaml")
    assert manager.cached_status() == expected
