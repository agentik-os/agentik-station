from __future__ import annotations

from pathlib import Path
import tomllib

import agentik_station.cli as cli

ROOT = Path(__file__).resolve().parents[2]


def test_verification_extra_includes_shipped_component_dependencies():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    verification = set(project["project"]["optional-dependencies"]["dev"])
    component = {
        line.strip()
        for line in (ROOT / "components/agk-tui/requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert component <= verification, f"Missing component test dependencies: {component - verification}"


def test_agk_tui_component_pinned():
    pin = (ROOT / "components" / "agk-tui" / "PIN").read_text().strip()
    lock = (ROOT / "config" / "versions.lock").read_text()
    assert pin
    assert f"AGK_TUI_COMMIT={pin}" in lock
    assert (ROOT / "components" / "agk-tui" / "install.sh").is_file()
    assert (ROOT / "components" / "agk-tui" / "bin" / "agk").is_file()


def test_bootstrap_wires_agk_tui():
    text = (ROOT / "bootstrap.sh").read_text()
    assert "INSTALL_AGK_TUI" in text
    assert "components/agk-tui" in text
    assert "station tui" in text
    assert "station_agk_sync.py" in text
    assert "--skip-agk-tui" in text


def test_station_tui_registered():
    parser = cli.build_parser()
    args = parser.parse_args(["tui"])
    assert args.command == "tui"
    assert callable(args.handler)
