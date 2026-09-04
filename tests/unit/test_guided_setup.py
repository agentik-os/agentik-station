from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentik_station.errors import SecurityError, ValidationError
from agentik_station.guided_setup import LinkUnavailable, SetupLinkStore, setup_link_card


def _create(store: SetupLinkStore, *, now: int = 1000, purpose: str = "hermes-credentials"):
    target = "https://station.example.ts.net/operator/config"
    if purpose == "composio-oauth":
        target = "https://connect.composio.dev/link/ln_example"
    return store.create(
        base_url="https://station.example.ts.net/station-setup",
        target_url=target,
        zone_id="station-system",
        principal_id="discord-123456789",
        provider="openai" if purpose == "hermes-credentials" else "composio",
        purpose=purpose,
        now=now,
    )


def _url_parts(url: str) -> tuple[str, str]:
    session_id, token = url.rsplit("/", 2)[-2:]
    return session_id, token


def test_setup_link_is_hashed_scoped_expiring_and_single_use(tmp_path: Path) -> None:
    store = SetupLinkStore(tmp_path / "links")
    created = _create(store)
    session_id, token = _url_parts(created.url)
    record = json.loads((store.root / f"{session_id}.json").read_text())

    assert token not in json.dumps(record)
    assert record["token_sha256"]
    assert record["zone_id"] == "station-system"
    assert store.peek(session_id, token, now=1100)["provider"] == "openai"
    assert store.consume(session_id, token, now=1100).endswith("/operator/config")
    with pytest.raises(LinkUnavailable, match="already been used"):
        store.consume(session_id, token, now=1101)


def test_setup_link_expiry_and_target_allowlists_fail_closed(tmp_path: Path) -> None:
    store = SetupLinkStore(tmp_path / "links")
    created = _create(store)
    session_id, token = _url_parts(created.url)
    with pytest.raises(LinkUnavailable, match="expired"):
        store.peek(session_id, token, now=1600)
    with pytest.raises(ValidationError, match="connect.composio.dev"):
        store.create(
            base_url="https://station.example.ts.net/setup",
            target_url="https://evil.example/connect",
            zone_id="station-system",
            principal_id="discord-123456789",
            provider="composio",
            purpose="composio-oauth",
        )
    with pytest.raises(ValidationError, match="Tailscale"):
        store.create(
            base_url="https://public.example/setup",
            target_url="https://station.example.ts.net/config",
            zone_id="station-system",
            principal_id="discord-123456789",
            provider="openai",
            purpose="hermes-credentials",
        )


def test_setup_link_state_rejects_symlink_and_card_is_provider_neutral(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SecurityError):
        SetupLinkStore(link / "sessions")

    store = SetupLinkStore(tmp_path / "safe")
    card = setup_link_card(_create(store, purpose="composio-oauth"))
    assert card["type"] == "station.guided_setup"
    assert card["visibility"] == "requesting-principal-only"
    assert card["actions"][0]["label"] == "Open secure setup"
    assert "credential" not in card["actions"][0]["url"]


def test_station_secret_is_written_only_to_zone_hermes_env(tmp_path: Path) -> None:
    zone = tmp_path / "zone"
    store = SetupLinkStore(zone / "connector-state" / "setup-links")
    created = store.create(
        base_url="https://station.example.ts.net/station-setup",
        target_url=None,
        zone_id="station-system",
        principal_id="discord-123456789",
        provider="openai",
        purpose="station-secret",
        now=1000,
    )
    session_id, token = _url_parts(created.url)
    assert store.submit_secret(session_id, token, "sk-test-value", now=1001) == "openai"
    env_file = zone / "hermes" / ".env"
    assert env_file.read_text() == "OPENAI_API_KEY=sk-test-value\n"
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert "sk-test-value" not in (store.root / f"{session_id}.json").read_text()


def test_station_secret_rejects_unmapped_provider_and_multiline_values(tmp_path: Path) -> None:
    zone = tmp_path / "zone"
    store = SetupLinkStore(zone / "connector-state" / "setup-links")
    with pytest.raises(ValidationError, match="allowlisted"):
        store.create(
            base_url="https://station.example.ts.net/station-setup",
            target_url=None,
            zone_id="station-system",
            principal_id="discord-123456789",
            provider="unknown",
            purpose="station-secret",
        )
    created = store.create(
        base_url="https://station.example.ts.net/station-setup",
        target_url=None,
        zone_id="station-system",
        principal_id="discord-123456789",
        provider="discord",
        purpose="station-secret",
        now=1000,
    )
    with pytest.raises(ValidationError, match="whitespace"):
        store.submit_secret(*_url_parts(created.url), "first\nsecond", now=1001)


def test_station_secret_rejects_symlinked_env_without_touching_target(tmp_path: Path) -> None:
    zone = tmp_path / "zone"
    hermes = zone / "hermes"
    hermes.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.write_text("unchanged\n", encoding="utf-8")
    (hermes / ".env").symlink_to(victim)
    store = SetupLinkStore(zone / "connector-state" / "setup-links")
    created = store.create(
        base_url="https://station.example.ts.net/station-setup",
        target_url=None,
        zone_id="station-system",
        principal_id="discord-123456789",
        provider="openai",
        purpose="station-secret",
        now=1000,
    )

    with pytest.raises(SecurityError, match="credential file"):
        store.submit_secret(*_url_parts(created.url), "sk-test-value", now=1001)

    assert victim.read_text(encoding="utf-8") == "unchanged\n"
