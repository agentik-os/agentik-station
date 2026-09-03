from __future__ import annotations

import json

import pytest

from agentik_station.errors import ValidationError
from agentik_station.models import InstallSpec, SeedSpec, ZoneSpec


def test_install_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Unknown InstallSpec"):
        InstallSpec.from_dict({"host_id": "gareth-core-01", "mystery": True})


def test_install_spec_requires_real_json_booleans() -> None:
    with pytest.raises(ValidationError, match="JSON boolean"):
        InstallSpec.from_dict({"install_system_packages": "false"})


def test_client_host_may_only_seed_client_zone() -> None:
    seed = SeedSpec("PROJECTS", "verba", "production", "gareth", "app")
    with pytest.raises(ValidationError, match="client Host"):
        InstallSpec(role="client", seed=seed)


def test_seed_rejects_non_deployment_environment() -> None:
    with pytest.raises(ValidationError):
        SeedSpec("CLIENTS", "moonbase", "lab", "moonbase", "platform")


def test_zone_category_environment_contract() -> None:
    zone = ZoneSpec("CLIENTS", "moonbase", "production", "moonbase-prod-01", "moonbase")
    assert zone.zone_id == "moonbase-prod"
    with pytest.raises(ValidationError):
        ZoneSpec("PRIVATE", "gareth", "production", "gareth-core-01", "gareth")


def test_install_spec_roundtrip(tmp_path) -> None:
    spec = InstallSpec(
        operation_id="op-test-roundtrip",
        host_id="moonbase-prod-01",
        role="client",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
        seed=SeedSpec("CLIENTS", "moonbase", "production", "moonbase", "platform"),
    )
    path = tmp_path / "install-spec.json"
    spec.write(path)
    assert json.loads(path.read_text())["seed"]["project"] == "platform"
    assert InstallSpec.load(path) == spec
    with pytest.raises(ValidationError):
        spec.write(path)
