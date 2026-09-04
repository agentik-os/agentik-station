"""Global AGK rules injected into every Hermes and OpenRouter conversation."""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def _rules_path() -> Path:
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


def active_rules() -> list[dict]:
    path = _rules_path()
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return []
    rules = document.get("rules") or []
    return [
        rule
        for rule in rules
        if isinstance(rule, dict)
        and rule.get("enabled", True)
        and str(rule.get("content") or "").strip()
        and (
            "*" in (rule.get("providers") or ["*"])
            or "hermes" in (rule.get("providers") or [])
            or "openrouter" in (rule.get("providers") or [])
        )
    ]


def rules_prompt(_session_info: dict | None = None) -> str:
    if not active_rules():
        return ""
    # Full canonical rules remain in the registry. Inject only the compact invariant
    # so dedicated completion, owner, UI and inter-agent sections fit the aggregate
    # Hermes plugin prompt budget.
    return (
        "AGK rules active: resolve intent; plan and independently verify; preserve user work; "
        "verify the live runtime; isolate profiles; treat Station scope as Hermes+AGK+Discord; "
        "publish only safe contextual links."
    )
