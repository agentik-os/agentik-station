#!/usr/bin/env python3
"""Project AGK's managed global rule block into supported provider files."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

START = "<!-- AGK MANAGED RULES: START -->"
END = "<!-- AGK MANAGED RULES: END -->"


def rules_path() -> Path:
    configured = os.environ.get("AGK_RULES_CONFIG")
    if configured:
        return Path(configured).expanduser()
    user_rules = Path.home() / ".agentik" / "rules.yaml"
    if user_rules.is_file():
        return user_rules
    system_rules = Path("/etc/agk-terminal/rules.yaml")
    if system_rules.is_file():
        return system_rules
    root = Path(os.environ.get("AGK_TERMINAL_ROOT", "/usr/local/lib/agk-terminal"))
    return root / "config" / "rules.yaml"


def load_rules(path: Path) -> list[dict]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = document.get("rules") or []
    return [
        rule
        for rule in rules
        if isinstance(rule, dict)
        and rule.get("enabled", True)
        and str(rule.get("content") or "").strip()
    ]


def applies(rule: dict, provider: str) -> bool:
    providers = rule.get("providers") or ["*"]
    return "*" in providers or provider in providers


def render(rules: list[dict], provider: str) -> str:
    lines = [START, "# AGK global rules", ""]
    for rule in rules:
        if not applies(rule, provider):
            continue
        title = str(rule.get("title") or rule.get("id") or "Rule").strip()
        content = str(rule.get("content") or "").strip()
        lines.extend([f"## {title}", "", content, ""])
    lines.append(END)
    return "\n".join(lines) + "\n"


def update(path: Path, block: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError(f"refusing symlinked provider rules file: {path}")
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if START in current and END in current:
        before, remainder = current.split(START, 1)
        _, after = remainder.split(END, 1)
        prefix = before.rstrip()
        updated = (prefix + "\n\n" if prefix else "") + block + after.lstrip("\n")
    else:
        updated = current.rstrip() + ("\n\n" if current.strip() else "") + block
    temporary = path.with_name(f".{path.name}.agk-new")
    temporary.write_text(updated, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def main() -> int:
    source = rules_path()
    rules = load_rules(source)
    targets = {
        "claude": Path.home() / ".claude" / "CLAUDE.md",
        "codex": Path.home() / ".codex" / "AGENTS.md",
        "opencode": Path.home() / ".config" / "opencode" / "AGENTS.md",
    }
    for provider, target in targets.items():
        update(target, render(rules, provider))
        print(f"{provider}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
