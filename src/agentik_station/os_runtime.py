from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any

from .errors import SecurityError, ValidationError
from .identifiers import validate_identifier
from .os_contract import doctor_os_source
from .filesystem import SafeFS


def instance_profile_map(zone_id: str, instance_id: str, roles: list[str]) -> dict[str, str]:
    """Stable names within the Zone's single native user-service namespace.

    Package versions do not alter identity. The ledger additionally reserves the
    generated names: a truncated hash is not treated as collision-free authority.
    """
    validate_identifier(zone_id, "Zone id")
    validate_identifier(instance_id, "OS instance id")
    if not roles or len(set(roles)) != len(roles):
        raise ValidationError("An instance requires unique canonical roles")
    mapping = {}
    for role in roles:
        validate_identifier(role, "OS role")
        digest = hashlib.sha256(f"{zone_id}\0{instance_id}\0{role}".encode()).hexdigest()[:20]
        mapping[role] = validate_identifier(f"i-{digest}-{role[:25].rstrip('-')}", "instance profile")
    return mapping


def _map_role_references(value: Any, mapping: dict[str, str]) -> Any:
    """Rewrite exact structured role values, not arbitrary strings or prose."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_map_role_references(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _map_role_references(item, mapping) for key, item in value.items()}
    return value


def _instance_routing(destination: Path, mapping: dict[str, str], *, zone_id: str, instance_id: str,
                      workspace_root: Path, organization_id: str | None, allowed_project_ids: list[str],
                      voice_defaults: dict[str, Any]) -> None:
    """Compile routing bindings into the artifact; source OS roles remain canonical."""
    import yaml

    config_path = destination / "config.yaml"
    config = _unique_config_yaml(config_path.read_text(encoding="utf-8"))
    config_path.write_text(yaml.safe_dump(_merge_defaults(voice_defaults, config), sort_keys=False), encoding="utf-8")
    routing = {"schema_version": 1, "zone_id": zone_id, "instance_id": instance_id,
               "organization_id": organization_id, "allowed_project_ids": allowed_project_ids,
               "workspace_root": str(workspace_root), "role_profile_map": mapping,
               "project_scope": "DECLARED_NOT_UNIX_ENFORCED", "orchestrator": "hermes"}
    (destination / "INSTANCE.json").write_text(json.dumps(routing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = destination / "distribution.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["distribution_owned"].append("INSTANCE.json")
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    for name in ("COMMANDS.yaml", "STRIX_TEAM.json"):
        path = destination / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8")) if name.endswith(".json") else yaml.safe_load(path.read_text(encoding="utf-8"))
        data = _map_role_references(data, mapping)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n" if name.endswith(".json") else yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    # Add an explicit governing map to each prompt and rewrite only machine-form
    # selectors (backticked profile identifiers and native --profile/-p flags).
    # Ordinary role prose is a label and must not be globally string-replaced.
    for path in destination.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for role, profile in mapping.items():
            text = text.replace(f"`{role}`", f"`{profile}`")
            text = re.sub(r"(?P<flag>--profile\s+|-p\s+)" + re.escape(role) + r"(?=$|[\s`\"'])",
                          lambda match, value=profile: match.group("flag") + value, text)
        path.write_text(text, encoding="utf-8")
    soul = destination / "SOUL.md"
    header = ("# Instance-local native routing\n\n"
              f"OS instance: {instance_id}; Zone: {zone_id}. Native working directory: {workspace_root}.\n"
              "This instance owns OS coordination work, not its client's Project repositories.\n"
              "Canonical role names in source prose are labels only, never native profile selectors.\n"
              "For every delegation use the exact native profile below in this instance's HERMES_HOME; "
              "never route by a bare role, another instance, or the Zone default profile. "
              "If a required role is absent, stop rather than invent a worker. Hermes remains the sole orchestrator.\n\n"
              + "\n".join(f"- {role}: `{profile}`" for role, profile in mapping.items())
              + "\n\nDeclared allowed Projects: " + (", ".join(allowed_project_ids) or "none")
              + ". This declaration is not a Unix isolation boundary; same-Zone profiles share a UID. "
              "Resolve an allowed Project explicitly before Project work; never infer permission from this text.\n\n")
    soul.write_text(header + soul.read_text(encoding="utf-8"), encoding="utf-8")
    for path in destination.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o640)


def require_root_owned_directory_chain(path: Path) -> None:
    """Privileged publication must never traverse an agent-writable parent."""
    SafeFS._assert_existing_absolute_chain(path)
    for parent in (path, *path.parents):
        st = parent.stat(follow_symlinks=False)
        if st.st_uid != 0 or not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o022:
            raise SecurityError(f"Publication ancestor must be root-owned and not group/world writable: {parent}")


def _unique_config_yaml(template: str) -> dict[str, Any]:
    import yaml

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if not isinstance(key, str) or key in result:
                raise ValidationError("OS config contains a non-string or duplicate YAML key")
            result[key] = loader.construct_object(value_node, deep=True)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        config = yaml.load(template, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValidationError("OS config must be valid, unambiguous YAML") from exc
    if not isinstance(config, dict):
        raise ValidationError("OS config must be a mapping")
    return config


def _merge_defaults(defaults: dict, overrides: dict) -> dict:
    """Only source-defined overrides, never operator credentials or Zone config."""
    merged = dict(defaults)
    for key, value in overrides.items():
        merged[key] = _merge_defaults(merged[key], value) if isinstance(merged.get(key), dict) and isinstance(value, dict) else value
    return merged


def _instance_voice_defaults(source: Path) -> dict:
    path = source.parents[1] / "config/hermes/voice.default.yaml"
    SafeFS._assert_existing_absolute_chain(path.absolute().parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise ValidationError("Canonical instance voice defaults must be a bounded single-link regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(65537)
    finally:
        os.close(fd)
    if len(data) > 65536:
        raise ValidationError("Canonical instance voice defaults are oversized")
    defaults = _unique_config_yaml(data.decode("utf-8"))
    if set(defaults) != {"voice", "stt", "tts"} or any(not isinstance(value, dict) for value in defaults.values()):
        raise ValidationError("Canonical instance voice defaults must contain only voice, stt and tts mappings")
    return defaults


def _profile_config(template: str, profile_id: str, project_root: Path) -> dict[str, Any]:
    """Merge mappings, never append duplicate YAML sections or interpolate YAML source."""
    config = _unique_config_yaml(template)
    if "plugins" in config:
        raise ValidationError("OS config template plugins section is reserved for the distribution compiler")
    for section in ("profile", "terminal"):
        if not isinstance(config.setdefault(section, {}), dict):
            raise ValidationError(f"OS config {section} must be a mapping")
    config["profile"]["id"] = profile_id
    config["terminal"].update(cwd=str(project_root), home_mode="profile")
    config["plugins"] = {
        "enabled": ["station-web"],
        "entries": {"station-web": {"allow_tool_override": False}},
    }
    return config


def _require_clean_output(output: Path) -> None:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise SecurityError(f"Compiler output must not already exist: {output}")
    SafeFS._assert_existing_absolute_chain(output.absolute().parent)


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
        '  - research_fabric/\n'
        '  - COMMANDS.yaml\n'
        '  - plugins/station-web/\n'
        '  - distribution.yaml\n'
    )
    config_template = (source / "hermes/config.template.yaml").read_text(encoding="utf-8")
    config = _profile_config(config_template, profile_id, project_root)
    if os_id == "devops-os":
        security_target = destination / "plugins/station-strix"
        security_target.mkdir(parents=True)
        original = source.parents[1] / "components/agk-tui/hermes/plugins/agentik_os/strix_plugin.py"
        if original.is_symlink() or not original.is_file():
            raise ValidationError("Missing canonical Strix plugin")
        shutil.copyfile(original, security_target / "__init__.py")
        (security_target / "plugin.yaml").write_text(
            'name: station-strix\nversion: 1.0.0\nkind: standalone\n'
            'description: Governed Strix preparation and evidence for the DevOps Hermes team\n'
            'provides_tools: [station_strix]\n', encoding="utf-8")
        config["plugins"]["enabled"].append("station-strix")
        config["plugins"]["entries"]["station-strix"] = {"allow_tool_override": False}
        distribution += '  - plugins/station-strix/\n  - STRIX_TEAM.json\n'
        shutil.copyfile(source / "team/STRIX.json", destination / "STRIX_TEAM.json")

    # Ship only the governed web tools, not the operator's runtime/router/Discord plugin.
    plugin_source = source.parents[1] / "components/agk-tui/hermes/plugins/agentik_os"
    plugin_target = destination / "plugins/station-web"
    plugin_target.mkdir(parents=True)
    for filename in ("web_plugin.py", "web_fetch.py", "web_runtime.py", "scrapegraph_tool.py", "scrapegraph_runner.py"):
        original = plugin_source / filename
        if original.is_symlink() or not original.is_file():
            raise ValidationError(f"Missing or unsafe canonical web plugin source: {original}")
        shutil.copyfile(original, plugin_target / ("__init__.py" if filename == "web_plugin.py" else filename))
    (plugin_target / "plugin.yaml").write_text(
        'name: station-web\nversion: 1.0.0\nkind: standalone\n'
        'description: Governed public HTML extraction through Station runtimes\n'
        'provides_tools: [station_scrapegraph, station_crawl4ai]\n', encoding="utf-8",
    )
    import yaml
    (destination / "distribution.yaml").write_text(distribution, encoding="utf-8")
    (destination / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
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


def compile_os_to_hermes(source: Path, output: Path, *, project_root: Path | None = None,
                         workspace_root: Path | None = None, profile_mapping: dict[str, str] | None = None,
                         zone_id: str | None = None, instance_id: str | None = None,
                         organization_id: str | None = None, allowed_project_ids: tuple[str, ...] = ()) -> dict[str, Any]:
    instance = workspace_root is not None
    if instance:
        if project_root is not None or zone_id is None or instance_id is None:
            raise ValidationError("Instance compilation requires explicit Zone/instance/workspace, not a Project owner")
        validate_identifier(zone_id, "Zone id")
        validate_identifier(instance_id, "OS instance id")
        if organization_id is not None:
            validate_identifier(organization_id, "Organization id")
        for project in allowed_project_ids:
            validate_identifier(project, "allowed Project id")
        if len(set(allowed_project_ids)) != len(allowed_project_ids):
            raise ValidationError("Allowed Project declarations must be unique")
        target_root = Path(workspace_root)
        if not target_root.is_absolute() or ".." in target_root.parts:
            raise ValidationError("Instance workspace must be an absolute canonical path")
        SafeFS._assert_existing_absolute_chain(target_root)
    elif project_root is None or profile_mapping is not None or any((zone_id, instance_id, organization_id, allowed_project_ids)):
        raise ValidationError("Legacy compilation requires only its owning Project root")
    else:
        target_root = Path(project_root).resolve(strict=False)
    source = Path(source)
    SafeFS._assert_existing_absolute_chain(source.absolute())
    for current, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            candidate = Path(current) / name
            if candidate.is_symlink() or not (candidate.is_dir() or candidate.is_file()):
                raise SecurityError(f"OS source contains a symlink or special file: {candidate}")
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
    roles = [director, *[value for value in workers if value != director]]
    if len(roles) != len(set(roles)):
        raise ValidationError("OS team contains duplicate roles")
    mapping = instance_profile_map(zone_id, instance_id, roles) if instance else {role: role for role in roles}
    if profile_mapping is not None and profile_mapping != mapping:
        raise ValidationError("Instance profile mapping must match its stable Zone/instance namespace")
    profiles = [mapping[role] for role in roles]
    voice_defaults = _instance_voice_defaults(source) if instance else None

    output.mkdir(parents=True, mode=0o750)
    profiles_root = output / "profiles"
    profiles_root.mkdir()

    for role in roles:
        profile_id = mapping[role]
        if role == director:
            profile_text = (source / "director/PROFILE.md").read_text(encoding="utf-8")
        else:
            profile_path = source / "profiles" / role / "PROFILE.md"
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
            project_root=target_root,
        )
        if instance:
            _instance_routing(profiles_root / profile_id, mapping, zone_id=zone_id, instance_id=instance_id,
                              workspace_root=target_root, organization_id=organization_id,
                              allowed_project_ids=sorted(allowed_project_ids), voice_defaults=voice_defaults)

    compiled = {
        "schema_version": 2,
        "os_id": os_id,
        "os_version": os_version,
        "nano_director": mapping[director],
        "profiles": profiles,
        "project_root": str(target_root),
        "source_contract": "AGK OS v2",
        "runtime_target": "Hermes Profile Distributions",
        "claim": "COMPILED_NOT_INSTALLED",
        "next_gate": "Install every profile into the target Zone HERMES_HOME, then run Hermes/plugin Doctor and fresh-session acceptance.",
    }
    if instance:
        compiled.pop("project_root")
        compiled.update(schema_version=3, zone_id=zone_id, instance_id=instance_id,
                        organization_id=organization_id, allowed_project_ids=sorted(allowed_project_ids),
                        workspace_root=str(target_root), role_profile_map=mapping)
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
            "-i",
            f"HOME={hermes_home.parent / 'home'}",
            f"HERMES_HOME={hermes_home}",
            "PATH=/usr/local/bin:/usr/bin:/bin",
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
