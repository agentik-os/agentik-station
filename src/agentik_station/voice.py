"""Explicit, one-profile native STT enrollment; never an OS bundle migration.

Hermes owns plugin scanning, installation, enablement and configuration writes.
This module only validates Station scope and invokes those native commands as
the Zone identity. Failures may leave a disabled/partly configured plugin: this
is not a transaction, and conflicting existing installations are never replaced.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import re
import stat
import subprocess

from . import os_instances, os_lifecycle as lifecycle
from .errors import SecurityError, ValidationError
from .hermes_platforms import build_gateway_argv
from .identifiers import validate_identifier
from .installer import install_lock
from .models import new_operation_id
from .native_process import run_bounded_native
from .paths import LayoutPaths

PLUGIN = "station-voice"
PROVIDER = "station-openai-parakeet"
MODEL = "gpt-transcribe"
SOURCE = "https://github.com/agentik-os/agentik-station.git#runtime/hermes-station/hermes/plugins/station-voice"
REPAIR = (
    "Inspect this exact profile's native plugin/configuration and recorded step outcomes; "
    "do not force reinstall or replace its OS distribution. Rerun instance verification "
    "after reviewed repair, then perform provider/chat acceptance."
)
_MISSING = object()


def _effective_profile(prefix, profile_root):
    """Confirm native dotenv/startup resolution still selects this profile.

    The Unix Zone remains the hard boundary; this readback prevents an existing
    native HOME/HERMES_HOME override from silently redirecting our config writes.
    No credential file is inspected and no override is stripped or rewritten.
    """
    reply = run_bounded_native(prefix + ["config", "path"], timeout=60, capture=True)
    expected = str(profile_root / "config.yaml").encode("utf-8") + b"\n"
    if reply.returncode != 0 or reply.stderr or reply.stdout != expected:
        raise SecurityError("Native configuration path differs from the selected instance profile")


def _config_value(prefix, key):
    """Read one native effective key privately; never return subprocess output."""
    reply = run_bounded_native(prefix + ["config", "get", key, "--json"], timeout=60, capture=True)
    out, err = reply.stdout or b"", reply.stderr or b""
    if reply.returncode == 1 and not out and err == f"Config key not set: {key}\n".encode():
        return _MISSING
    if reply.returncode != 0 or err or len(out) > 65536:
        raise ValidationError("Native effective voice policy readback failed")
    try:
        return json.loads(out, object_pairs_hook=lifecycle._unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise ValidationError("Native effective voice policy readback is invalid") from None


def _effective_value(prefix, key, default=_MISSING):
    # Hermes config get intentionally prefers literal dotted mapping keys;
    # its scanner uses nested cfg_get instead. Reject EVERY possible collapsed
    # segment so a managed dotted literal cannot spoof a different nested value.
    parts = key.split(".")
    for start in range(len(parts) - 1):
        for stop in range(start + 2, len(parts) + 1):
            literal = "\\.".join(parts[start:stop])
            probe = ".".join([*parts[:start], literal])
            if _config_value(prefix, probe) is not _MISSING:
                raise ValidationError("Ambiguous literal dotted native policy keys require explicit repair")
    value = _config_value(prefix, key)
    return default if value is _MISSING else value


def _effective_policy(prefix, *, selected=False):
    """Prove effective policy, including managed overlays and dotenv routing."""
    if _effective_value(prefix, "plugins.scan_on_install", True) is not True:
        raise SecurityError("Effective native plugin scanning must remain enabled")
    if _effective_value(prefix, "stt.enabled", True) is not True:
        raise ValidationError("Effective STT is disabled; enrollment will not enable it")
    provider = _effective_value(prefix, "stt.provider")
    accepted = {PROVIDER} if selected else {"openai", PROVIDER}
    if not isinstance(provider, str) or provider not in accepted:
        raise ValidationError("Effective native STT selection differs from the requested profile policy")
    if _effective_value(prefix, f"stt.providers.{PROVIDER}") is not _MISSING:
        raise ValidationError("Effective custom provider declaration conflicts with Station voice")
    model = _effective_value(prefix, f"stt.{PROVIDER}.model", MODEL if not selected else _MISSING)
    if model != MODEL:
        raise ValidationError("Effective Station voice model differs from its reviewed selection")
    if selected:
        enabled = _effective_value(prefix, "plugins.enabled", [])
        disabled = _effective_value(prefix, "plugins.disabled", [])
        if (not isinstance(enabled, list) or not isinstance(disabled, list)
                or not all(isinstance(value, str) for value in [*enabled, *disabled])
                or PLUGIN not in enabled or PLUGIN in disabled
                or _effective_value(prefix, f"plugins.entries.{PLUGIN}.allow_tool_override") is not False):
            raise ValidationError("Effective native voice plugin selection is incomplete")


def _scope(paths, zone, instance_id, role):
    instance_id = validate_identifier(instance_id, "OS instance id")
    role = validate_identifier(role, "explicit OS team role")
    record = os_instances.load_os_instance_record(
        paths, zone=zone, instance_id=instance_id, require_configured=True,
    )
    profile = record["role_profile_map"].get(role)
    if profile is None:
        raise ValidationError("Requested role is not in this instance's trusted Hermes team")
    context = os_instances._runtime_context(
        paths, zone, record, lifecycle._context(paths, zone),
    )
    profile_root = context["hermes_home"] / "profiles" / profile
    with lifecycle._directory(profile_root, uid=context["uid"], trusted_root=context["hermes_home"]) as fd:
        if os.fstat(fd).st_gid != context["gid"]:
            raise SecurityError("Native profile group differs from its Zone identity")
    data = lifecycle._read_bytes(
        profile_root / "config.yaml", uid=context["uid"], immutable=True,
        trusted_root=context["hermes_home"],
    )
    return record, context, profile, profile_root, lifecycle._yaml(data)


def _voice_policy(config):
    plugins, stt = config.get("plugins", {}), config.get("stt", {})
    if not isinstance(plugins, dict) or not isinstance(stt, dict):
        raise ValidationError("Native plugin and STT configuration must be mappings")
    if plugins.get("scan_on_install", True) is not True:
        raise SecurityError("Native plugin scan_on_install must remain enabled")
    for key in ("enabled", "disabled"):
        values = plugins.get(key, [])
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValidationError("Native plugin selection must be a list of names")
    entries = plugins.get("entries", {})
    if not isinstance(entries, dict) or any(not isinstance(value, dict) for value in entries.values()):
        raise ValidationError("Native plugin policies must be mappings")
    if stt.get("enabled", True) is not True:
        raise ValidationError("STT is disabled; voice enrollment will not enable it")
    if not isinstance(stt.get("provider"), str) or stt["provider"] not in {"openai", PROVIDER}:
        raise ValidationError("Voice enrollment only accepts an explicit OpenAI or Station voice selection")
    providers = stt.get("providers", {})
    if not isinstance(providers, dict) or PROVIDER in providers:
        raise ValidationError("A custom STT provider declaration conflicts with Station voice")
    settings = stt.get(PROVIDER, {})
    if not isinstance(settings, dict) or settings.get("model", MODEL) != MODEL:
        raise ValidationError("Existing Station voice model differs; preserve it for explicit review")


def _absent_plugin(profile_root, context, config):
    plugins = profile_root / "plugins"
    with lifecycle._directory(plugins, uid=context["uid"], trusted_root=context["hermes_home"]) as fd:
        if os.fstat(fd).st_gid != context["gid"]:
            raise SecurityError("Native plugins directory group differs from its Zone")
        try:
            os.stat(PLUGIN, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValidationError("Station voice plugin already exists; no forced replacement or automatic adoption")
    try:
        metadata = lifecycle.read_runtime_json(
            plugins / ".install-metadata.json", uid=context["uid"], immutable=True,
            trusted_root=context["hermes_home"],
        )
    except FileNotFoundError:
        metadata = {}
    if PLUGIN in metadata:
        raise ValidationError("Station voice has existing native source metadata; explicit repair is required")
    policy = config["plugins"]
    for key in ("enabled", "disabled"):
        values = policy.get(key, [])
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValidationError("Native plugin selection must be a list of names")
        if PLUGIN in values:
            raise ValidationError("Station voice has an existing plugin selection; explicit repair is required")
    entries = policy.get("entries", {})
    if not isinstance(entries, dict) or PLUGIN in entries:
        raise ValidationError("Station voice has an existing plugin policy; explicit repair is required")


def _binary(value):
    if not isinstance(value, (str, Path)) or not str(value) or "\x00" in str(value):
        raise ValidationError("Native executable must be an absolute path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValidationError("Native executable must be absolute without traversal")
    return path


def prepare_voice_enrollment(paths: LayoutPaths, *, zone: dict, instance_id: str,
                             role: str, revision: str, hermes_binary: str | Path,
                             runuser_binary: str | Path) -> dict:
    """Pure bounded reads and a non-secret command plan for exactly one role."""
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValidationError("Voice plugin revision must be an exact lowercase 40-character Git SHA")
    record, context, profile, profile_root, config = _scope(paths, zone, instance_id, role)
    _voice_policy(config)
    _absent_plugin(profile_root, context, config)
    # Reuse the native gateway identity builder, removing only its final action.
    prefix = build_gateway_argv(
        zone, "doctor", runtime_uid=context["uid"], hermes_binary=_binary(hermes_binary),
        runuser_binary=_binary(runuser_binary), director_profile=profile, instance_id=instance_id,
    )[:-1]
    commands = [
        ("install", ["plugins", "install", SOURCE, "--ref", revision, "--no-enable"]),
        ("doctor", ["plugins", "doctor", "--ci", PLUGIN]),
        ("enable", ["plugins", "enable", "--no-allow-tool-override", PLUGIN]),
        ("model", ["config", "set", f"stt.{PROVIDER}.model", MODEL]),
        ("select", ["config", "set", "stt.provider", PROVIDER]),
    ]
    return {
        "schema_version": 1, "state": "PREPARED", "operational": False,
        "zone_id": zone["id"], "instance_id": instance_id, "role": role,
        "profile": profile, "os_id": record["os_id"], "os_version": record["os_version"],
        "hermes_home": str(context["hermes_home"]), "profile_root": str(profile_root),
        "source": SOURCE, "revision": revision, "provider": PROVIDER,
        "scope": "All native STT calls in this selected profile; other profiles are unchanged.",
        "effective_policy": "Native scoped readback is required during execution; this pure plan reads local authority only.",
        "steps": [{"id": name, "argv": prefix + args} for name, args in commands],
        "next_repair_action": REPAIR,
    }


def _installed_source(profile_root, context, revision):
    metadata = lifecycle.read_runtime_json(
        profile_root / "plugins/.install-metadata.json", uid=context["uid"], immutable=True,
        trusted_root=context["hermes_home"],
    )
    if metadata.get(PLUGIN) != {"source": SOURCE, "revision": revision, "pinned": True}:
        raise ValidationError("Native Station voice source/revision readback differs from the selected pin")
    with lifecycle._directory(profile_root / "plugins" / PLUGIN,
                              uid=context["uid"], trusted_root=context["hermes_home"]) as fd:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_gid != context["gid"]:
            raise SecurityError("Installed native voice plugin is not owned by its Zone")


def enroll_voice_profile(paths: LayoutPaths, *, zone: dict, instance_id: str,
                         role: str, revision: str, hermes_binary: str | Path,
                         runuser_binary: str | Path) -> dict:
    """Execute native commands under a Station lock, reporting partial outcomes.

    No provider calls, gateway restart, secret copy, global configuration write,
    forced reinstall or security-scan override is performed.
    """
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("Scoped voice enrollment requires root to select the Zone identity")
    with install_lock(paths, new_operation_id()):
        plan = prepare_voice_enrollment(
            paths, zone=zone, instance_id=instance_id, role=role, revision=revision,
            hermes_binary=hermes_binary, runuser_binary=runuser_binary,
        )
        result = {**plan, "state": "INCOMPLETE", "steps": []}
        prefix = plan["steps"][0]["argv"][:-6]
        for step in plan["steps"]:
            # Reread trusted roots/config between native mutations. The native
            # installer owns its target publication, and refuses existing paths.
            try:
                _, context, profile, profile_root, config = _scope(paths, zone, instance_id, role)
                _voice_policy(config)
                if profile != plan["profile"] or str(profile_root) != plan["profile_root"]:
                    raise SecurityError("Selected native profile changed during enrollment")
                if step["id"] == "install":
                    _absent_plugin(profile_root, context, config)
                else:
                    _installed_source(profile_root, context, revision)
                _effective_profile(prefix, profile_root)
                _effective_policy(prefix)
            except (OSError, SecurityError, ValidationError, subprocess.SubprocessError):
                result["steps"].append({"id": step["id"], "status": "BLOCKED", "returncode": None})
                return result
            try:
                code = run_bounded_native(step["argv"], timeout=300, capture=False).returncode
            except subprocess.TimeoutExpired:
                code = 124
            except OSError:
                code = 127
            except subprocess.SubprocessError:
                code = 125
            result["steps"].append({"id": step["id"], "status": "SUCCEEDED" if code == 0 else "FAILED",
                                    "returncode": code})
            if code != 0:
                return result
        try:
            _, context, _, profile_root, config = _scope(paths, zone, instance_id, role)
            _voice_policy(config)
            _installed_source(profile_root, context, revision)
            _effective_profile(prefix, profile_root)
            _effective_policy(prefix, selected=True)
            plugins = config["plugins"]
            if (config["stt"].get("provider") != PROVIDER
                    or config["stt"].get(PROVIDER, {}).get("model") != MODEL
                    or PLUGIN not in plugins.get("enabled", [])
                    or PLUGIN in plugins.get("disabled", [])
                    or plugins.get("entries", {}).get(PLUGIN, {}).get("allow_tool_override") is not False):
                raise ValidationError("Native voice configuration readback is incomplete")
        except (OSError, SecurityError, ValidationError, subprocess.SubprocessError):
            result["steps"].append({"id": "readback", "status": "BLOCKED", "returncode": None})
            return result
        result["state"] = "CONFIGURED"
        result["steps"].append({"id": "readback", "status": "SUCCEEDED", "returncode": None})
        result["next_repair_action"] = "Rerun station os instance verify, then perform scoped live provider/chat acceptance."
        return result
