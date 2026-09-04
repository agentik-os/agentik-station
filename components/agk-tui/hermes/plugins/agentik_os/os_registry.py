"""Secure, read-first Operative System registry contracts.

No package is created by this module unless a future privileged installer
explicitly calls an installation primitive. Archive inspection never executes
or extracts package content.
"""

from __future__ import annotations

import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml


OS_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
ALLOWED_SCOPES = {"global", "operator", "agentik", "mission", "private", "client", "project", "session"}
LIST_FIELDS = ("dependencies", "capabilities", "skills", "workflows", "agents", "tools", "commands", "knowledge", "evals")
MAX_ARCHIVE_FILES = 5000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


@dataclass(frozen=True)
class InspectedPackage:
    manifest: dict
    manifest_path: str
    file_count: int
    uncompressed_bytes: int


def validate_manifest(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("OS manifest must be a mapping")
    manifest = dict(raw)
    required = ("id", "name", "version", "description", "scope")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"OS manifest missing required fields: {', '.join(missing)}")
    if not OS_ID.fullmatch(str(manifest["id"])):
        raise ValueError("OS id must be a lowercase kebab-case identifier")
    if not SEMVER.fullmatch(str(manifest["version"])):
        raise ValueError("OS version must be semantic versioning")
    if not isinstance(manifest["name"], str) or not manifest["name"].strip():
        raise ValueError("OS name must be non-empty")
    if not isinstance(manifest["description"], str):
        raise ValueError("OS description must be a string")
    scopes = manifest["scope"]
    if not isinstance(scopes, list) or not scopes or any(scope not in ALLOWED_SCOPES for scope in scopes):
        raise ValueError("OS scope must be a non-empty list of allowed scopes")
    if len(scopes) != len(set(scopes)):
        raise ValueError("OS scope entries must be unique")
    for field in LIST_FIELDS:
        value = manifest.setdefault(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"OS manifest field {field} must be a list of strings")
    return manifest


def inspect_zip(path: Path) -> InspectedPackage:
    """Inspect an untrusted OS ZIP without extracting or executing it."""
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise ValueError("package is not a valid ZIP archive")
    manifests: list[zipfile.ZipInfo] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError("OS archive contains too many files")
        for info in infos:
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or "\\" in info.filename:
                raise ValueError(f"unsafe archive path: {info.filename}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"archive symlinks are not allowed: {info.filename}")
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("OS archive exceeds uncompressed size limit")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ValueError(f"suspicious compression ratio: {info.filename}")
            if member.name.lower() in {"manifest.yaml", "manifest.yml", "manifest.json", "os.yaml", "os.yml"}:
                manifests.append(info)
        if len(manifests) != 1:
            raise ValueError("OS archive must contain exactly one recognizable manifest")
        selected = manifests[0]
        payload = archive.read(selected)
        if len(payload) > 1024 * 1024:
            raise ValueError("OS manifest exceeds 1 MiB")
        try:
            raw = json.loads(payload) if selected.filename.lower().endswith(".json") else yaml.safe_load(payload)
        except Exception as exc:
            raise ValueError(f"OS manifest cannot be parsed: {exc}") from exc
    return InspectedPackage(validate_manifest(raw), selected.filename, len(infos), total)


class OSRegistry:
    def __init__(self, root: Path = Path("/opt/agentik/os-registry")):
        self.root = root

    def packages(self) -> list[dict]:
        try:
            index = json.loads((self.root / "state/index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        packages = index.get("packages", []) if isinstance(index, dict) else []
        return [item for item in packages if isinstance(item, dict)]

    def find(self, package_id: str, version: str | None = None) -> list[dict]:
        return [p for p in self.packages() if p.get("id") == package_id and (version is None or p.get("version") == version)]

    def doctor(self, assignment_paths: list[Path] | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        seen: set[tuple[str, str]] = set()
        installed = set()
        for package in self.packages():
            try:
                manifest = validate_manifest(package)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            key = (manifest["id"], manifest["version"])
            if key in seen:
                errors.append(f"duplicate registry entry: {key[0]}@{key[1]}")
            seen.add(key)
            installed.add(f"{key[0]}@{key[1]}")
            package_path = self.root / "packages" / key[0] / key[1]
            if not package_path.is_dir():
                errors.append(f"package directory missing: {key[0]}@{key[1]}")
        for path in assignment_paths or []:
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except OSError as exc:
                errors.append(f"assignment file unreadable: {path}: {exc}")
                continue
            records = data.get("assignments", []) if isinstance(data, dict) else []
            if not isinstance(records, list):
                errors.append(f"assignments must be a list: {path}")
                continue
            for record in records:
                reference = record if isinstance(record, str) else record.get("os") if isinstance(record, dict) else None
                if not reference or reference not in installed:
                    errors.append(f"assignment references an uninstalled OS: {reference}")
        return not errors, errors


def resolve_assignments(records: list[dict], context: dict) -> list[str]:
    """Resolve GLOBAL→environment→client→project→session assignments."""
    levels = ("global", "environment", "client", "project", "session")
    resolved: list[str] = []
    for level in levels:
        for record in records:
            if not isinstance(record, dict) or record.get("scope") != level:
                continue
            target = record.get("target")
            expected = "global" if level == "global" else context.get(f"{level}_id")
            if target != expected:
                continue
            reference = record.get("os")
            if isinstance(reference, str) and reference not in resolved:
                resolved.append(reference)
    return resolved
