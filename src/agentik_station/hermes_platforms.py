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
    # Reuse the same trusted identity/profile selection for an interactive OS CLI.
    # This does not install or start any messaging gateway.
    "chat": ("chat",),
    # The full native setup wizard can install/start the gateway, even when
    # messaging is skipped. Keep provider enrollment in its native model section.
    "configure": ("setup", "model"),
    "setup": ("gateway", "setup"),
    # The pinned Hermes CLI otherwise starts immediately in a headless context.
    # Keep Station's explicit install/start lifecycle, while enabling boot login.
    "install": ("gateway", "install", "--no-start-now", "--start-on-login"),
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


def platform_setup_guidance(platform: str | None) -> tuple[str, ...]:
    """Nonsecret briefing, not a replacement wizard or an enforced service gate."""
    selected = normalize_platform(platform)
    common = (
        "This opens the native Hermes platform picker; --platform records intent, not a filter.",
        "Keep configure -> verify -> install -> start: decline native install/start/restart offers, including at wizard entry.",
        "Enter credentials only in the native masked prompts; preserve existing credentials in this exact Zone/profile.",
        "Configuration is not acceptance: verify the intended bot, human/channel restrictions and live send/receive before declaring it ready.",
    )
    if selected != "discord":
        return common
    return common + (
        "Discord: the human owner creates/invites the app at https://discord.com/developers/applications; use least privilege, not permanent Administrator.",
        "Enable Message Content Intent. Use explicit numeric human IDs; Members Intent is needed only for username or role admission at the pinned Hermes version.",
        "Set an explicit channel allowlist separately: the home channel is for notifications, not authorization. Do not use wildcard/allow-all admission or public bot-to-bot replies.",
        "A bot token grants neither Linux sudo nor another Zone's accounts. Follow docs/dependencies/HERMES_PLATFORMS.md for channel ACLs and negative tests.",
    )


def build_gateway_argv(
    zone: dict[str, Any],
    action: str,
    *,
    runtime_uid: int,
    hermes_binary: Path,
    runuser_binary: Path = Path("/usr/sbin/runuser"),
    director_profile: str | None = None,
    instance_id: str | None = None,
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
    if not state_root.is_absolute() or ".." in state_root.parts or hermes_home != expected_home:
        raise ValidationError("Zone Hermes home must be the dedicated <state_root>/hermes directory")
    if instance_id is not None:
        instance_id = validate_identifier(instance_id, "OS instance id")
        if director_profile in (None, "default"):
            raise ValidationError("An OS instance requires its explicit native Director profile")
        hermes_home = state_root / "os-instances" / instance_id / "hermes"
    if not hermes_binary.is_absolute() or not runuser_binary.is_absolute():
        raise ValidationError("Hermes and runuser binaries must use absolute paths")
    if runtime_uid < 0:
        raise ValidationError("Zone runtime uid must be non-negative")
    profile = validate_identifier(director_profile, "OS Director profile") if director_profile is not None else "default"
    runtime_dir = Path("/run/user") / str(runtime_uid)
    interactive = action in {"chat", "configure", "setup"}
    return [
        str(runuser_binary),
        # Never share a privileged caller's controlling terminal with Zone code.
        # util-linux runuser(1) documents --pty for interactive UID boundaries.
        *(["--pty"] if interactive else []),
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
        *(["TERM=xterm-256color"] if interactive else []),
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
