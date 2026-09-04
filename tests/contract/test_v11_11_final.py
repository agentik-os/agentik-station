from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentik_station.errors import ValidationError
from agentik_station.maturity import load_catalog, load_os_catalog
from agentik_station.os_contract import doctor_os_source
from agentik_station.os_runtime import compile_os_to_hermes
from agentik_station.providers.composio import ComposioBinding, stable_principal
from agentik_station.providers.discord import verify_binding
from agentik_station.providers.rootless import zone_readiness

ROOT = Path(__file__).resolve().parents[2]


def test_real_librarian_v3_is_canonical() -> None:
    manifest = json.loads((ROOT / "os/librarian/MANIFEST.json").read_text())
    assert manifest["name"] == "Librarian OS"
    assert manifest["version"] == "3.0.0"
    agents = [p for p in (ROOT / "os/librarian/skills/book/agents").iterdir() if p.is_file() and p.suffix == ".md"]
    assert len(agents) == 15
    commands = (ROOT / "os/librarian/discord/COMMANDS.yaml").read_text()
    for command in ["research", "book", "bestseller", "web-deep", "latest", "triangulate", "research-to-os"]:
        assert command in commands


def test_every_canonical_os_passes_source_doctor() -> None:
    catalog = load_os_catalog(ROOT / "os/CATALOG.json")
    for entry in catalog["packages"]:
        result = doctor_os_source(ROOT / entry["path"], expected_id=entry["id"])
        assert result.ok, (entry["id"], result.issues)


def test_every_canonical_os_compiles_to_hermes(tmp_path: Path) -> None:
    catalog = load_os_catalog(ROOT / "os/CATALOG.json")
    project_root = tmp_path / "project"
    project_root.mkdir()
    for entry in catalog["packages"]:
        output = tmp_path / "dist" / entry["id"]
        compiled = compile_os_to_hermes(ROOT / entry["path"], output, project_root=project_root)
        assert compiled["claim"] == "COMPILED_NOT_INSTALLED"
        assert compiled["profiles"]
        for profile in compiled["profiles"]:
            profile_root = output / "profiles" / profile
            assert (profile_root / "distribution.yaml").is_file()
            assert (profile_root / "config.yaml").is_file()
            assert (profile_root / "STATION_RULES.md").is_file()
            assert "Station universal agent rules" in (profile_root / "SOUL.md").read_text()
            assert "home_mode: profile" in (profile_root / "config.yaml").read_text()


def test_module_catalog_truthful_and_parses() -> None:
    catalog = load_catalog(ROOT / "modules/catalog.json")
    assert all(item["maturity"] != "OPERATIONAL" for item in catalog["modules"])
    by_id = {item["id"]: item for item in catalog["modules"]}
    assert by_id["station-kernel"]["maturity"] == "VERIFIED"
    assert by_id["discord-experience"]["maturity"] == "INSTALLABLE"


def test_composio_principal_and_explicit_allowlist() -> None:
    binding = ComposioBinding.from_dict({
        "zone_id": "organization-alpha-dev",
        "organization_id": "organization-alpha",
        "subject_id": "sales-director",
        "toolkits": ["gmail", "notion"],
        "connected_accounts": {"gmail": ["ca-work"]},
    })
    assert binding.principal == stable_principal("organization-alpha-dev", "organization-alpha", "sales-director")
    assert binding.to_session_config()["mcp"] is True
    with pytest.raises(ValidationError):
        ComposioBinding.from_dict({
            "zone_id": "organization-alpha-dev",
            "organization_id": "organization-alpha",
            "subject_id": "sales-director",
            "toolkits": ["gmail"],
            "connected_accounts": {"notion": ["ca-wrong"]},
        })


def test_discord_binding_requires_host_owned_absolute_token_reference(tmp_path: Path) -> None:
    valid = verify_binding({
        "zone_id": "organization-alpha-dev",
        "os_id": "devops-os",
        "profile_id": "atlas",
        "guild_id": "1234567890",
        "channel_id": "1234567891",
        "token_file": "/run/credentials/devops/discord-token",
    })
    assert valid["profile_id"] == "atlas"
    with pytest.raises(ValidationError):
        verify_binding({
            "zone_id": "organization-alpha-dev",
            "os_id": "devops-os",
            "profile_id": "atlas",
            "guild_id": "1234567890",
            "channel_id": "1234567891",
            "token_file": "./token",
        })


def test_rootless_readiness_does_not_overclaim(tmp_path: Path) -> None:
    state = zone_readiness(tmp_path)
    assert state["verified"] is False
    assert state["state"] == "SCAFFOLDED"


def test_no_active_parallel_os_source_trees() -> None:
    assert not (ROOT / "packages/os").exists()
    assert not (ROOT / "source-packs").exists()
    assert (ROOT / "os/CATALOG.json").is_file()


def test_backup_plan_uses_explicit_regular_credential_references(tmp_path: Path) -> None:
    from agentik_station.providers.backup import plan_backup
    repo = tmp_path / "repository.ref"
    password = tmp_path / "password.ref"
    repo.write_text("s3:https://example.invalid/bucket")
    password.write_text("not-a-real-password")
    payload = plan_backup("organization-alpha-dev", [tmp_path / "zone"], repo.resolve(), password.resolve())
    assert payload["provider"] == "restic"
    assert payload["claim"] == "PLAN_NOT_RUN"


def test_remote_plan_includes_full_doctor_readback() -> None:
    from agentik_station.models import InstallSpec, SeedSpec
    from agentik_station.remote import build_remote_plan
    spec = InstallSpec(
        operation_id="op-v11-1-readback",
        host_id="organization-alpha-prod-01",
        role="team",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
        seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha", "platform"),
    )
    plan = build_remote_plan("operator@organization-alpha-prod-01", 22, spec)
    command_text = "\n".join(" ".join(command) for command in plan["commands"])
    assert "station doctor --full --json" in command_text
    assert "platform" not in command_text
    assert "--seed-name" not in command_text
