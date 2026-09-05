"""Shared code locations; HOME and credentials always belong to the caller."""

import os
from pathlib import Path

PYTHON_VERSION = "3.13.15"
PLAYWRIGHT_VERSION = "1.62.0"
VERSIONS = {"scrapegraphai": "2.2.2", "crawl4ai": "0.9.3"}
ROOT = Path("/opt/station/tools/web")


def runtime_root(component: str) -> Path:
    if not os.environ.get("STATION_WORKSTATION_ROOT"):
        # Host contracts also load this tiny location module with runpy. Do not
        # require package import context for the unchanged canonical Host path.
        return ROOT / f"{component}-{VERSIONS[component]}-py{PYTHON_VERSION}-pw{PLAYWRIGHT_VERSION}"
    # Native worker scripts import this module directly; Hermes imports it as a
    # plugin package. Both paths use the same validated personal context helper.
    if __package__:
        from .workstation import workstation_root
    else:
        from workstation import workstation_root
    personal = workstation_root()
    root = personal / "tools/web" if personal else ROOT
    return root / f"{component}-{VERSIONS[component]}-py{PYTHON_VERSION}-pw{PLAYWRIGHT_VERSION}"
