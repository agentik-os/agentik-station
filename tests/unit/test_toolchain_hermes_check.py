"""Credential-free installation probes; no real Hermes, login or network.

Portable tests execute the production embedded Python with a translated mock
supervisor. Linux/non-root cases also exercise the real bounded process runner.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import types

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/station_toolchain_install.sh"
SOURCE = SCRIPT.read_text()
PROBE_FUNCTION = SOURCE[SOURCE.index("run_version_probe() {"):SOURCE.index("\ncheck_tool() {")]
PROGRAM = PROBE_FUNCTION.split("<<'PY'\n", 1)[1].rsplit("\nPY\n}", 1)[0]
NATIVE_SUPPORTED = sys.platform == "linux" and os.geteuid() != 0
NATIVE_ONLY = pytest.mark.skipif(not NATIVE_SUPPORTED, reason="requires Linux and a non-root operator")
POISON = {
    "HOME": "", "HERMES_HOME": "", "HERMES_PROFILE": "private-profile",
    "OPENAI_API_KEY": "synthetic-private-key", "ANTHROPIC_API_KEY": "synthetic-private-key",
    "CODEX_HOME": "private-codex", "XDG_CONFIG_HOME": "private-config",
    "HERMES_MANAGED_DIR": "private-managed", "HERMES_DEV": "1",
    "NODE_OPTIONS": "--require /private/must-not-load.js",
    "PYTHONPATH": "/private/must-not-import", "PYTHONHOME": "/private/python",
    "BASH_ENV": "/private/must-not-source", "ENV": "/private/must-not-source",
    "LD_PRELOAD": "/private/must-not-load.so", "TMPDIR": "/private/must-not-use",
}


@pytest.fixture
def layout(tmp_path):
    root = tmp_path.resolve()
    home = root / "operator"
    bins = home / ".local/bin"
    bins.mkdir(parents=True)
    profile = home / ".hermes"
    profile.mkdir(mode=0o700)
    for name, content in {".env": "SYNTHETIC_TOKEN=private\n", "config.yaml": "model: private\n",
                          "active_profile": "private-profile\n"}.items():
        path = profile / name
        path.write_text(content)
        path.chmod(0o600)
    return home, bins, root / "observed.json"


def protected_snapshot(home):
    result = {}
    for path in (home / ".hermes").iterdir():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        info = path.stat()
        result[path.name] = (digest, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                             info.st_mtime_ns, info.st_ctime_ns)
    return result


def mutating_stub(layout, *, mode="success"):
    home, bins, observation = layout
    binary = bins / "hermes"
    binary.write_text("#!/usr/bin/python3\n" + f"""
import json, os, pathlib, sys, time
assert sys.argv[1:] == ['--version']
assert sys.stdin.read() == ''
home = pathlib.Path(os.environ['HOME'])
profile = pathlib.Path(os.environ['HERMES_HOME'])
pathlib.Path({str(observation)!r}).write_text(json.dumps({{
    'home': str(home), 'profile': str(profile), 'cwd': os.getcwd(),
    'mode': home.stat().st_mode & 0o777, 'uid': os.geteuid(), 'env': dict(os.environ),
}}))
(profile / '.env').write_text('NORMALIZED=fixture\\n')
(profile / 'config.yaml').write_text('model: normalized\\n')
mode = {mode!r}
if mode == 'failure':
    print('DO_NOT_REPLAY_PROVIDER_FAILURE', file=sys.stderr)
    raise SystemExit(17)
if mode == 'overflow':
    print('x' * 70000)
elif mode == 'empty':
    pass
elif mode == 'control':
    print('bad\\x1b]0;terminal-title\\x07')
elif mode == 'timeout':
    time.sleep(30)
else:
    print('Hermes Agent fixture')
    print('DO_NOT_REPLAY_SECONDARY_OUTPUT')
""")
    binary.chmod(0o755)
    return binary


def portable_probe(monkeypatch, layout, binary, *, fail=None):
    """Only supervision is mocked; the native-like child really executes.

    Translate GNU env --chdir for macOS. Real Linux process-group timeout and
    overflow enforcement are covered separately and are never claimed here.
    """
    home, bins, _ = layout
    observed = {}

    def supervised(command, *, timeout, capture):
        assert (timeout, capture) == (60, True)
        assert command[:2] == ["/usr/bin/env", "-i"]
        assert command[2].startswith("--chdir=")
        private = Path(command[2].partition("=")[2])
        observed["private"] = private
        env = {}
        index = 3
        while "=" in command[index]:
            key, value = command[index].split("=", 1)
            env[key] = value
            index += 1
        observed["env"] = env
        if fail:
            raise fail
        return subprocess.run(command[index:], env=env, cwd=private,
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=5)

    supervisor = types.ModuleType("agentik_station.native_process")
    supervisor.run_bounded_native = supervised
    monkeypatch.setitem(sys.modules, "agentik_station.native_process", supervisor)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "argv", ["-", str(ROOT), pwd.getpwuid(os.geteuid()).pw_name,
                                      str(bins), str(binary), "--version"])
    # Portable CI may run as root: mock only this identity precondition here.
    # A separate test asserts that the actual production root guard rejects.
    if os.geteuid() == 0:
        monkeypatch.setattr(os, "geteuid", lambda: 1001)
        monkeypatch.setattr(pwd, "getpwuid", lambda uid: types.SimpleNamespace(pw_name="root"))
    for key, value in POISON.items():
        monkeypatch.setenv(key, str(home / ".hermes") if key == "HERMES_HOME" else value)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/private/poisoned-path")
    # Keep all test artifacts below pytest's own temporary directory. Production
    # requests an explicit /tmp parent, never the inherited TMPDIR.
    original_temporary = tempfile.TemporaryDirectory

    def temporary(*, prefix, dir):
        assert dir == "/tmp" and prefix == "station-toolchain-check-"
        return original_temporary(prefix=prefix, dir=home.parent)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", temporary)
    try:
        exec(compile(PROGRAM, str(SCRIPT), "exec"), {})
    except SystemExit as error:
        return error.code, observed
    return 0, observed


@pytest.mark.parametrize("mode", ["success", "failure", "empty", "control"])
def test_production_context_does_not_inherit_credentials_or_normalize_operator_files(
    monkeypatch, layout, capsys, mode,
):
    binary = mutating_stub(layout, mode=mode)
    before = protected_snapshot(layout[0])
    status, observed = portable_probe(monkeypatch, layout, binary)
    assert (status == 0) == (mode == "success")
    assert protected_snapshot(layout[0]) == before
    payload = json.loads(layout[2].read_text())
    private = observed["private"]
    assert payload["home"] == payload["cwd"] == str(private)
    assert payload["profile"] == str(private / ".hermes")
    assert payload["mode"] == 0o700
    assert not private.exists()
    assert all(key not in observed["env"] for key in POISON
               if key not in {"HOME", "HERMES_HOME", "HERMES_MANAGED_DIR", "XDG_CONFIG_HOME", "TMPDIR"})
    assert observed["env"]["HERMES_MANAGED_DIR"] == str(private / ".managed")
    assert observed["env"]["PATH"] == f"{layout[1]}:/usr/bin:/bin"
    assert observed["env"]["TMPDIR"] == str(private / "tmp")
    output = capsys.readouterr().out
    assert "DO_NOT_REPLAY" not in output
    assert ("Hermes Agent fixture" in output) == (mode == "success")


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired("DO_NOT_REPLAY_PRIVATE_ARG", 60),
    subprocess.SubprocessError("DO_NOT_REPLAY_PRIVATE_EXCEPTION"),
    InterruptedError("DO_NOT_REPLAY_PRIVATE_INTERRUPT"),
])
def test_supervisor_failure_is_redacted_and_disposable_context_is_removed(
    monkeypatch, layout, capsys, failure,
):
    binary = mutating_stub(layout)
    before = protected_snapshot(layout[0])
    status, observed = portable_probe(monkeypatch, layout, binary, fail=failure)
    assert status == "Isolated version probe failed; no account readiness was checked"
    assert not observed["private"].exists()
    assert protected_snapshot(layout[0]) == before
    assert not layout[2].exists()
    assert "DO_NOT_REPLAY" not in capsys.readouterr().out


@pytest.mark.parametrize("platform,uid,expected", [
    ("darwin", 1001, "require Linux"), ("linux", 0, "non-root operator"),
])
def test_unsupported_host_or_root_fails_before_any_temporary_context(
    monkeypatch, layout, platform, uid, expected,
):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(os, "geteuid", lambda: uid)
    monkeypatch.setattr(sys, "argv", ["-", str(ROOT), "fixture", str(layout[1]), "/bin/false"])
    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda **kwargs: pytest.fail("created context"))
    with pytest.raises(SystemExit, match=expected):
        exec(compile(PROGRAM, str(SCRIPT), "exec"), {})


def test_all_version_and_sdk_probes_use_context_not_account_environment():
    checks = SOURCE[SOURCE.index("check_tool() {"):SOURCE.index("\nlinux_arches() {")]
    assert "as_station" not in checks
    assert checks.count('run_version_probe "$binary" "$@"') == 2
    assert 'run_version_probe "$tool_path/node" -e' in checks
    assert "command -v hermes" not in checks
    assert 'local hermes_binary="$tool_path/hermes"' in checks
    assert "hermes_binary=/usr/local/bin/hermes" in checks
    assert "/usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8" in PROBE_FUNCTION
    assert '/usr/bin/python3 -I -S -B - "$ROOT" "$STATION_USER"' in PROBE_FUNCTION
    assert '"$(/usr/bin/id -un)"' in PROBE_FUNCTION
    assert '/usr/bin/sudo -n -u "$STATION_USER"' in PROBE_FUNCTION


def test_privilege_dispatch_never_resolves_commands_from_operator_path(layout):
    home, bins, _ = layout
    marker = home.parent / "poisoned-command-ran"
    for name in ("id", "env", "sudo", "python3"):
        binary = bins / name
        binary.write_text(f"#!/bin/sh\n: > '{marker}'\nexit 90\n")
        binary.chmod(0o755)
    account = pwd.getpwuid(os.geteuid()).pw_name
    harness = 'set -Eeuo pipefail\nas_station() { exit 91; }\n' + PROBE_FUNCTION
    result = subprocess.run(["/bin/bash", "-c", harness + '\nrun_version_probe /bin/false --version'],
                            env={"PATH": str(bins), "ROOT": str(ROOT), "STATION_USER": account,
                                 "tool_path": str(bins), "HOME": str(home)},
                            cwd=home, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not marker.exists()
    assert "Version checks require" in result.stderr or "Isolated version probe failed" in result.stderr


def test_plan_never_runs_version_context_or_touches_synthetic_home(layout):
    before = protected_snapshot(layout[0])
    marker = layout[0].parent / "poisoned-plan-command-ran"
    cat = layout[1] / "cat"
    cat.write_text(f"#!/bin/sh\n: > '{marker}'\nexit 90\n")
    cat.chmod(0o755)
    result = subprocess.run(["/bin/bash", str(SCRIPT), "--plan"],
                            env={"PATH": "/usr/bin:/bin", "STATION_HOME": str(layout[0])},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert "Authentication: NOT PERFORMED" in result.stdout
    assert protected_snapshot(layout[0]) == before


def native_shell(layout, binary):
    home, bins, _ = layout
    account = pwd.getpwuid(os.geteuid()).pw_name
    harness = 'set -Eeuo pipefail\nas_station() { "$@"; }\n' + PROBE_FUNCTION
    return subprocess.run(["/bin/bash", "-c", harness + '\nrun_version_probe "$BINARY" --version'],
                          env={"PATH": "/usr/bin:/bin", "ROOT": str(ROOT), "STATION_USER": account,
                               "tool_path": str(bins), "BINARY": str(binary),
                               "HOME": str(home), "HERMES_HOME": str(home / ".hermes"),
                               "OPENAI_API_KEY": "synthetic-private-key", "NODE_OPTIONS": "private"},
                          cwd=home, capture_output=True, text=True, timeout=70)


@NATIVE_ONLY
@pytest.mark.parametrize("mode", ["success", "failure", "overflow"])
def test_real_linux_bounded_runner_preserves_profiles_and_cleans_context(layout, mode):
    binary = mutating_stub(layout, mode=mode)
    before = protected_snapshot(layout[0])
    result = native_shell(layout, binary)
    assert (result.returncode == 0) == (mode == "success"), result.stderr
    assert protected_snapshot(layout[0]) == before
    payload = json.loads(layout[2].read_text())
    assert payload["uid"] == os.geteuid() != 0
    assert not Path(payload["home"]).exists()
    assert "OPENAI_API_KEY" not in payload["env"] and "NODE_OPTIONS" not in payload["env"]
    assert "DO_NOT_REPLAY" not in result.stdout + result.stderr


@NATIVE_ONLY
def test_real_linux_timeout_removes_its_context(layout):
    # Keep the production 60-second bound fixed. This test shortens only the
    # supervisor argument in its extracted fixture, never a runtime env override.
    binary = mutating_stub(layout, mode="timeout")
    original = globals()["PROBE_FUNCTION"]
    try:
        globals()["PROBE_FUNCTION"] = original.replace("timeout=60, capture=True", "timeout=0.2, capture=True")
        result = native_shell(layout, binary)
    finally:
        globals()["PROBE_FUNCTION"] = original
    assert result.returncode != 0
    assert "Isolated version probe failed" in result.stderr
    assert not Path(json.loads(layout[2].read_text())["home"]).exists()
