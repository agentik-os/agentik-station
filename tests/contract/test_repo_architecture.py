from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".sh", ".toml", ".txt", ""}


def test_required_repository_contract_files_exist() -> None:
    required = [
        "README.md",
        "ARCHITECTURE.md",
        "INSTALL.md",
        "SETUP.md",
        "SECURITY.md",
        "AGENTS.md",
        "CLAUDE.md",
        "AI_INSTALL_PROMPT.md",
        "VERSION",
        "station",
        "install",
        "pyproject.toml",
        "config/station.default.json",
        "docs/hardening/README.md",
    ]
    assert all((ROOT / path).is_file() for path in required)


def test_canonical_architecture_uses_zone_and_simple_numbering() -> None:
    text = "\n".join((ROOT / path).read_text() for path in ["README.md", "ARCHITECTURE.md", "AGENTS.md"])
    assert re.search(r"\bZone\b", text)
    assert not re.search(r"\bCells?\b", text, re.IGNORECASE)
    for name in ["1_SYSTEM", "2_PRIVATE", "3_AGENTIK", "4_ORGANIZATIONS", "5_PROJECTS", "6_FACTORY", "7_LAB"]:
        assert name in text
    assert "10_CELLS" not in text and "20_SHARED" not in text


def test_os_and_module_catalogs_do_not_claim_scaffolds_operational() -> None:
    modules = json.loads((ROOT / "modules" / "catalog.json").read_text())
    packages = json.loads((ROOT / "os" / "CATALOG.json").read_text())
    assert all(item["maturity"] != "OPERATIONAL" for item in modules["modules"] if item["id"] != "station-kernel")
    assert all(item["maturity"] == "INSTALLABLE" for item in packages["packages"])
    assert all(item["runtime_state"] == "NOT_INSTALLED" for item in packages["packages"])


def test_no_forbidden_legacy_or_generated_cache_in_active_tree() -> None:
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in {"history", "audit", ".git"} for part in relative.parts):
            continue
        assert path.name not in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        if path.is_file() and path.suffix.lower() in ACTIVE_TEXT_SUFFIXES:
            text = path.read_text(errors="ignore").lower()
            assert "nutri" + "tion" not in text, str(relative)
            assert "curl" + " | sh" not in text, str(relative)
            assert "shell" + "=true" not in text.replace(" ", ""), str(relative)


def test_only_one_canonical_systemd_source_exists() -> None:
    sources = [path for path in ROOT.rglob("station-doctor.service") if "history" not in path.parts]
    assert sources == [ROOT / "runtime" / "systemd" / "station-doctor.service"]


def test_repository_paths_are_portable_to_case_insensitive_filesystems() -> None:
    seen: dict[str, Path] = {}
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts:
            continue
        folded = str(relative).casefold()
        assert folded not in seen, f"case-colliding paths: {seen.get(folded)} and {relative}"
        seen[folded] = relative
