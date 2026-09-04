from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .errors import SecurityError, ValidationError


START = "<!-- STATION-MANAGED-RULES:START -->"
END = "<!-- STATION-MANAGED-RULES:END -->"
RULES_REFERENCE = ".station/STATION_AGENT_RULES.md"

ADAPTERS = {
    "AGENTS.md": "Read and obey `.station/STATION_AGENT_RULES.md` before any work in this repository.",
    "CLAUDE.md": "Read and obey `.station/STATION_AGENT_RULES.md` before any Claude Code work in this repository.",
    "GEMINI.md": "Read and obey `.station/STATION_AGENT_RULES.md` before any Gemini CLI work in this repository.",
    ".github/copilot-instructions.md": "Apply `.station/STATION_AGENT_RULES.md` to every GitHub Copilot task in this repository.",
}


def _assert_directory(path: Path, label: str) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} does not exist: {path}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise SecurityError(f"{label} must be a real directory: {path}")


def _read_regular_or_empty(path: Path) -> str:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return ""
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise SecurityError(f"Refusing to replace non-regular instruction file: {path}")
    return path.read_text(encoding="utf-8")


def _managed_text(existing: str, instruction: str) -> str:
    block = f"{START}\n{instruction}\n{END}"
    if START in existing or END in existing:
        if existing.count(START) != 1 or existing.count(END) != 1 or existing.index(START) > existing.index(END):
            raise ValidationError("Malformed Station-managed instruction block")
        before, tail = existing.split(START, 1)
        _, after = tail.split(END, 1)
        return (before.rstrip() + "\n\n" + block + after).strip() + "\n"
    if not existing.strip():
        return block + "\n"
    return existing.rstrip() + "\n\n" + block + "\n"


def _atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    _assert_directory(path.parent, "Instruction parent")
    _read_regular_or_empty(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def install_agent_rules(repo_root: Path, canonical_rules: str, *, plan_only: bool = False) -> dict[str, Any]:
    repo_root = Path(os.path.abspath(repo_root))
    _assert_directory(repo_root, "Repository root")
    git_marker = repo_root / ".git"
    try:
        marker_mode = os.lstat(git_marker).st_mode
    except FileNotFoundError as exc:
        raise ValidationError(f"Target is not a Git repository/worktree: {repo_root}") from exc
    if stat.S_ISLNK(marker_mode) or not (stat.S_ISDIR(marker_mode) or stat.S_ISREG(marker_mode)):
        raise SecurityError(f"Unsafe .git marker: {git_marker}")
    actions: list[dict[str, str]] = []
    targets = [(repo_root / RULES_REFERENCE, canonical_rules)]
    for relative, instruction in ADAPTERS.items():
        path = repo_root / relative
        targets.append((path, _managed_text(_read_regular_or_empty(path), instruction)))
    for path, desired in targets:
        existing = _read_regular_or_empty(path)
        action = "unchanged" if existing == desired else "write"
        actions.append({"path": str(path), "action": action})
        if not plan_only and action == "write":
            _atomic_write(path, desired)
    return {
        "schema_version": 1,
        "repository": str(repo_root),
        "state": "PLAN_READY" if plan_only else "INSTALLED",
        "actions": actions,
        "claim": "RULES_PLANNED_NOT_WRITTEN" if plan_only else "RULES_INSTALLED_NOT_RUNTIME_ACCEPTED",
    }
