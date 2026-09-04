"""Shared code locations; HOME and credentials always belong to the caller."""

from pathlib import Path

PYTHON_VERSION = "3.13.15"
PLAYWRIGHT_VERSION = "1.62.0"
VERSIONS = {"scrapegraphai": "2.2.2", "crawl4ai": "0.9.3"}
ROOT = Path("/opt/station/tools/web")


def runtime_root(component: str) -> Path:
    return ROOT / f"{component}-{VERSIONS[component]}-py{PYTHON_VERSION}-pw{PLAYWRIGHT_VERSION}"
