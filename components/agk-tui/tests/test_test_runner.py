import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_runner_help_has_no_build_or_install_side_effects():
    result = subprocess.run(["bash", str(ROOT / "scripts/test.sh"), "--help"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "--offline" in result.stdout
    assert "private source copy" in result.stdout


@pytest.mark.parametrize("fail_cargo", [False, True])
def test_runner_builds_in_disposable_copy_and_preserves_authored_assets(tmp_path, fail_cargo):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls"
    cargo = fake_bin / "cargo"
    cargo.write_text(
        '#!/bin/sh\nprintf "cargo %s %s\\n" "$CARGO_TARGET_DIR" "$*" >> "$AGK_TEST_CALLS"\n'
        'test "$AGK_TEST_FAIL_CARGO" = no\n', encoding="utf-8")
    uv = fake_bin / "uv"
    uv.write_text('#!/bin/sh\nprintf "uv %s\\n" "$*" >> "$AGK_TEST_CALLS"\n', encoding="utf-8")
    npm = fake_bin / "npm"
    npm.write_text(
        '#!/bin/sh\nprintf "npm %s %s\\n" "$PWD" "$*" >> "$AGK_TEST_CALLS"\n'
        'test -f ../../hermes/plugins/agentik_os/dashboard/dist/index.js || exit 7\n'
        'test -f ../../hermes/plugins/agentik_os/dashboard/dist/style.css || exit 7\n'
        'if [ "$*" = "run build" ]; then mkdir -p server-dist; printf "// fixture\\n" > server-dist/server.js; fi\n',
        encoding="utf-8")
    for command in (cargo, uv, npm):
        command.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
           "AGK_TEST_CALLS": str(calls), "AGK_TEST_FAIL_CARGO": "yes" if fail_cargo else "no"}
    before = {path: path.read_bytes() for path in (
        ROOT / "apps/hermes-fleet/package-lock.json",
        ROOT / "hermes/plugins/agentik_os/dashboard/dist/index.js",
    )}
    result = subprocess.run(["bash", str(ROOT / "scripts/test.sh"), "--offline"],
                            capture_output=True, text=True, env=env, timeout=30)
    assert (result.returncode != 0) == fail_cargo, result.stderr
    lines = calls.read_text().splitlines()
    temporary = Path(lines[0].split(" ", 2)[1]).parent
    assert not temporary.exists()
    assert not temporary.is_relative_to(ROOT)
    assert all(path.read_bytes() == content for path, content in before.items())
    if not fail_cargo:
        assert any("pytest==8.4.2" in line and "--offline" in line for line in lines)
        assert any(line.startswith("npm ") and "--offline --ignore-scripts" in line for line in lines)
        assert "external accounts, live chat and service acceptance were not exercised" in result.stdout


def test_missing_rust_sources_fail_without_claiming_complete_verification(tmp_path):
    scripts = tmp_path / "component/scripts"
    scripts.mkdir(parents=True)
    runner = scripts / "test.sh"
    shutil.copyfile(ROOT / "scripts/test.sh", runner)
    result = subprocess.run(["bash", str(runner), "--offline"], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 2
    assert "Native Rust TUI source is absent" in result.stderr
