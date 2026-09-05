import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync-hermes.sh"


@pytest.fixture
def sync_fixture(tmp_path):
    install_root = tmp_path / "installation"
    for relative in (
        "hermes/plugins/agentik_os",
        "hermes/plugins/platforms/discord",
        "agents/master-os-builder",
    ):
        directory = install_root / relative
        directory.mkdir(parents=True)
        (directory / "fixture.txt").write_text("fixture\n", encoding="utf-8")
    themes = install_root / "hermes/dashboard-themes"
    themes.mkdir()
    for name in ("agentik-shadcn.yaml", "agentik-shadcn-light.yaml"):
        (themes / name).write_text("name: fixture\n", encoding="utf-8")
    scripts = install_root / "scripts"
    scripts.mkdir()
    (scripts / "sync-rules.py").write_text("pass\n", encoding="utf-8")
    fallback_python = install_root / "venv/bin/python"
    fallback_python.parent.mkdir(parents=True)
    fallback_python.symlink_to(sys.executable)

    user_root = tmp_path / "operator"
    local_bin = user_root / ".local/bin"
    local_bin.mkdir(parents=True)
    fixture_bin = tmp_path / "bin"
    fixture_bin.mkdir()
    (fixture_bin / "python3").symlink_to(sys.executable)
    calls = tmp_path / "hermes-calls.txt"
    env = {
        "HOME": str(user_root),
        "HERMES_HOME": str(user_root / ".hermes"),
        "AGK_TERMINAL_ROOT": str(install_root),
        "AGK_TEST_HERMES_CALLS": str(calls),
        "PATH": f"{local_bin}:{fixture_bin}:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return local_bin / "hermes", fixture_bin, calls, env


def write_launcher(path):
    path.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$AGK_TEST_HERMES_CALLS"\n',
        encoding="utf-8",
    )
    path.chmod(0o700)


def run_sync(env):
    return subprocess.run(
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_sync_preserves_same_path_regular_launcher_on_repeated_runs(sync_fixture):
    launcher, _, calls, env = sync_fixture
    write_launcher(launcher)
    original = launcher.read_bytes()
    original_inode = launcher.stat().st_ino

    for _ in range(2):
        result = run_sync(env)
        assert result.returncode == 0, result.stderr
        assert not launcher.is_symlink()
        assert launcher.read_bytes() == original
        assert launcher.stat().st_ino == original_inode
    assert calls.read_text().splitlines().count("config migrate") == 2


@pytest.mark.parametrize("relative_link", [False, True])
def test_sync_links_valid_external_launcher_and_can_repeat(sync_fixture, relative_link):
    launcher, fixture_bin, calls, env = sync_fixture
    external = fixture_bin / "hermes-runtime"
    write_launcher(external)
    if relative_link:
        (fixture_bin / "hermes").symlink_to("hermes-runtime")
    else:
        external.rename(fixture_bin / "hermes")
        external = fixture_bin / "hermes"

    for _ in range(2):
        result = run_sync(env)
        assert result.returncode == 0, result.stderr
        assert launcher.is_symlink()
        assert launcher.resolve() == external.resolve()
    assert calls.read_text().splitlines().count("config migrate") == 2


@pytest.mark.parametrize("invalid_kind", ["missing", "nonexecutable", "self-link", "cycle"])
def test_sync_rejects_invalid_launcher_without_syncing(sync_fixture, invalid_kind):
    launcher, fixture_bin, calls, env = sync_fixture
    if invalid_kind == "nonexecutable":
        launcher.write_text("not executable\n", encoding="utf-8")
    elif invalid_kind == "self-link":
        launcher.symlink_to("hermes")
    elif invalid_kind == "cycle":
        launcher.symlink_to(fixture_bin / "loop")
        (fixture_bin / "loop").symlink_to(launcher)

    result = run_sync(env)

    assert result.returncode != 0
    assert "Hermes executable" in result.stderr
    assert not calls.exists()
    assert not (Path(env["HERMES_HOME"]) / "plugins").exists()
    if invalid_kind in {"self-link", "cycle"}:
        assert launcher.is_symlink()


def test_sync_rejects_directory_in_place_of_launcher(sync_fixture):
    launcher, fixture_bin, calls, env = sync_fixture
    launcher.mkdir()
    write_launcher(fixture_bin / "hermes")

    result = run_sync(env)

    assert result.returncode != 0
    assert "Hermes launcher" in result.stderr
    assert launcher.is_dir()
    assert list(launcher.iterdir()) == []
    assert not calls.exists()


def test_sync_delivers_importable_canonical_routing_helper(sync_fixture):
    launcher, _, _, env = sync_fixture
    write_launcher(launcher)
    source = SCRIPT.parents[1] / "hermes/plugins/agentik_os/canonical_routing.py"
    copied = Path(env["AGK_TERMINAL_ROOT"]) / "hermes/plugins/agentik_os/canonical_routing.py"
    shutil.copyfile(source, copied)
    result = run_sync(env)
    assert result.returncode == 0, result.stderr
    installed = Path(env["HERMES_HOME"]) / "plugins/agentik_os/canonical_routing.py"
    assert installed.read_bytes() == source.read_bytes()
    probe = subprocess.run([
        sys.executable, "-I", "-B", "-c",
        "import importlib.util,json,sys; "
        "spec=importlib.util.spec_from_file_location('routing',sys.argv[1]); "
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        "print(json.dumps(module.canonical_handoff('builder-os',zone='os',instance='builder')))",
        str(installed),
    ], capture_output=True, text=True, check=False, timeout=10)
    assert probe.returncode == 0, probe.stderr
    handoff = json.loads(probe.stdout)
    assert handoff["agent"] == "builder-os" and not handoff["executed"]
