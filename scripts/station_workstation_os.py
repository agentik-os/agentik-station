#!/usr/bin/env python3
"""Compile one bundled personal OS; never authenticate, start a service or use sudo."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from agentik_station.errors import StationError, ValidationError
from agentik_station.identifiers import validate_identifier
from agentik_station.os_discovery import resolve_package
from agentik_station.os_runtime import compile_os_to_hermes, _map_role_references


def tree_digest(root: Path, *, exclude: tuple[str, ...] = ()) -> str:
    digest = hashlib.sha256()
    paths = [root] if root.is_file() else sorted(root.rglob("*"))
    for path in paths:
        if path.name in exclude:
            continue
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValidationError("OS evidence requires regular, single-link files")
        digest.update(str(path.relative_to(root) if path != root else path.name).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def inputs_digest(source: Path) -> str:
    roots = [source, REPO / "os/_shared", REPO / "rules/STATION_AGENT_RULES.md",
             REPO / "config/hermes/orchestration.default.yaml", REPO / "os/CATALOG.json",
             REPO / "src/agentik_station/os_runtime.py", Path(__file__),
             REPO / "components/agk-tui/hermes/plugins/agentik_os"]
    return hashlib.sha256("\0".join(tree_digest(root) for root in roots).encode()).hexdigest()


def private_path(root: Path, target: Path) -> None:
    if not target.is_relative_to(root) or target == root:
        raise ValidationError("Workstation OS path must remain inside its enrolled root")
    for path in (root, *[root.joinpath(*target.relative_to(root).parts[:n])
                        for n in range(1, len(target.relative_to(root).parts) + 1)]):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValidationError("Personal OS ancestry must be real, private and owned by the invoking user")


def compile_personal(root: Path, profile: str, os_id: str, output: Path, *, check: bool = False) -> dict:
    import yaml

    if os.geteuid() == 0:
        raise ValidationError("Personal OS compilation must run as the enrolled non-root user")
    if not root.is_absolute() or ".." in root.parts or root.is_symlink():
        raise ValidationError("Explicit absolute Workstation root required")
    validate_identifier(profile, "Workstation profile")
    package = resolve_package(REPO, os_id)
    if package["os_id"] not in {"stepper-os", "builder-os", "librarian-os"} or os_id != package["os_id"]:
        raise ValidationError("Only canonical bundled personal OS ids are accepted")
    if output != root / "resources/os-distributions" / os_id:
        raise ValidationError("Unexpected personal OS distribution destination")
    workspace = root / "personal/os" / os_id / "workspace"
    home = root / "personal/home/os" / os_id / "hermes"
    source = REPO / package["source"]
    if check:
        for target in (workspace, home, output):
            private_path(root, target)
            if not target.is_dir():
                raise ValidationError("Personal OS software or namespace is missing")
        marker = output / "COMPILED.json"
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise ValidationError("Unsafe personal OS compiled record")
        record = json.loads(marker.read_text(encoding="utf-8"))
        if (record.get("schema_version") != 4 or record.get("os_id") != os_id
                or record.get("workspace_root") != str(workspace) or record.get("hermes_home") != str(home)
                or record.get("inputs_sha256") != inputs_digest(source)
                or record.get("artifacts_sha256") != tree_digest(output, exclude=("COMPILED.json",))):
            raise ValidationError("Compiled personal OS differs from the reviewed release or workspace")
        return record
    for target in (workspace, home, output.parent):
        private_path(root, target)
        # mkdir(parents=True) uses the process umask for intermediate ancestors.
        target.mkdir(parents=True, mode=0o700, exist_ok=True)
        private_path(root, target)
    compiled = compile_os_to_hermes(source, output, project_root=workspace)
    mapping = {}
    for role in compiled["profiles"]:
        digest = hashlib.sha256("\0".join((str(root), profile, os_id, role)).encode()).hexdigest()[:16]
        mapping[role] = f"w-{digest}-{role[:25].rstrip('-')}"
    for role, native in mapping.items():
        validate_identifier(native, "personal OS profile")
        original = output / "profiles" / role
        destination = output / "profiles" / native
        original.rename(destination)
        config_path = destination / "config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["profile"]["id"] = native
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        manifest_path = destination / "distribution.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["name"] = native
        manifest["description"] = f"{os_id} personal role {role}"
        manifest["distribution_owned"].append("PERSONAL.json")
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        binding = {"schema_version": 1, "boundary": "personal-same-uid", "os_id": os_id,
                   "workstation_profile": profile, "hermes_home": str(home),
                   "workspace_root": str(workspace), "role_profile_map": mapping,
                   "zone_isolation": False, "accounts_enrolled": False}
        (destination / "PERSONAL.json").write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
        commands = destination / "COMMANDS.yaml"
        commands.write_text(yaml.safe_dump(_map_role_references(yaml.safe_load(commands.read_text()), mapping), sort_keys=False), encoding="utf-8")
        soul = destination / "SOUL.md"
        text = soul.read_text(encoding="utf-8")
        for canonical, scoped in mapping.items():
            text = text.replace(f"`{canonical}`", f"`{scoped}`")
        soul.write_text("# Personal Workstation OS\n\n"
                        "Use PERSONAL.json instead of INSTANCE.json in this deployment. "
                        "This is a personal same-UID namespace, not a Host Zone or client isolation. "
                        "Never import the user's external account files. Native role selectors:\n\n"
                        + "\n".join(f"- {name}: `{value}`" for name, value in mapping.items())
                        + "\n\n" + text, encoding="utf-8")
    result = {"schema_version": 4, "os_id": os_id, "os_version": compiled["os_version"],
              "profiles": list(mapping.values()), "nano_director": mapping[compiled["nano_director"]],
              "role_profile_map": mapping, "workspace_root": str(workspace), "hermes_home": str(home),
              "boundary": "personal-same-uid", "claim": "COMPILED_NOT_INSTALLED",
              "inputs_sha256": inputs_digest(source),
              "artifacts_sha256": tree_digest(output, exclude=("COMPILED.json",))}
    (output / "COMPILED.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for path in [output, *output.rglob("*")]:
        path.chmod(0o700 if path.is_dir() else 0o600)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--os-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Read back existing software, without importing profiles")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(compile_personal(args.root, args.profile, args.os_id, args.output, check=args.check), sort_keys=True))
    except (StationError, ValueError, OSError) as error:
        print(f"Personal OS compilation failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
