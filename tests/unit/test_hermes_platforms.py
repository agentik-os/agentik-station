from pathlib import Path

import pytest

from agentik_station.errors import ValidationError
from agentik_station.hermes_platforms import SUPPORTED_PLATFORMS, build_gateway_argv, normalize_platform


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
    assert "HERMES_HOME=/var/lib/station/zones/organization-alpha-dev/hermes" in argv
    assert "XDG_RUNTIME_DIR=/run/user/12001" in argv
    assert "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/12001/bus" in argv
    assert argv[-3:] == ["/usr/local/bin/hermes", "gateway", "status"]


def test_gateway_command_rejects_cross_zone_hermes_home() -> None:
    zone = _zone()
    zone["hermes_home"] = "/var/lib/station/zones/another/hermes"
    with pytest.raises(ValidationError):
        build_gateway_argv(zone, "start", runtime_uid=12001, hermes_binary=Path("/usr/local/bin/hermes"))
