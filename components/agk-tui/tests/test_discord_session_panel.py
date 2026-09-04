from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "hermes" / "plugins" / "platforms" / "discord" / "agk_session_panel.py"
)
SPEC = importlib.util.spec_from_file_location("agk_session_panel", MODULE_PATH)
assert SPEC and SPEC.loader
session_panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(session_panel)


def test_picker_filters_internal_rows_and_bounds_discord_fields():
    rows = session_panel.session_picker_rows(
        [
            {
                "id": "20260826_024739_dda9be55",
                "title": "  Continue   the profile conversation  ",
                "source": "discord",
                "last_active": 1_787_743_951,
            },
            {"id": "tool-row", "title": "secret", "source": "tool"},
            {"id": "hidden-row", "source": "cli", "hidden": 1},
            {"id": "bad id; /new", "title": "unsafe", "source": "cli"},
        ]
    )

    assert len(rows) == 1
    assert rows[0]["id"] == "20260826_024739_dda9be55"
    assert rows[0]["label"] == "Continue the profile conversation"
    assert rows[0]["description"].startswith("discord · ")
    assert len(rows[0]["label"]) <= 88
    assert len(rows[0]["description"]) <= 100


def test_resume_command_uses_native_admin_scoped_gateway_path():
    assert (
        session_panel.resume_all_command("20260826_024739_dda9be55")
        == "/resume --all 20260826_024739_dda9be55"
    )
    with pytest.raises(ValueError):
        session_panel.resume_all_command("x; /clear")
