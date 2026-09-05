#!/usr/bin/env python3
"""Alert once when an AGK profile bot stays unavailable for ten minutes.

Routine gateway stop/start messages are disabled in Hermes configuration.
This watchdog is deliberately out-of-process, so it can still notify Discord
when the profile gateway itself is down.  Recovery is silent.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


DEFAULT_STATE = Path("/var/lib/agk-terminal/gateway-watchdog.json")
DEFAULT_HOME_ROOT = Path("/home")
DEFAULT_NOTIFIER_HOME = Path("/home/operator/.hermes")
DEFAULT_THRESHOLD = 600
DISCORD_API = "https://discord.com/api/v10"


@dataclass(frozen=True)
class ProfileBot:
    name: str
    hermes_home: Path
    required_platforms: tuple[str, ...]


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a YAML object")
    return data


def discover_profile_bots(home_root: Path = DEFAULT_HOME_ROOT) -> list[ProfileBot]:
    candidates = list(home_root.glob("*/.hermes/config.yaml"))
    candidates.extend(home_root.glob("*/.hermes/profiles/*/config.yaml"))
    profiles: list[ProfileBot] = []
    for config_path in sorted(candidates):
        try:
            hermes_home = config_path.parent.resolve()
            relative = hermes_home.relative_to(home_root.resolve())
            parts = relative.parts
            if (len(parts) not in {2, 4} or parts[1] != ".hermes"
                    or (len(parts) == 4 and parts[2] != "profiles")):
                continue
            config = _read_yaml(config_path)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        platforms = config.get("platforms") or {}
        if not isinstance(platforms, dict):
            continue
        required = tuple(
            name
            for name in ("discord", "telegram")
            if isinstance(platforms.get(name), dict)
            and bool(platforms[name].get("enabled"))
        )
        if not required:
            continue
        # A named Hermes profile may intentionally inherit the parent bot
        # configuration while never owning a gateway process of its own.  Do
        # not report that shadow profile as a separate outage. A gateway
        # becomes monitorable after its first start writes gateway_state.json,
        # or when provisioning explicitly marks it as expected.
        discord_extra = (
            platforms.get("discord", {}).get("extra", {})
            if isinstance(platforms.get("discord"), dict)
            else {}
        )
        explicitly_expected = bool(
            isinstance(discord_extra, dict)
            and discord_extra.get("offline_alert_enabled") is True
        )
        if not (hermes_home / "gateway_state.json").exists() and not explicitly_expected:
            continue
        linux_user = parts[0]
        profile_name = parts[3] if len(parts) == 4 else None
        name = f"{linux_user}/{profile_name}" if profile_name else linux_user
        profiles.append(ProfileBot(name, hermes_home, required))
    return profiles


def _pid_is_gateway(pid: Any) -> bool:
    try:
        numeric = int(pid)
    except (OverflowError, TypeError, ValueError):
        return False
    if numeric <= 1:
        return False
    try:
        command = Path(f"/proc/{numeric}/cmdline").read_bytes().replace(b"\0", b" ")
    except OSError:
        return False
    return b"gateway" in command and b"run" in command and b"hermes" in command


def profile_health(profile: ProfileBot) -> tuple[bool, str]:
    state_path = profile.hermes_home / "gateway_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "gateway state unavailable"
    if not isinstance(state, dict):
        return False, "gateway state invalid"
    if state.get("gateway_state") != "running" or not _pid_is_gateway(state.get("pid")):
        return False, "gateway process unavailable"
    platforms = state.get("platforms") or {}
    if not isinstance(platforms, dict):
        return False, "gateway platform state invalid"
    for platform in profile.required_platforms:
        platform_state = platforms.get(platform) or {}
        if (not isinstance(platform_state, dict)
                or platform_state.get("state") != "connected" or platform_state.get("error_code")):
            return False, f"{platform} disconnected"
    return True, "connected"


def _env_value(path: Path, key: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        current, value = stripped.split("=", 1)
        if current.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value or None
    return None


def _discord_json(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{DISCORD_API}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "AGK-Gateway-Watchdog/1",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def _normalized_channel_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(character for character in text if not unicodedata.combining(character))


def _discord_general_target(hermes_home: Path, token: str) -> str | None:
    config = _read_yaml(hermes_home / "config.yaml")
    discord = ((config.get("platforms") or {}).get("discord") or {})
    extra = discord.get("extra") or {}
    explicit = str(extra.get("offline_alert_channel_id") or "").strip()
    if explicit.isdigit():
        return explicit
    home = discord.get("home_channel") or {}
    guild_id = str(home.get("scope_id") or home.get("guild_id") or "").strip()
    if not guild_id.isdigit():
        home_channel = str(home.get("chat_id") or "").strip()
        if home_channel.isdigit():
            channel = _discord_json(token, "GET", f"/channels/{home_channel}") or {}
            guild_id = str(channel.get("guild_id") or "")
    if not guild_id.isdigit():
        return None
    channels = _discord_json(token, "GET", f"/guilds/{guild_id}/channels") or []
    matches = [
        channel
        for channel in channels
        if channel.get("type") in {0, 5}
        and _normalized_channel_name(channel.get("name")) == "general"
        and str(channel.get("id") or "").isdigit()
    ]
    matches.sort(key=lambda channel: int(channel.get("position") or 0))
    return str(matches[0]["id"]) if matches else None


def notify_general(notifier_home: Path, message: str) -> bool:
    token = _env_value(notifier_home / ".env", "DISCORD_BOT_TOKEN")
    if not token:
        return False
    try:
        channel_id = _discord_general_target(notifier_home, token)
        if not channel_id:
            return False
        result = _discord_json(
            token,
            "POST",
            f"/channels/{channel_id}/messages",
            {"content": message, "allowed_mentions": {"parse": []}},
        )
        return isinstance(result, dict) and bool(result.get("id"))
    except (OSError, ValueError, yaml.YAMLError, urllib.error.URLError):
        return False


def evaluate_profile(
    record: dict[str, Any] | None,
    *,
    healthy: bool,
    reason: str,
    now: float,
    threshold: int,
    send: Callable[[], bool],
) -> dict[str, Any] | None:
    """Advance one outage state. Healthy recovery intentionally returns None."""

    if healthy:
        return None
    current = dict(record) if isinstance(record, dict) else {}
    try:
        down_since = float(current.get("down_since", now))
    except (OverflowError, TypeError, ValueError):
        down_since = float("nan")
    if not math.isfinite(down_since) or down_since < 0 or down_since > now:
        # Corrupt state cannot create an immediate alert or suppress one
        # indefinitely. Restart the grace period without sending a message.
        current = {}
        down_since = now
    current["down_since"] = down_since
    current["reason"] = reason
    current["alerted"] = current.get("alerted") is True
    if not current["alerted"] and now - down_since >= threshold:
        if send():
            current["alerted"] = True
            current["alerted_at"] = now
    return current


def _load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def run_once(
    *,
    state_path: Path = DEFAULT_STATE,
    home_root: Path = DEFAULT_HOME_ROOT,
    notifier_home: Path = DEFAULT_NOTIFIER_HOME,
    threshold: int = DEFAULT_THRESHOLD,
    now: float | None = None,
) -> dict[str, Any]:
    timestamp = time.time() if now is None else float(now)
    previous = _load_state(state_path)
    next_state: dict[str, Any] = {}
    for profile in discover_profile_bots(home_root):
        healthy, reason = profile_health(profile)

        def send(profile: ProfileBot = profile, reason: str = reason) -> bool:
            minutes = max(1, threshold // 60)
            return notify_general(
                notifier_home,
                f"🔴 AGK · `{profile.name}` est hors ligne depuis {minutes} minutes ({reason}).",
            )

        record = evaluate_profile(
            previous.get(str(profile.hermes_home)),
            healthy=healthy,
            reason=reason,
            now=timestamp,
            threshold=threshold,
            send=send,
        )
        if record is not None:
            next_state[str(profile.hermes_home)] = record
    _save_state(state_path, next_state)
    return next_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--home-root", type=Path, default=DEFAULT_HOME_ROOT)
    parser.add_argument("--notifier-home", type=Path, default=DEFAULT_NOTIFIER_HOME)
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()
    run_once(
        state_path=args.state,
        home_root=args.home_root,
        notifier_home=args.notifier_home,
        threshold=max(60, args.threshold),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
