from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ValidationError
from .identifiers import validate_identifier


SUPPORTED_PLATFORMS = (
    "telegram",
    "discord",
    "slack",
    "whatsapp",
    "signal",
    "sms",
    "email",
    "home-assistant",
    "mattermost",
    "matrix",
    "dingtalk",
    "feishu-lark",
    "wecom",
    "weixin",
    "bluebubbles-imessage",
    "qq",
    "yuanbao",
    "microsoft-teams",
    "line",
    "ntfy",
    "browser",
)

GATEWAY_ACTIONS = {
    "configure": ("setup",),
    "setup": ("gateway", "setup"),
    "install": ("gateway", "install"),
    "start": ("gateway", "start"),
    "restart": ("gateway", "restart"),
    "status": ("gateway", "status"),
    "doctor": ("doctor",),
}


def normalize_platform(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().lower().replace("_", "-").replace("/", "-")
    aliases = {
        "teams": "microsoft-teams",
        "msteams": "microsoft-teams",
        "homeassistant": "home-assistant",
        "imessage": "bluebubbles-imessage",
        "lark": "feishu-lark",
        "feishu": "feishu-lark",
    }
    candidate = aliases.get(candidate, candidate)
    if candidate not in SUPPORTED_PLATFORMS:
        raise ValidationError(
            f"Unsupported Hermes platform {value!r}; choose one of: {', '.join(SUPPORTED_PLATFORMS)}"
        )
    return candidate


def build_gateway_argv(
    zone: dict[str, Any],
    action: str,
    *,
    runtime_uid: int,
    hermes_binary: Path,
    runuser_binary: Path = Path("/usr/sbin/runuser"),
    director_profile: str | None = None,
) -> list[str]:
    """Build a native command; callers must resolve Directors from the OS ledger.

    An explicit default selector also prevents Hermes' sticky ``active_profile``
    from silently routing a legacy Zone-level action to another OS.
    """
    if action not in GATEWAY_ACTIONS:
        raise ValidationError(f"Unsupported Hermes gateway action: {action}")
    unix_user = validate_identifier(str(zone.get("unix_user", "")), "Zone Unix user")
    state_root = Path(str(zone.get("state_root", "")))
    hermes_home = Path(str(zone.get("hermes_home", "")))
    expected_home = state_root / "hermes"
    if not state_root.is_absolute() or hermes_home != expected_home:
        raise ValidationError("Zone Hermes home must be the dedicated <state_root>/hermes directory")
    if not hermes_binary.is_absolute() or not runuser_binary.is_absolute():
        raise ValidationError("Hermes and runuser binaries must use absolute paths")
    if runtime_uid < 0:
        raise ValidationError("Zone runtime uid must be non-negative")
    profile = validate_identifier(director_profile, "OS Director profile") if director_profile is not None else "default"
    runtime_dir = Path("/run/user") / str(runtime_uid)
    return [
        str(runuser_binary),
        "--user",
        unix_user,
        "--",
        "/usr/bin/env",
        "-i",
        f"HOME={state_root / 'home'}",
        f"HERMES_HOME={hermes_home}",
        f"XDG_RUNTIME_DIR={runtime_dir}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir / 'bus'}",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        str(hermes_binary),
        "--profile",
        profile,
        *GATEWAY_ACTIONS[action],
    ]


def gateway_service_name(director_profile: str | None = None) -> str:
    """Pinned Hermes native systemd name for a canonical named profile."""
    profile = validate_identifier(director_profile, "OS Director profile") if director_profile is not None else "default"
    suffix = "" if profile == "default" else f"-{profile}"
    return f"hermes-gateway{suffix}.service"
