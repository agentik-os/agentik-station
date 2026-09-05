"""Read-only, coupled update inventory. Upstream discovery never applies pins."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
VERSION = re.compile(r"[A-Za-z0-9_.+/-]{1,120}\Z")
GATES = ["immutable source and license/security review", "coupled SDK, adapter and runtime compatibility",
         "lockfile and image digest reconciliation", "unit/security/contract and native installation tests",
         "isolated LAB/canary readback", "state backup and explicit database/service migration review",
         "new immutable Station release on main", "installed full-check and profile-specific live acceptance"]


def inventory(repo: Path) -> dict[str, Any]:
    pins = dict(line.split("=", 1) for line in (repo / "config/versions.lock").read_text().splitlines()
                if re.fullmatch(r"[A-Z0-9_]+=[^\s]+", line))
    bom = json.loads((repo / "SBOM.cdx.json").read_text())
    rows = []
    seen = set()
    for item in bom["components"]:
        identity = item["bom-ref"]
        if identity in seen:
            continue
        seen.add(identity)
        row = {"id": identity, "name": item["name"], "pinned": item.get("version"),
               "kind": item["type"], "discovery": "REVIEW_SOURCE", "source": None,
               "compatibility": "NOT_ACCEPTED", "apply": "new-reviewed-station-release-only"}
        purl = item.get("purl", "")
        if purl.startswith("pkg:npm/"):
            row.update(discovery="npm", source=purl[8:].rsplit("@", 1)[0])
        for ref in item.get("externalReferences", []):
            url = ref.get("url", "")
            if url.startswith("https://github.com/"):
                candidate = "/".join(url.removeprefix("https://github.com/").split("/")[:2]).removesuffix(".git")
                if REPO.fullmatch(candidate):
                    row.update(discovery="github", source=candidate)
                    break
            elif url.startswith("https://pypi.org/project/"):
                candidate = url.removeprefix("https://pypi.org/project/").split("/")[0]
                if re.fullmatch(r"[A-Za-z0-9_.-]+", candidate): row.update(discovery="pypi", source=candidate)
            elif url.startswith("https://www.npmjs.com/package/"):
                row.update(discovery="npm", source=url.removeprefix("https://www.npmjs.com/package/"))
        # A CLI/client version must never be compared to an unrelated app/server tag.
        clients = {'ChatbotX CLI': ('npm', 'chatbotx'), 'Honcho': ('pypi', 'honcho-ai'),
                   'Hindsight': ('pypi', 'hindsight-client'), 'Playwright': ('pypi', 'playwright')}
        if item['name'] in clients:
            kind, source = clients[item['name']]
            row.update(discovery=kind, source=source)
        if item["type"] == "container":
            row.update(discovery="OCI_DIGEST_REVIEW", source=item["name"])
        rows.append(row)
    known_sources = {row['source'] for row in rows if row['discovery'] == 'github'}
    for key, source in sorted(pins.items()):
        if key.endswith('_REPOSITORY') and REPO.fullmatch(source) and source not in known_sources:
            prefix = key.removesuffix('_REPOSITORY')
            release = pins.get(prefix + '_RELEASE')
            commit = pins.get(prefix + '_COMMIT', pins.get(prefix + '_REVIEW_COMMIT'))
            rows.append({'id': f'station-source:{prefix.lower()}', 'name': prefix,
                         'pinned': release or commit,
                         'kind': 'source', 'discovery': 'github' if release else 'github-commit', 'source': source,
                         'compatibility': 'NOT_ACCEPTED', 'apply': 'new-reviewed-station-release-only'})
            known_sources.add(source)
    rows.append({'id': 'station-source:rmux', 'name': 'RMUX', 'pinned': pins['RMUX_VERSION'],
                 'kind': 'application', 'discovery': 'github', 'source': 'Helvesec/rmux',
                 'compatibility': 'NOT_ACCEPTED', 'apply': 'new-reviewed-station-release-only'})
    rows.append({'id': 'station-source:uv', 'name': 'uv', 'pinned': pins['UV_VERSION'],
                 'kind': 'application', 'discovery': 'pypi', 'source': 'uv',
                 'compatibility': 'NOT_ACCEPTED', 'apply': 'new-reviewed-station-release-only'})
    for manifest in sorted((repo / 'resources/services').glob('*.json')):
        service = json.loads(manifest.read_text())
        rows.append({'id': 'station-service:' + service['id'], 'name': service['id'] + ' server',
                     'pinned': service['images'][0]['version'], 'commit': service['source']['commit'],
                     'kind': 'server-source', 'discovery': 'github',
                     'source': service['source']['repository'].removeprefix('https://github.com/'),
                     'compatibility': 'NOT_ACCEPTED', 'apply': 'new-reviewed-station-release-only'})
    return {"schema_version": 1, "release": (repo / "VERSION").read_text().strip(),
            "scope": "complete-delivered-sbom-and-version-lock-not-installed-state",
            "pins": pins, "pin_count": len(pins), "components": rows, "component_count": len(rows),
            "gates": GATES, "applied": False, "compatible": False, "operational": False,
            "limitations": ["Discovery proposes versions; it never changes a lock, image, account, profile or service.",
                            "OCI digests and sources without registry metadata require explicit upstream review.",
                            "Project-owned application lockfiles require their own release tests."]}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Upstream metadata redirect refused")


def fetch_metadata(kind: str, source: str) -> dict[str, Any]:
    if kind in {"github", "github-commit"} and REPO.fullmatch(source):
        suffix = 'commits?per_page=1' if kind == 'github-commit' else 'releases/latest'
        url = f"https://api.github.com/repos/{source}/{suffix}"
        field = "sha" if kind == 'github-commit' else "tag_name"
    elif kind == "npm" and re.fullmatch(r"(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+", source):
        url, field = f"https://registry.npmjs.org/{quote(source, safe='')}/latest", "version"
    elif kind == "pypi" and re.fullmatch(r"[A-Za-z0-9_.-]+", source):
        url, field = f"https://pypi.org/pypi/{source}/json", "version"
    else:
        return {"status": "REVIEW_REQUIRED", "latest": None}
    request = Request(url, headers={"User-Agent": "Station-readonly-update-inventory", "Accept": "application/json"})
    # Public metadata only: no inherited proxy credentials, tokens or redirects.
    opener = build_opener(ProxyHandler({}), HTTPSHandler(), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024: raise ValueError("Oversized metadata")
        payload = json.loads(raw)
        if kind == 'github-commit':
            if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
                raise ValueError('Invalid commit metadata')
            payload = payload[0]
        value = payload.get("info", {}).get(field) if kind == "pypi" else payload.get(field)
        if not isinstance(value, str) or not VERSION.fullmatch(value): raise ValueError("Invalid version metadata")
        if kind == 'github-commit':
            if not re.fullmatch(r'[a-f0-9]{40}', value): raise ValueError('Invalid commit identifier')
            return {"status": "OBSERVED_NOT_ACCEPTED", "latest": value,
                    "track": "default-branch-commit-not-a-release"}
        return {"status": "OBSERVED_NOT_ACCEPTED", "latest": value}
    except HTTPError as exc:
        return {"status": "NO_RELEASE_METADATA" if exc.code == 404 else "UNAVAILABLE", "latest": None}
    except Exception:
        return {"status": "UNAVAILABLE", "latest": None}


def check(repo: Path, *, fetch=fetch_metadata) -> dict[str, Any]:
    report = inventory(repo)
    sources = sorted({(row["discovery"], row["source"]) for row in report["components"]
                      if row["discovery"] in {"github", "github-commit", "npm", "pypi"}})
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda pair: fetch(*pair), sources))
    observations = dict(zip(sources, values))
    for row in report["components"]:
        value = observations.get((row["discovery"], row["source"]), {"status": "REVIEW_REQUIRED", "latest": None})
        row["upstream"] = value
        row["different"] = value["latest"].removeprefix("v") != str(row["pinned"]).removeprefix("v") if value["latest"] else None
    report.update(checked_at=datetime.now(timezone.utc).isoformat(),
                  collection_succeeded=all(value['status'] in {'OBSERVED_NOT_ACCEPTED', 'NO_RELEASE_METADATA'}
                                           for value in values),
                  discovery_complete=all(row["upstream"]["status"] == "OBSERVED_NOT_ACCEPTED" for row in report["components"]))
    return report
