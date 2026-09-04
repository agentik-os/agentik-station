from __future__ import annotations

from pathlib import Path

import pytest

from agentik_station.agent_rules import END, START, install_agent_rules
from agentik_station.errors import SecurityError, ValidationError


RULES = "# Rules\n\nStay inside the owning Project.\n"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def test_agent_rules_install_is_idempotent_and_preserves_existing_content(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "AGENTS.md").write_text("# Existing instructions\n", encoding="utf-8")
    first = install_agent_rules(repo, RULES)
    second = install_agent_rules(repo, RULES)
    assert first["state"] == "INSTALLED"
    assert all(item["action"] == "unchanged" for item in second["actions"])
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "# Existing instructions" in agents
    assert agents.count(START) == 1
    assert agents.count(END) == 1
    assert (repo / ".station/STATION_AGENT_RULES.md").read_text(encoding="utf-8") == RULES
    assert (repo / ".github/copilot-instructions.md").is_file()


def test_agent_rules_plan_does_not_write(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = install_agent_rules(repo, RULES, plan_only=True)
    assert result["state"] == "PLAN_READY"
    assert not (repo / ".station").exists()


def test_agent_rules_rejects_non_git_and_symlink_instruction(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValidationError):
        install_agent_rules(empty, RULES)
    repo = _repo(tmp_path)
    target = tmp_path / "outside"
    target.write_text("outside", encoding="utf-8")
    (repo / "CLAUDE.md").symlink_to(target)
    with pytest.raises(SecurityError):
        install_agent_rules(repo, RULES)
