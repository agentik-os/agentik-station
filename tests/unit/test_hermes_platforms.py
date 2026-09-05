from pathlib import Path

import pytest

from agentik_station.errors import ValidationError
from agentik_station.hermes_platforms import (
    GATEWAY_ACTIONS, SUPPORTED_PLATFORMS, build_gateway_argv, gateway_service_name, normalize_platform,
    platform_setup_guidance,
)


def _zone() -> dict[str, str]:
    return {
        "unix_user": "z-org-alpha-dev",
        "state_root": "/var/lib/station/zones/organization-alpha-dev",
        "hermes_home": "/var/lib/station/zones/organization-alpha-dev/hermes",
    }


def test_platform_aliases_and_supported_surface() -> None:
    assert normalize_platform("Teams") == "microsoft-teams"
    assert normalize_platform("Feishu/Lark") == "feishu-lark"
    assert {"discord", "slack", "telegram", "whatsapp", "signal", "matrix"} <= set(SUPPORTED_PLATFORMS)
    with pytest.raises(ValidationError):
        normalize_platform("made-up-chat")


def test_gateway_command_preserves_zone_identity_and_home() -> None:
    argv = build_gateway_argv(
        _zone(),
        "status",
        runtime_uid=12001,
        hermes_binary=Path("/usr/local/bin/hermes"),
        runuser_binary=Path("/usr/sbin/runuser"),
    )
    assert argv[:4] == ["/usr/sbin/runuser", "--user", "z-org-alpha-dev", "--"]
    assert argv[4:6] == ["/usr/bin/env", "-i"]
    assert "HERMES_HOME=/var/lib/station/zones/organization-alpha-dev/hermes" in argv
    assert "XDG_RUNTIME_DIR=/run/user/12001" in argv
    assert "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/12001/bus" in argv
    assert argv[-5:] == ["/usr/local/bin/hermes", "--profile", "default", "gateway", "status"]


def test_gateway_command_rejects_cross_zone_hermes_home() -> None:
    zone = _zone()
    zone["hermes_home"] = "/var/lib/station/zones/another/hermes"
    with pytest.raises(ValidationError):
        build_gateway_argv(zone, "start", runtime_uid=12001, hermes_binary=Path("/usr/local/bin/hermes"))


@pytest.mark.parametrize("action", GATEWAY_ACTIONS)
def test_all_actions_explicitly_route_to_accepted_director(action):
    argv = build_gateway_argv(_zone(), action, runtime_uid=12001,
                              hermes_binary=Path("/usr/local/bin/hermes"), director_profile="forge")
    command = argv[argv.index("/usr/local/bin/hermes"):]
    assert command == ["/usr/local/bin/hermes", "--profile", "forge", *GATEWAY_ACTIONS[action]]
    assert "HERMES_HOME=/var/lib/station/zones/organization-alpha-dev/hermes" in argv
    assert "--all" not in argv


@pytest.mark.parametrize("profile", ["", "../other", "/tmp/other", "-p", "bad name", "FORGE"])
def test_director_selector_rejects_arbitrary_profile_paths_or_options(profile):
    with pytest.raises(ValidationError):
        build_gateway_argv(_zone(), "setup", runtime_uid=12001,
                           hermes_binary=Path("/usr/local/bin/hermes"), director_profile=profile)
    with pytest.raises(ValidationError):
        gateway_service_name(profile)


def test_native_service_names_and_model_setup():
    assert gateway_service_name() == "hermes-gateway.service"
    assert gateway_service_name("default") == "hermes-gateway.service"
    assert gateway_service_name("forge") == "hermes-gateway-forge.service"
    assert GATEWAY_ACTIONS["configure"] == ("setup", "model")


@pytest.mark.parametrize("profile,instance", [(None, None), ("atlas", None), ("i-1234-atlas", "engineering")])
def test_model_enrollment_never_selects_native_full_or_gateway_setup(profile, instance):
    argv = build_gateway_argv(_zone(), "configure", runtime_uid=12001,
                              hermes_binary=Path("/usr/local/bin/hermes"),
                              director_profile=profile, instance_id=instance)
    assert argv[-4:] == ["--profile", profile or "default", "setup", "model"]
    assert "gateway" not in argv and "--quick" not in argv and "--reset" not in argv


def test_discord_briefing_states_manual_admission_and_service_gates():
    result = platform_setup_guidance("Discord")
    assert isinstance(result, tuple)
    text = "\n".join(result)
    for phrase in ("not a filter", "decline native", "masked prompts", "numeric human IDs",
                   "home channel is for notifications, not authorization", "not permanent Administrator",
                   "neither Linux sudo", "negative tests"):
        assert phrase in text
    assert "https://discord.com/developers/applications" in text


@pytest.mark.parametrize("platform", [None, "telegram", "slack", "Teams"])
def test_generic_platform_guidance_does_not_claim_discord_or_automatic_provisioning(platform):
    text = "\n".join(platform_setup_guidance(platform))
    assert "native Hermes platform picker" in text
    assert "Discord:" not in text
    assert "Configuration is not acceptance" in text


def test_guidance_rejects_unknown_platform():
    with pytest.raises(ValidationError):
        platform_setup_guidance("untrusted-platform")


def test_bootstrap_completion_distinguishes_operator_from_first_station_bot():
    root = Path(__file__).resolve().parents[2]
    completion = (root / "bootstrap.sh").read_text().split("AGK Station bootstrap complete.", 1)[1]
    assert "Operator CLI logins (these do not authenticate a Zone or OS instance)" in completion
    assert "hermes setup model" in completion
    assert "\n  hermes setup\n" not in completion
    assert "\n  hermes gateway setup" not in completion
    assert "station platform configure --zone discord-bootstrap" in completion
    assert "station platform setup --zone discord-bootstrap --platform discord" in completion
    assert "Decline native service install/start/restart offers" in completion
    assert "never copy them to Atlas" in completion


def test_headless_install_explicitly_disables_immediate_start_but_enables_persistence():
    argv = build_gateway_argv(_zone(), "install", runtime_uid=12001,
                              hermes_binary=Path("/usr/local/bin/hermes"))
    assert argv[-6:] == ["--profile", "default", "gateway", "install", "--no-start-now", "--start-on-login"]
    assert "--start-now" not in argv
    start = build_gateway_argv(_zone(), "start", runtime_uid=12001,
                               hermes_binary=Path("/usr/local/bin/hermes"))
    assert start[-2:] == ["gateway", "start"]
