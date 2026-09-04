from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .errors import SecurityError, ValidationError
from .identifiers import validate_identifier
from .os_contract import doctor_os_source


def _require_clean_output(output: Path) -> None:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise SecurityError(f"Compiler output must not already exist: {output}")
    if output.parent.exists() and output.parent.is_symlink():
        raise SecurityError(f"Compiler output parent must not be a symlink: {output.parent}")


def _profile_distribution(
    source: Path,
    destination: Path,
    *,
    os_id: str,
    os_version: str,
    profile_id: str,
    profile_text: str,
    station_rules: str,
    project_root: Path,
) -> None:
    destination.mkdir(parents=True, mode=0o750)
    # Generated distribution duplication is intentional and disposable; canonical source remains under os/.
    if (source / "skills").is_dir():
        shutil.copytree(source / "skills", destination / "skills", symlinks=False)
    if (source / "research_fabric").is_dir():
        shutil.copytree(source / "research_fabric", destination / "research_fabric", symlinks=False)

    distribution = (
        f'name: {profile_id}\n'
        f'version: "{os_version}"\n'
        f'description: "{os_id} profile {profile_id}"\n'
        'hermes_requires: ">=0.21.0"\n'
        'author: "AGK / Agentik"\n'
        'distribution_owned:\n'
        '  - SOUL.md\n'
        '  - STATION_RULES.md\n'
        '  - config.yaml\n'
        '  - skills/\n'
        '  - distribution.yaml\n'
    )
    config_template = (source / "hermes/config.template.yaml").read_text(encoding="utf-8")
    config = config_template.replace("__PROJECT_ROOT__", str(project_root))
    # Strict Zone/profile tool-home isolation is a Station invariant.
    if "home_mode:" not in config:
        config += "\nterminal:\n  home_mode: profile\n"
    elif "home_mode: profile" not in config:
        config = config.replace("terminal:\n", "terminal:\n  home_mode: profile\n", 1)

    (destination / "distribution.yaml").write_text(distribution, encoding="utf-8")
    (destination / "config.yaml").write_text(config, encoding="utf-8")
    soul = (
        profile_text.rstrip()
        + "\n\n## Station universal agent rules\n\n"
        + "The following rules are mandatory for this profile and every delegated executor.\n\n"
        + station_rules.strip()
        + "\n"
    )
    (destination / "SOUL.md").write_text(soul, encoding="utf-8")
    (destination / "STATION_RULES.md").write_text(station_rules.rstrip() + "\n", encoding="utf-8")
    (destination / "COMMANDS.yaml").write_text(
        (source / "discord/COMMANDS.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for path in destination.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o640)
        elif path.is_dir():
            os.chmod(path, 0o750)


def compile_os_to_hermes(source: Path, output: Path, *, project_root: Path) -> dict[str, Any]:
    source = Path(source)
    result = doctor_os_source(source)
    if not result.ok:
        raise ValidationError(f"OS source Doctor failed for {source}: {result.issues[:3]}")
    _require_clean_output(output)

    rules_path = source.parents[1] / "rules" / "STATION_AGENT_RULES.md"
    if rules_path.is_symlink() or not rules_path.is_file():
        raise ValidationError(f"Canonical Station agent rules are missing or unsafe: {rules_path}")
    station_rules = rules_path.read_text(encoding="utf-8")

    contract = json.loads((source / "CONTRACT.json").read_text(encoding="utf-8"))
    os_id = validate_identifier(str(contract["os_id"]), "OS id")
    os_version = str(contract["version"])
    director = validate_identifier(str(contract["nano_director"]), "Nano Director profile")
    workers = [validate_identifier(str(value), "NanoTeam profile") for value in contract["nanoteam"]]
    profiles = [director, *[value for value in workers if value != director]]

    project_root = Path(project_root).resolve(strict=False)
    if not project_root.is_absolute():
        raise ValidationError("project_root must resolve to an absolute path")

    output.mkdir(parents=True, mode=0o750)
    profiles_root = output / "profiles"
    profiles_root.mkdir()

    for profile_id in profiles:
        if profile_id == director:
            profile_text = (source / "director/PROFILE.md").read_text(encoding="utf-8")
        else:
            profile_path = source / "profiles" / profile_id / "PROFILE.md"
            if not profile_path.is_file() or profile_path.is_symlink():
                raise ValidationError(f"Missing persistent profile source: {profile_path}")
            profile_text = profile_path.read_text(encoding="utf-8")
        _profile_distribution(
            source,
            profiles_root / profile_id,
            os_id=os_id,
            os_version=os_version,
            profile_id=profile_id,
            profile_text=profile_text,
            station_rules=station_rules,
            project_root=project_root,
        )

    compiled = {
        "schema_version": 2,
        "os_id": os_id,
        "os_version": os_version,
        "nano_director": director,
        "profiles": profiles,
        "project_root": str(project_root),
        "source_contract": "AGK OS v2",
        "runtime_target": "Hermes Profile Distributions",
        "claim": "COMPILED_NOT_INSTALLED",
        "next_gate": "Install every profile into the target Zone HERMES_HOME, then run Hermes/plugin Doctor and fresh-session acceptance.",
    }
    (output / "COMPILED.json").write_text(json.dumps(compiled, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return compiled


def install_compiled_bundle(
    compiled_root: Path,
    *,
    hermes_home: Path,
    unix_user: str,
    hermes_binary: str,
    runuser_binary: str,
) -> dict[str, Any]:
    """Install a previously compiled bundle into one Zone-local HERMES_HOME.

    This performs local Hermes profile installation only. It does not configure
    provider secrets, Discord bot tokens, Composio accounts, or external readback.
    """
    compiled_root = Path(compiled_root)
    manifest_path = compiled_root / "COMPILED.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValidationError(f"Missing compiled bundle manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValidationError("Compiled bundle contains no profiles")
    hermes_home = Path(hermes_home)
    if hermes_home.is_symlink():
        raise SecurityError(f"Zone HERMES_HOME may not be a symlink: {hermes_home}")

    observations: list[dict[str, Any]] = []
    for raw_profile in profiles:
        profile = validate_identifier(str(raw_profile), "Hermes profile")
        distribution = compiled_root / "profiles" / profile
        argv = [
            runuser_binary,
            "--user",
            unix_user,
            "--",
            "/usr/bin/env",
            f"HERMES_HOME={hermes_home}",
            hermes_binary,
            "profile",
            "install",
            str(distribution),
            "--name",
            profile,
            "--yes",
        ]
        import subprocess
        completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=300)
        observations.append(
            {
                "profile": profile,
                "install_returncode": completed.returncode,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-8000:],
            }
        )
        if completed.returncode != 0:
            return {
                "schema_version": 1,
                "os_id": manifest.get("os_id"),
                "state": "DEGRADED",
                "profiles": observations,
                "next_repair_action": f"Repair Hermes installation for profile {profile} and rerun the OS install gate.",
            }

    return {
        "schema_version": 1,
        "os_id": manifest.get("os_id"),
        "state": "CONFIGURED",
        "profiles": observations,
        "verified": False,
        "operational": False,
        "next_repair_action": "Run Hermes profile Doctor/plugin Doctor, configure credentials and dedicated Discord bot, then fresh-session acceptance.",
    }
