#!/usr/bin/env python3
"""Generate/check the exact release inventory, provenance and CycloneDX SBOM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATED = {"FILE_INDEX.md", "MANIFEST.json", "RELEASE_PROVENANCE.json"}
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}


def inventory() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in IGNORED_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"release inventory contains a symlinked file: {relative}")
        result.append(path)
    return sorted(result, key=lambda item: str(item.relative_to(ROOT)))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_versions() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "config" / "versions.lock").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def npm_components(lock_path: Path) -> list[dict[str, Any]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    result = []
    for location, item in sorted(lock.get("packages", {}).items()):
        if not location or "node_modules/" not in location or not isinstance(item, dict) or not item.get("version"):
            continue
        name = location.rsplit("node_modules/", 1)[1]
        version = str(item["version"])
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": f"pkg:npm/{name}@{version}",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{name}@{version}",
        }
        if item.get("integrity"):
            component["properties"] = [{"name": "npm:dist:integrity", "value": str(item["integrity"])}]
        if item.get("resolved"):
            component["externalReferences"] = [{"type": "distribution", "url": str(item["resolved"])}]
        result.append(component)
    return result


def sbom_payload() -> dict[str, Any]:
    pins = read_versions()
    release = (ROOT / "VERSION").read_text().strip()
    declared = [
        ("Hermes Agent", "application", pins["HERMES_RELEASE"], "https://github.com/NousResearch/hermes-agent"),
        ("Python", "application", pins["PYTHON_VERSION"], "https://www.python.org"),
        ("Python AI", "application", pins["AI_PYTHON_VERSION"], "https://www.python.org"),
        ("ScrapeGraphAI", "library", pins["SCRAPEGRAPHAI_VERSION"], "https://github.com/ScrapeGraphAI/Scrapegraph-ai"),
        ("Strix", "application", pins["STRIX_VERSION"], "https://github.com/usestrix/strix"),
        ("Playwright", "library", pins["PLAYWRIGHT_VERSION"], "https://playwright.dev/python/"),
        ("Node.js", "application", pins["NODE_VERSION"], "https://nodejs.org"),
        ("npm", "application", pins["NPM_VERSION"], "https://www.npmjs.com/package/npm"),
        ("GitHub CLI", "application", pins["GITHUB_CLI_VERSION"], "https://github.com/cli/cli"),
        ("Vercel CLI", "application", pins["VERCEL_CLI_VERSION"], "https://www.npmjs.com/package/vercel"),
        ("Codex CLI", "application", pins["CODEX_CLI_VERSION"], "https://www.npmjs.com/package/@openai/codex"),
        ("Composio CLI", "application", pins["COMPOSIO_CLI_VERSION"], "https://composio.dev"),
        ("shadcn CLI", "application", pins["SHADCN_CLI_VERSION"], "https://www.npmjs.com/package/shadcn"),
        ("Ponytail", "library", pins["PONYTAIL_RELEASE"], "https://github.com/DietrichGebert/ponytail"),
        ("Langfuse", "application", pins["LANGFUSE_RELEASE"], "https://github.com/langfuse/langfuse"),
        ("Honcho", "library", pins["HONCHO_PYTHON_VERSION"], "https://github.com/plastic-labs/honcho"),
        ("Hindsight", "library", pins["HINDSIGHT_PYTHON_VERSION"], "https://github.com/vectorize-io/hindsight"),
        ("TigerVNC", "application", pins["TIGERVNC_RELEASE"], "https://github.com/TigerVNC/tigervnc"),
        ("Crawl4AI", "application", pins["CRAWL4AI_PYTHON_VERSION"], "https://github.com/unclecode/crawl4ai"),
        ("Parakeet", "application", pins["PARAKEET_RELEASE"], "https://github.com/achetronic/parakeet"),
        ("setuptools", "library", "84.0.0", "https://pypi.org/project/setuptools/84.0.0/"),
        ("pytest", "library", "8.4.2", "https://pypi.org/project/pytest/8.4.2/"),
        ("Pillow", "library", "12.3.0", "https://pypi.org/project/Pillow/12.3.0/"),
        ("PyYAML", "library", "6.0.3", "https://pypi.org/project/PyYAML/6.0.3/"),
        ("jsonschema", "library", "4.25.1", "https://pypi.org/project/jsonschema/4.25.1/"),
    ]
    components: list[dict[str, Any]] = []
    for name, kind, version, url in declared:
        ref = f"station:{name.lower().replace(' ', '-')}@{version}"
        components.append(
            {
                "type": kind,
                "bom-ref": ref,
                "name": name,
                "version": version,
                "externalReferences": [{"type": "website", "url": url}],
            }
        )
    for lock in (
        ROOT / "components" / "agk-tui" / "apps" / "hermes-fleet" / "package-lock.json",
        ROOT / "resources" / "discord-js-sdk" / "package-lock.json",
    ):
        components.extend(npm_components(lock))
    unique = {str(item["bom-ref"]): item for item in components}
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/agentik-os/agentik-station/{release}")),
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"pkg:generic/agentik-station@{release}",
                "name": "agentik-station",
                "version": release,
            },
            "properties": [
                {"name": "station:claim", "value": "READY_FOR_SETUP"},
                {"name": "station:generation", "value": "deterministic-no-network"},
            ],
        },
        "components": [unique[key] for key in sorted(unique)],
    }


def provenance_payload(paths: list[Path], virtual_files: dict[Path, bytes] | None = None) -> dict[str, Any]:
    virtual_files = virtual_files or {}
    subjects = []
    for path in paths:
        relative = str(path.relative_to(ROOT))
        if relative in GENERATED:
            continue
        info = os.lstat(path) if path.exists() or path.is_symlink() else None
        if info is not None and not stat.S_ISREG(info.st_mode):
            raise ValueError(f"provenance subject is not a regular file: {relative}")
        data = virtual_files[path] if path in virtual_files else path.read_bytes()
        subjects.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "executable": bool(info and info.st_mode & 0o111),
            }
        )
    return {
        "schema_version": "agk-release-provenance/v1",
        "release": (ROOT / "VERSION").read_text().strip(),
        "algorithm": "sha256",
        "claim": "SOURCE_TREE_VERIFIED_NOT_RUNTIME_ACCEPTED",
        "generated_by": "scripts/generate_release_metadata.py",
        "excluded_generated_files": sorted(GENERATED),
        "subject_count": len(subjects),
        "subjects": subjects,
    }


def rendered_outputs() -> dict[Path, str]:
    sbom = json.dumps(sbom_payload(), indent=2, sort_keys=True) + "\n"
    # Render in memory. --check must work on immutable releases without even
    # momentarily rewriting their metadata or changing file timestamps.
    paths = sorted(set(inventory()) | {ROOT / name for name in GENERATED | {"SBOM.cdx.json"}},
                   key=lambda path: str(path.relative_to(ROOT)))
    provenance = json.dumps(provenance_payload(paths, {ROOT / "SBOM.cdx.json": sbom.encode("utf-8")}), indent=2, sort_keys=True) + "\n"
    names = [str(path.relative_to(ROOT)) for path in paths]
    manifest_path = ROOT / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["release"] = (ROOT / "VERSION").read_text().strip()
    manifest["files"] = names
    manifest["file_count"] = len(names)
    manifest_text = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    index_text = "# FILE_INDEX\n\nTotal files: " + str(len(names)) + "\n\n" + "".join(f"- `{name}`\n" for name in names)
    return {
        ROOT / "SBOM.cdx.json": sbom,
        ROOT / "RELEASE_PROVENANCE.json": provenance,
        manifest_path: manifest_text,
        ROOT / "FILE_INDEX.md": index_text,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    before = {
        path: path.read_text(encoding="utf-8") if path.is_file() else None
        for path in (ROOT / "SBOM.cdx.json", ROOT / "RELEASE_PROVENANCE.json", ROOT / "MANIFEST.json", ROOT / "FILE_INDEX.md")
    }
    outputs = rendered_outputs()
    if args.check:
        mismatches = [str(path.relative_to(ROOT)) for path, text in outputs.items() if before[path] != text]
        if mismatches:
            print("release metadata drift: " + ", ".join(mismatches), file=sys.stderr)
            return 1
        print("RELEASE_METADATA_OK")
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    print(f"RELEASE_METADATA_WRITTEN {len(inventory())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
