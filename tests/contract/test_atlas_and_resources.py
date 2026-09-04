from __future__ import annotations

import json
from pathlib import Path

from agentik_station.resources import build_stack_plan, find_resource, load_resource_catalog


ROOT = Path(__file__).resolve().parents[2]


def test_atlas_covers_system_spine() -> None:
    atlas = (ROOT / "atlas.md").read_text(encoding="utf-8")
    for subject in (
        "Hermes",
        "/srv/station",
        "/opt/station",
        "Discord",
        "DevOps OS",
        "Convex",
        "shadcn/ui",
        "Lucide",
        "Composio",
        "Hindsight",
        "OPERATIONAL",
    ):
        assert subject in atlas


def test_resource_catalog_and_exact_web_stack_plan() -> None:
    catalog = load_resource_catalog(ROOT / "resources" / "CATALOG.json")
    assert catalog["open_to_other_stacks"] is True
    assert find_resource(catalog, "shadcn-ui")["version"] == "4.21.0"
    plan = build_stack_plan(catalog, "web-product")
    assert plan["claim"] == "PLAN_ONLY_NOT_INSTALLED"
    commands = plan["commands"]
    assert commands[0][:2] == ["npm", "install"]
    assert "next@16.3.4" in commands[0]
    assert "convex@1.45.0" in commands[0]
    assert "lucide-react@1.41.0" in commands[0]
    assert commands[-1] == ["shadcn", "init"]
    json.dumps(plan)

    pins = {}
    for line in (ROOT / "config/versions.lock").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            pins[key] = value
    expected = {
        "next": pins["NEXTJS_VERSION"],
        "react": pins["REACT_VERSION"],
        "convex": pins["CONVEX_VERSION"],
        "@clerk/nextjs": pins["CLERK_NEXTJS_VERSION"],
        "stripe": pins["STRIPE_NODE_VERSION"],
        "@stripe/stripe-js": pins["STRIPE_JS_VERSION"],
        "lucide-react": pins["LUCIDE_REACT_VERSION"],
        "tailwindcss": pins["TAILWINDCSS_VERSION"],
        "typescript": pins["TYPESCRIPT_VERSION"],
    }
    declared = {}
    for package in [*commands[0][2:], *commands[1][3:]]:
        name, version = package.rsplit("@", 1)
        declared[name] = version
    for name, version in expected.items():
        assert declared[name] == version
