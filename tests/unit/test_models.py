from __future__ import annotations

import json

import pytest

from agentik_station.errors import ValidationError
from agentik_station.models import InstallSpec, SeedSpec, ZoneSpec


def test_install_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Unknown InstallSpec"):
        InstallSpec.from_dict({"host_id": "station-core-01", "mystery": True})


def test_install_spec_requires_real_json_booleans() -> None:
    with pytest.raises(ValidationError, match="JSON boolean"):
        InstallSpec.from_dict({"install_system_packages": "false"})


def test_client_host_may_only_seed_client_zone() -> None:
    seed = SeedSpec("PROJECTS", "example-project", "production", "operator", "app")
    with pytest.raises(ValidationError, match="team Host"):
        InstallSpec(role="team", seed=seed)


def test_seed_rejects_non_deployment_environment() -> None:
    with pytest.raises(ValidationError):
        SeedSpec("ORGANIZATIONS", "organization-alpha", "lab", "organization-alpha", "platform")


def test_zone_category_environment_contract() -> None:
    zone = ZoneSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha-prod-01", "organization-alpha")
    assert zone.zone_id == "organization-alpha-prod"
    with pytest.raises(ValidationError):
        ZoneSpec("PRIVATE", "operator", "production", "station-core-01", "operator")


def test_install_spec_roundtrip(tmp_path) -> None:
    spec = InstallSpec(
        operation_id="op-test-roundtrip",
        host_id="organization-alpha-prod-01",
        role="team",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
        seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha", "platform"),
    )
    path = tmp_path / "install-spec.json"
    spec.write(path)
    assert json.loads(path.read_text())["seed"]["project"] == "platform"
    assert InstallSpec.load(path) == spec
    with pytest.raises(ValidationError):
        spec.write(path)
