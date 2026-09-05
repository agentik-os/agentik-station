"""Run the real dependency dispatcher only against disposable fixture files."""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
PINS = {"PONYTAIL_REPOSITORY": "DietrichGebert/ponytail", "PONYTAIL_RELEASE": "v4.9.0",
        "PONYTAIL_COMMIT": "0a4dd63ad4541f4f655c4108a295916f3c1d8fda"}


@pytest.fixture
def gate(tmp_path):
    repo = tmp_path.resolve() / "release"
    (repo / "scripts").mkdir(parents=True)
    (repo / "config").mkdir()
    script = repo / "scripts/station_deps_install.sh"
    shutil.copyfile(ROOT / "scripts/station_deps_install.sh", script)
    home = tmp_path.resolve() / "private-home"
    (home / ".local/bin").mkdir(parents=True)
    (home / ".hermes").mkdir()
    calls = tmp_path / "native-calls"
    # Any attempted native installation, plugin listing or fallback is visible.
    hermes = home / ".local/bin/hermes"
    hermes.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + shlex.quote(str(calls)) + "\nexit 0\n")
    hermes.chmod(0o755)
    config = home / ".hermes/config.yaml"

    def run(*, changes=None, scan=False, missing=()):
        pins = PINS | (changes or {})
        (repo / "config/versions.lock").write_text(
            "".join(key + "=" + shlex.quote(value) + "\n" for key, value in pins.items() if key not in missing))
        config.write_text("plugins:\n  scan_on_install: " + ("true" if scan else "false") + "\n")
        before = config.read_bytes()
        result = subprocess.run(
            ["/bin/bash", str(script), "--component", "ponytail"],
            env={"PATH": str(hermes.parent) + ":/usr/bin:/bin", "HOME": str(home),
                 "STATION_HOME": str(home), "HERMES_HOME": str(home / ".hermes"),
                 "STATION_USER": pwd.getpwuid(os.geteuid()).pw_name, "LANG": "C.UTF-8"},
            cwd=repo, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
        )
        assert not calls.exists(), "Known/unreviewed Ponytail must never reach a native command"
        assert config.read_bytes() == before, "The gate must preserve the account's scanner setting"
        assert not (home / ".hermes/plugins").exists()
        assert "Ponytail installed through" not in result.stdout
        assert "Done." not in result.stdout
        return result

    return run


@pytest.mark.parametrize("scan", [False, True])
def test_exact_rejected_pin_never_calls_native_installer_regardless_of_scan_config(gate, scan):
    result = gate(scan=scan)
    assert result.returncode == 1
    assert "BLOCKED:" in result.stderr
    assert PINS["PONYTAIL_COMMIT"] in result.stderr
    assert PINS["PONYTAIL_RELEASE"] in result.stderr
    assert PINS["PONYTAIL_REPOSITORY"] in result.stderr
    assert "No plugin was installed or enabled" in result.stderr
    assert "docs/audit/2026-09-05-ponytail-native-scan.md" in result.stderr


@pytest.mark.parametrize("changes", [
    {"PONYTAIL_COMMIT": "a" * 40},
    {"PONYTAIL_RELEASE": "v4.9.1"},
    {"PONYTAIL_REPOSITORY": "another-owner/ponytail"},
    {"PONYTAIL_COMMIT": "a" * 40, "PONYTAIL_RELEASE": "v5.0.0"},
])
def test_pin_update_is_not_an_implicit_guard_bypass(gate, changes):
    result = gate(changes=changes, scan=False)
    assert result.returncode == 2
    assert "NOT_VERIFIED:" in result.stderr
    assert "new immutable-source review and full native security acceptance" in result.stderr
    assert "No plugin was installed or enabled" in result.stderr


@pytest.mark.parametrize("missing", [("PONYTAIL_COMMIT",), ("PONYTAIL_RELEASE",), ("PONYTAIL_REPOSITORY",)])
def test_incomplete_pin_cannot_reach_native_installer(gate, missing):
    result = gate(missing=missing)
    assert result.returncode == 2
    assert "NOT_VERIFIED:" in result.stderr


def test_pin_gate_keeps_ponytail_a_required_failed_component():
    source = (ROOT / "scripts/station_deps_install.sh").read_text()
    selection = source.split('if [[ "$ALL" -eq 1 ]]; then', 1)[1].split("fi", 1)[0]
    assert "ponytail" in selection.split("COMPONENTS=(", 1)[1].split(")", 1)[0].split()
    # Aggregate tests exercise that every nonzero Ponytail child is retained and
    # later independent software is attempted. The gate must not remove its row
    # or turn refusal into a successful no-op.
    from agentik_station.full_stack import COMPONENTS
    assert any(component.id == "ponytail" for component in COMPONENTS)
