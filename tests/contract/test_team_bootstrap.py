from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_full_and_team_modes_are_distinct() -> None:
    config = json.loads((ROOT / "config" / "station.default.json").read_text())
    assert set(config["roles"]) == {"core", "team", "project", "lab", "worker"}
    core_categories = {z["category"] for z in config["roles"]["core"]["zones"]}
    team_categories = {z["category"] for z in config["roles"]["team"]["zones"]}
    assert "PRIVATE" in core_categories
    assert "PRIVATE" not in team_categories
    assert team_categories == {"SYSTEM"}


def test_global_organization_category_replaces_client_category() -> None:
    schema = json.loads((ROOT / "config" / "schemas" / "zone.schema.json").read_text())
    values = schema["properties"]["category"]["enum"]
    assert "ORGANIZATIONS" in values
    assert "CLIENTS" not in values
    assert "4_ORGANIZATIONS" in (ROOT / "src" / "agentik_station" / "constants.py").read_text()


def test_bootstrap_uses_dedicated_account_and_no_piped_installers() -> None:
    text = (ROOT / "bootstrap.sh").read_text()
    assert 'STATION_USER="agk-station"' in text
    assert "/home/${STATION_USER}" in text
    assert "station_toolchain_install.sh" in text
    assert "--skip-hermes-auto-update" in text
    assert "HERMES_INSTALL_SHA256" in text
    assert 'HERMES_COMMIT' in text
    assert '--dir "$hermes_install_dir"' in text
    assert 'curl --fail --silent --show-error --location "$HERMES_INSTALL_URL"' in text
    assert "curl -fsSL" not in text
    assert "| bash" not in text
    assert 'source_root" == /root' in text


def test_member_contract_is_present() -> None:
    schema = json.loads((ROOT / "contracts" / "member.schema.json").read_text())
    assert "member_id" in schema["required"]
    assert "principal_id" in schema["required"]
    assert (ROOT / "templates" / "member" / "MEMBER.example.json").is_file()
