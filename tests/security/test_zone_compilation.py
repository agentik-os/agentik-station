"""Zone-ID collisions must not merge identity or desired OS namespaces."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from agentik_station.configuration import StationConfig, ZoneTemplate, compile_zones, load_station_config
from agentik_station.errors import ValidationError
from agentik_station.identity import zone_unix_user
from agentik_station.models import InstallSpec, SeedSpec, ZoneSpec
from agentik_station.paths import LayoutPaths

ROOT = Path(__file__).resolve().parents[2]


def template(category="ORGANIZATIONS", name="alpha", environment="development", organization="alpha", requested_os=()):
    return ZoneTemplate(category, name, environment, organization, requested_os)


def config(*templates):
    return StationConfig("station.config/v2", "test-station", {"core": templates}, {})


@pytest.mark.parametrize("first,second", [
    (template(), template(category="PROJECTS")),
    (template(category="SYSTEM", name="same", environment="system", organization=None),
     template(category="PRIVATE", name="same", environment="private", organization=None)),
    (template(category="AGENTIK", name="dev", organization="agentik"),
     template(category="AGENTIK", name="dev", environment="production", organization="agentik")),
    (template(category="LAB", name="alpha-dev", environment="lab", organization=None), template()),
    (template(), template(organization="different-principal")),
])
def test_conflicting_semantic_definitions_with_same_zone_id_are_rejected(first, second):
    spec = InstallSpec()
    with pytest.raises(ValidationError, match="Conflicting Zone definitions"):
        compile_zones(spec, config(first, second))
    with pytest.raises(ValidationError, match="Conflicting Zone definitions"):
        compile_zones(spec, config(second, first))


@pytest.mark.parametrize("first_os,second_os", [
    (("builder-os",), ("devops-os",)), (("builder-os",), ()),
    ((), ("builder-os",)), (("builder-os", "devops-os"), ("builder-os",)),
])
def test_conflicting_os_declarations_are_not_last_writer_wins(first_os, second_os):
    with pytest.raises(ValidationError, match="Conflicting requested OS"):
        compile_zones(InstallSpec(), config(template(requested_os=first_os), template(requested_os=second_os)))


def test_identical_semantics_dedupe_and_preserve_first_declaration_order():
    first = template(requested_os=("builder-os", "devops-os"))
    reordered = replace(first, requested_os=("devops-os", "builder-os"))
    second = template(name="beta", organization="beta")
    zones, desired = compile_zones(InstallSpec(), config(first, reordered, second, second))
    assert [zone.zone_id for zone in zones] == ["alpha-dev", "beta-dev"]
    assert desired == {"alpha-dev": ("builder-os", "devops-os"), "beta-dev": ()}


def test_identical_seed_keeps_template_os_and_compiles_one_zone():
    selected = template(requested_os=("devops-os",))
    spec = InstallSpec(seed=SeedSpec("ORGANIZATIONS", "alpha", "dev", "alpha", "platform"))
    zones, desired = compile_zones(spec, config(selected))
    assert zones == [ZoneSpec("ORGANIZATIONS", "alpha", "development", spec.host_id, "alpha")]
    assert desired == {"alpha-dev": ("devops-os",)}


@pytest.mark.parametrize("seed", [
    SeedSpec("PROJECTS", "alpha", "development", "alpha"),
    SeedSpec("ORGANIZATIONS", "alpha", "development", "other"),
])
def test_conflicting_seed_cannot_reuse_template_namespace(seed):
    with pytest.raises(ValidationError, match="Conflicting Zone definitions"):
        compile_zones(InstallSpec(seed=seed), config(template(requested_os=("devops-os",))))


def test_seed_without_template_gets_empty_desired_os():
    zones, desired = compile_zones(InstallSpec(seed=SeedSpec("ORGANIZATIONS", "alpha", "development", "alpha")), config())
    assert [zone.zone_id for zone in zones] == ["alpha-dev"]
    assert desired == {"alpha-dev": ()}


def test_all_canonical_roles_preserve_zone_identities_and_host_scope():
    canonical = load_station_config(ROOT)
    for role, definitions in canonical.roles.items():
        spec = InstallSpec(role=role, host_id="fixture-host")
        zones, desired = compile_zones(spec, canonical)
        expected = [ZoneSpec(item.category, item.name, item.environment, spec.host_id, item.organization) for item in definitions]
        assert zones == expected
        assert desired == {zone.zone_id: item.requested_os for zone, item in zip(expected, definitions)}
    zones, _ = compile_zones(InstallSpec(role="core"), canonical)
    assert [zone.zone_id for zone in zones] == ["station-maintainer", "discord-bootstrap", "fleet-operator", "operator", "dev", "os", "hermes-edge"]


@pytest.mark.parametrize("path", sorted((ROOT / "config/examples/zones").glob("*.yaml")), ids=lambda path: path.stem)
def test_examples_use_canonical_unix_identity_and_runtime_hermes_home(path):
    example = yaml.safe_load(path.read_text())
    zone = ZoneSpec(example["category"], example["organization"], example["environment"], example["host"], example["organization"])
    assert example["id"] == path.stem == zone.zone_id
    assert example["unix_user"] == zone_unix_user(zone.category, zone.name, zone.environment)
    assert example["hermes_home"] == str(LayoutPaths.live().zones_state / zone.zone_id / "hermes")
