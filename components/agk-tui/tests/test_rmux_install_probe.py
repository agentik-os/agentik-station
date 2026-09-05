"""Temp-only RMUX installer probes; no native daemon, install, or sudo runs."""
import getpass
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
SOURCE = INSTALLER.read_text()
PROBE = SOURCE[SOURCE.index("rmux_works_for_target() {"):SOURCE.index("\nexpose_working_rmux()")]
PYTHON_PROBE = PROBE.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
CAPABILITIES = {
    "version": "0.10.0", "wire_version": 8, "binary_contract_version": 1,
    "capabilities": ["protocol.capabilities", "protocol.framed_errors", "rpc.detached"],
}


@pytest.fixture
def probe(tmp_path):
    candidate = tmp_path / "rmux"
    candidate.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
with open(os.environ["RMUX_TEST_CALLS"], "a") as output:
    output.write(json.dumps({"argv": sys.argv[1:], "home": os.environ["HOME"]}) + "\\n")
data = json.loads(os.environ["RMUX_TEST_DATA"])
if sys.argv[1:] == ["capabilities", "--json"]:
    print(data["caps"])
    raise SystemExit(data["caps_rc"])
if sys.argv[1:] == ["list-sessions"]:
    sys.stdout.write(data["stdout"])
    sys.stderr.write(data["stderr"])
    raise SystemExit(data["rc"])
raise SystemExit(99)
''')
    candidate.chmod(0o755)
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/bin/sh\n[ "$1" = -u ] || exit 98\nshift 2\nexec "$@"\n')
    sudo.chmod(0o755)
    (tmp_path / "python3").symlink_to(sys.executable)
    calls = tmp_path / "calls.jsonl"
    endpoint = tmp_path / "no-daemon.sock"

    def run(*, caps=None, caps_rc=0, rc=1, stdout="", stderr=None, other_user=False):
        data = {"caps": json.dumps(CAPABILITIES if caps is None else caps), "caps_rc": caps_rc,
                "rc": rc, "stdout": stdout,
                "stderr": f"no server running on {endpoint}\n" if stderr is None else stderr}
        env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
                   RMUX_TEST_DATA=json.dumps(data), RMUX_TEST_CALLS=str(calls),
                   PROBE_CANDIDATE=str(candidate), PROBE_HOME=str(tmp_path / "operator-home"),
                   PROBE_USER="fixture-other-user" if other_user else getpass.getuser())
        script = 'set -euo pipefail\ntarget_user="$PROBE_USER"\ntarget_home="$PROBE_HOME"\nrmux_version=0.10.0\n'
        script += PROBE + '\nrmux_works_for_target "$PROBE_CANDIDATE"\n'
        result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=5)
        recorded = [json.loads(line) for line in calls.read_text().splitlines()]
        assert all(item["home"] == env["PROBE_HOME"] for item in recorded)
        assert all(item["argv"] in [["capabilities", "--json"], ["list-sessions"]] for item in recorded)
        return result

    return run, endpoint


@pytest.mark.parametrize("other_user", [False, True])
def test_fresh_account_is_idle_without_creating_a_session(probe, other_user):
    run, endpoint = probe
    result = run(other_user=other_user)
    assert result.returncode == 0, result.stderr
    assert "IDLE (no daemon started or verified)" in result.stdout
    assert not endpoint.exists()


def test_live_daemon_requires_successful_protocol_readback(probe):
    run, _ = probe
    result = run(rc=0, stdout="private-session-name\n", stderr="")
    assert result.returncode == 0
    assert "existing daemon protocol verified" in result.stdout
    assert "private-session-name" not in result.stdout


@pytest.mark.parametrize("change", [{"version": "0.9.0"}, {"wire_version": 7},
                                   {"binary_contract_version": True}, {"capabilities": []},
                                   {"capabilities": [None]}])
def test_idle_does_not_accept_incompatible_binary(probe, change):
    run, _ = probe
    assert run(caps={**CAPABILITIES, **change}).returncode == 1


def test_capabilities_command_failure_is_not_an_idle_install(probe):
    run, _ = probe
    assert run(caps_rc=1).returncode == 1


@pytest.mark.parametrize("rc,stdout,stderr", [
    (2, "", None), (1, "unexpected output", None),
    (1, "", "permission denied\n"), (1, "", "unsupported RMUX wire version 7\n"),
    (1, "", "rmux: running daemon uses an incompatible protocol\n"),
    (1, "", "no server running on /tmp/missing\nadditional diagnostic\n"),
    (1, "", "no server running on relative-path\n"),
])
def test_only_exact_native_absence_is_idle(probe, rc, stdout, stderr):
    run, _ = probe
    assert run(rc=rc, stdout=stdout, stderr=stderr).returncode == 1


@pytest.mark.parametrize("kind", ["file", "directory", "dangling-symlink"])
def test_existing_endpoint_is_preserved_and_rejected(probe, kind):
    run, endpoint = probe
    if kind == "file":
        endpoint.write_text("preserve")
    elif kind == "directory":
        endpoint.mkdir()
    else:
        endpoint.symlink_to(endpoint.parent / "missing")
    assert run().returncode == 1
    assert os.path.lexists(endpoint)


def test_socket_endpoint_is_rejected_without_starting_any_daemon(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["-", "/fixture/rmux", "0.10.0"])

    def fake_run(argv, **kwargs):
        if argv[1] == "capabilities":
            return subprocess.CompletedProcess(argv, 0, json.dumps(CAPABILITIES), "")
        assert argv[1:] == ["list-sessions"]
        return subprocess.CompletedProcess(argv, 1, "", "no server running on /fixture/socket\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Socket creation is forbidden in some CI sandboxes; supply its lstat result.
    monkeypatch.setattr(os, "lstat", lambda path: os.stat_result((stat.S_IFSOCK, 0, 0, 1, 0, 0, 0, 0, 0, 0)))
    with pytest.raises(SystemExit) as error:
        exec(compile(PYTHON_PROBE, str(INSTALLER), "exec"), {})
    assert error.value.code == 1


@pytest.mark.parametrize("timeout_command", ["capabilities", "list-sessions"])
def test_native_probes_are_time_bounded_and_fail_closed(monkeypatch, timeout_command):
    monkeypatch.setattr(sys, "argv", ["-", "/fixture/rmux", "0.10.0"])

    def fake_run(argv, **kwargs):
        assert kwargs["timeout"] == (10 if argv[1] == "capabilities" else 20)
        if argv[1] == timeout_command:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0, json.dumps(CAPABILITIES), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as error:
        exec(compile(PYTHON_PROBE, str(INSTALLER), "exec"), {})
    assert error.value.code == 1


def test_installer_checks_python_before_rmux_and_keeps_shell_syntax():
    assert SOURCE.index("command -v python3") < SOURCE.index("\ninstall_rmux\n")
    subprocess.run(["bash", "-n", str(INSTALLER)], check=True)
