from __future__ import annotations

from pathlib import Path

from agentik_station.configuration import load_station_config
from agentik_station.models import InstallSpec, SeedSpec
from agentik_station.planner import build_plan, zone_specs

ROOT = Path(__file__).resolve().parents[2]


def _zone_ids(spec: InstallSpec) -> set[str]:
    config = load_station_config(ROOT)
    return {zone.zone_id for zone in zone_specs(spec, config)}


def test_core_role_compiles_expected_canonical_zones() -> None:
    ids = _zone_ids(InstallSpec(host_id="station-core-01", role="core"))
    assert {"station-maintainer", "discord-bootstrap", "fleet-operator", "operator", "dev", "os", "hermes-edge"} <= ids


def test_client_host_compiles_only_system_and_requested_client_zone() -> None:
    spec = InstallSpec(
        host_id="organization-alpha-prod-01",
        role="team",
        seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha", "platform"),
    )
    ids = _zone_ids(spec)
    assert ids == {"station-maintainer", "discord-bootstrap", "fleet-operator", "organization-alpha-prod"}
    assert "operator" not in ids and "dev" not in ids and "os" not in ids


def test_plan_is_typed_and_ends_at_ready_for_setup() -> None:
    spec = InstallSpec(host_id="station-core-01", role="core")
    steps = build_plan(spec, load_station_config(ROOT))
    assert steps
    assert all(step.id and step.description and isinstance(step.detail, dict) for step in steps)
    assert [step.id for step in steps][-2:] == ["doctor", "receipt"]
