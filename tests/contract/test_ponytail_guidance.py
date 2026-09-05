"""Blocked integration guidance is not proof of an installed plugin."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
GUIDANCE = (
    "modules/ponytail/README.md",
    "docs/hermes/12_PONYTAIL_ENGINEERING.md",
    "docs/hermes/06_SKILLS_PLUGINS_HOOKS.md",
    "docs/os/04_DEVOPS_OS.md",
    "docs/os/08_BOTS_AND_NANOTEAMS.md",
    "docs/builder/10_GAUNTLET_VERIFICATION.md",
)
FALSE_CURRENT_CLAIMS = (
    r"\bponytail(?: v[0-9.]+)? is (?:installed|installable|enabled)\b",
    r"\bponytail (?:enforces|is the simplification gate)\b",
    r"\bcoding profiles install ponytail\b",
    r"\bexpected available commands/skills\b",
)


def test_module_exactly_matches_catalog_and_reports_blocked_delivery() -> None:
    module = json.loads((ROOT / "modules/ponytail/MODULE.json").read_text())
    catalog = json.loads((ROOT / "modules/catalog.json").read_text())
    rows = [row for row in catalog["modules"] if row["id"] == "ponytail"]
    assert len(rows) == 1
    assert module == {"schema_version": 1, **rows[0]}
    assert module["maturity"] == "SCAFFOLDED"
    assert module["binary_probes"] == []
    assert "required but NOT_INSTALLED" in module["claim"]
    assert "retained native Hermes security rejection" in module["claim"]
    action = module["next_repair_action"]
    for requirement in (
        "upstream scanner correction or published distribution",
        "immutable pin",
        "fresh full native security scan",
        "scoped runtime, command and authorization acceptance",
        "Do not bypass the guard",
        "retry the rejected tree as a repair",
    ):
        assert requirement in action
    assert "station deps install" not in action


@pytest.mark.parametrize("relative", GUIDANCE)
def test_guidance_retains_blocker_and_safe_independent_work(relative: str) -> None:
    text = (ROOT / relative).read_text()
    normalized = " ".join(text.lower().split())
    assert "NOT_INSTALLED" in text
    assert "unavailable" in text
    assert "retained native hermes security scan" in normalized
    assert "immutable pin" in normalized
    assert "full native security scan" in normalized
    assert "scoped runtime/command/acl acceptance" in normalized
    assert "2026-09-05-ponytail-native-scan.md" in text
    assert "independent" in normalized and "station's" in normalized
    assert "ponytail-dependent acceptance" in normalized or "ponytail-dependent task" in normalized
    # These guidance pages must not recommend mutable direct activation or a
    # retry of the retained dangerous tree as if the normal guard would accept it.
    assert not re.search(r"hermes\s+plugins\s+(?:install|enable)\b", normalized)
    assert "agentik.lock" not in text
    for pattern in FALSE_CURRENT_CLAIMS:
        assert not re.search(pattern, normalized), relative


def test_declared_modes_and_commands_are_explicitly_future_capabilities() -> None:
    guide = (ROOT / "docs/hermes/12_PONYTAIL_ENGINEERING.md").read_text()
    skills = (ROOT / "docs/hermes/06_SKILLS_PLUGINS_HOOKS.md").read_text()
    devops = (ROOT / "docs/os/04_DEVOPS_OS.md").read_text()
    assert "Intended profile mapping — unavailable until accepted" in guide
    assert "Intended mapping after acceptance, not current configuration" in devops
    assert "Intended commands/skills after acceptance, **not available now**" in skills
    assert "Future scoped policy, only after the delivery gate passes" in skills
    for command in ("/ponytail", "/ponytail-review", "/ponytail-audit",
                    "/ponytail-debt", "/ponytail-gain", "/ponytail-help"):
        assert command in skills
    for text in (guide, skills):
        assert "process-global" in text
        assert "`HOME`" in text
        assert "config/versions.lock" in text
