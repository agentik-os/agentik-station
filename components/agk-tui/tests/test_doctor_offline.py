"""Static Doctor must neither initialize runtimes nor turn optional accounts into core gates."""

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts/doctor.sh"


@pytest.fixture
def installation(tmp_path):
    prefix = tmp_path / "prefix with spaces"
    root = prefix / "lib/agk-terminal"
    calls = tmp_path / "forbidden-calls"
    trap = '#!/bin/sh\nprintf "called\\n" >> "$DOCTOR_CALLS"\nexit 92\n'
    for relative in (
        "bin/agk", "bin/agk-terminal", "lib/agk-terminal/bin/agk-tui",
        "lib/agk-terminal/scripts/agk_control.py", "lib/agk-terminal/scripts/provider.sh",
        "lib/agk-terminal/bin/rmux", "lib/agk-terminal/venv/bin/python",
    ):
        path = prefix / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(trap)
        path.chmod(0o755)
    for name in ("hermes", "claude", "codex", "opencode", "composio", "curl", "sudo", "python3"):
        path = prefix / "bin" / name
        path.write_text(trap)
        path.chmod(0o755)
    for name in ("rules.yaml", "providers.yaml", "topology.yaml"):
        path = root / "config" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("version: 1\n")
    (root / "venv/pyvenv.cfg").write_text("home = /usr/bin\n")
    site = root / "venv/lib/python3.13/site-packages"
    for name, version, module in (
        ("PyYAML", "6.0.3", "yaml/__init__.py"),
        ("pillow", "12.3.0", "PIL/Image.py"),
    ):
        metadata = site / f"{name.lower()}-{version}.dist-info/METADATA"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(f"Name: {name}\nVersion: {version}\n")
        source = site / module
        source.parent.mkdir(parents=True)
        source.write_text("raise RuntimeError('must never import installed dependency')\n")
    # Neither account files nor venv startup hooks may be read/executed.
    (site / "unsafe.pth").write_text("import os; os.abort()\n")
    return root, calls


def run_doctor(root, calls, *args):
    return subprocess.run(
        ["/bin/bash", str(DOCTOR), *args],
        env={"AGK_TERMINAL_ROOT": str(root), "DOCTOR_CALLS": str(calls),
             "PATH": str(root.parent.parent / "bin"), "PYTHONPATH": str(root)},
        capture_output=True, text=True, timeout=15,
    )


def test_offline_inventory_does_not_execute_installed_code_or_need_home(installation):
    root, calls = installation
    before = {path.relative_to(root) for path in root.rglob("*")}
    result = run_doctor(root, calls, "--offline")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCOPE: INSTALLATION_ONLY" in result.stdout
    assert "RESULT: INSTALLATION_FILES_PRESENT" in result.stdout
    assert "NOT_CHECKED: RMUX daemon/protocol" in result.stdout
    assert "dependency imports" in result.stdout
    assert "authentication, Discord/chat, external services" in result.stdout
    assert not calls.exists()
    assert before == {path.relative_to(root) for path in root.rglob("*")}


@pytest.mark.parametrize("relative", [
    "bin/agk-tui", "scripts/agk_control.py", "scripts/provider.sh", "bin/rmux",
    "venv/bin/python", "venv/pyvenv.cfg", "config/rules.yaml", "config/providers.yaml",
    "config/topology.yaml", "venv/lib/python3.13/site-packages/yaml/__init__.py",
    "venv/lib/python3.13/site-packages/PIL/Image.py",
    "venv/lib/python3.13/site-packages/pyyaml-6.0.3.dist-info/METADATA",
])
def test_missing_core_file_fails_without_runtime_probes(installation, relative):
    root, calls = installation
    (root / relative).unlink()
    result = run_doctor(root, calls, "--offline")
    assert result.returncode == 1
    assert "RESULT: INSTALLATION_FILES_MISSING_OR_INVALID" in result.stdout
    assert not calls.exists()


@pytest.mark.parametrize("name", ["agk", "agk-terminal"])
def test_missing_private_entrypoint_fails(installation, name):
    root, calls = installation
    (root.parent.parent / "bin" / name).unlink()
    assert run_doctor(root, calls, "--offline").returncode == 1


def test_legitimate_rmux_and_python_symlinks_are_inventory_supported(installation):
    root, calls = installation
    for relative in ("bin/rmux", "venv/bin/python"):
        path = root / relative
        target = path.with_name(path.name + "-native")
        path.rename(target)
        path.symlink_to(target.name)
    assert run_doctor(root, calls, "--offline").returncode == 0
    assert not calls.exists()


def test_core_binary_without_execute_permission_fails(installation):
    root, calls = installation
    (root / "bin/agk-tui").chmod(0o644)
    result = run_doctor(root, calls, "--offline")
    assert result.returncode == 1
    assert "FAIL: native AGK TUI file" in result.stdout
    assert not calls.exists()


def test_mismatched_dependency_metadata_fails_without_disclosure(installation):
    root, calls = installation
    metadata = root / "venv/lib/python3.13/site-packages/pyyaml-6.0.3.dist-info/METADATA"
    metadata.write_text("Name: PyYAML\nVersion: PRIVATE_WRONG_VERSION\n")
    result = run_doctor(root, calls, "--offline")
    assert result.returncode == 1
    assert "FAIL: PyYAML 6.0.3 distribution files" in result.stdout
    assert "PRIVATE_WRONG_VERSION" not in result.stdout + result.stderr


def test_dependency_inventory_has_a_directory_count_bound(installation):
    root, calls = installation
    library = root / "venv/lib"
    for index in range(33):
        (library / f"unexpected-{index}").mkdir()
    result = run_doctor(root, calls, "--offline")
    assert result.returncode == 1
    assert "FAIL: PyYAML 6.0.3 distribution files" in result.stdout
    assert not calls.exists()


@pytest.mark.parametrize("kind", ["empty", "oversized", "symlink", "fifo", "nonutf8"])
def test_config_reads_are_bounded_and_never_disclose_content(installation, kind):
    root, calls = installation
    config = root / "config/rules.yaml"
    config.unlink()
    if kind == "empty":
        config.write_text("")
    elif kind == "oversized":
        config.write_bytes(b"PRIVATE_CONTENT" * 100_000)
    elif kind == "symlink":
        target = config.with_name("private.yaml")
        target.write_text("PRIVATE_CONTENT")
        config.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(config)
    else:
        config.write_bytes(b"PRIVATE_CONTENT\xff")
    result = run_doctor(root, calls, "--offline")
    assert result.returncode == 1
    assert "PRIVATE_CONTENT" not in result.stdout + result.stderr
    assert not calls.exists()


@pytest.mark.parametrize("args,code", [
    (("--help",), 0), (("-h",), 0), (("unknown-private-value",), 2),
    (("--offline", "--full"), 2),
])
def test_argument_handling_happens_before_any_environment_initialization(tmp_path, args, code):
    result = run_doctor(tmp_path / "nonexistent", tmp_path / "calls", *args)
    assert result.returncode == code
    assert "usage: agk doctor" in result.stdout + result.stderr
    assert "unknown-private-value" not in result.stdout + result.stderr
    assert "SCOPE:" not in result.stdout
    assert not (tmp_path / "calls").exists()


def test_dependency_inventory_pins_match_install_requirements():
    source = DOCTOR.read_text()
    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    for requirement in requirements:
        name, version = requirement.split("==")
        assert f'"{name.lower()}", "{version}"' in source.lower()


def test_default_strict_checks_remain_the_existing_full_diagnostic():
    # Preserve its optional-provider/cloud failures instead of moving them to
    # warnings. Only the explicit static branch is allowed to skip probes.
    source = DOCTOR.read_text()
    strict = source.split("install_root=${AGK_TERMINAL_ROOT:", 1)[1]
    assert "check 'RMUX daemon' rmux list-sessions" in strict
    assert "check 'Agentik OS cloud' curl -fsSIL --max-time 10 https://agentik-os.com" in strict
    assert "check 'Discord gateway' discord_connected" in strict
    assert "check 'Claude Code'" in strict
    assert "check 'Composio authentication' composio_authenticated" in strict
    assert 'failed=1' in strict
    assert 'exit "$failed"' in strict
