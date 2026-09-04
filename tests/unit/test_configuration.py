from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentik_station.configuration import load_station_config
from agentik_station.errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def _minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "os").mkdir(parents=True)
    shutil.copy2(ROOT / "config" / "station.default.json", repo / "config" / "station.default.json")
    shutil.copy2(ROOT / "os" / "CATALOG.json", repo / "os" / "CATALOG.json")
    return repo


def test_canonical_config_loads_and_contains_every_host_role() -> None:
    config = load_station_config(ROOT)
    assert set(config.roles) == {"core", "team", "project", "lab", "worker"}
    assert config.policy["unresolved_context"] == "block"


def test_unknown_config_field_is_rejected(tmp_path: Path) -> None:
    repo = _minimal_repo(tmp_path)
    path = repo / "config" / "station.default.json"
    payload = json.loads(path.read_text())
    payload["mystery"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="Unknown canonical"):
        load_station_config(repo)


def test_unsafe_policy_relaxation_is_rejected(tmp_path: Path) -> None:
    repo = _minimal_repo(tmp_path)
    path = repo / "config" / "station.default.json"
    payload = json.loads(path.read_text())
    payload["policy"]["cross_zone_mounts"] = "allow"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="Unsafe or unsupported"):
        load_station_config(repo)


def test_unknown_requested_os_is_rejected(tmp_path: Path) -> None:
    repo = _minimal_repo(tmp_path)
    path = repo / "config" / "station.default.json"
    payload = json.loads(path.read_text())
    payload["roles"]["core"]["zones"][0]["requested_os"] = ["unknown-os"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="absent from the catalog"):
        load_station_config(repo)
