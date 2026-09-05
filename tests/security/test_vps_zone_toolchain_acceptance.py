"""Execute only acceptance probe code with strict fakes; never run Host gates."""
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci_vps_acceptance.sh"
SOURCE = SCRIPT.read_text().split("<<'PY_ZONE_TOOLS'\n", 1)[1].split("\nPY_ZONE_TOOLS\n", 1)[0]
PROBE = {"__name__": "acceptance_probe_test"}
exec(compile(SOURCE, str(SCRIPT), "exec"), PROBE)
PINS = {key: "1.2.3" for key in PROBE["TOOLS"].values()}
RECORD = {"id": "dev", "category": "AGENTIK", "placement": "local", "unix_user": "z-agentik-dev",
          "state_root": "/var/lib/station/zones/dev", "hermes_home": "/var/lib/station/zones/dev/hermes"}
EXPECTED = {"uid": 61001, "gid": 61002, "home": RECORD["state_root"] + "/home",
            "hermes_home": RECORD["hermes_home"]}


@pytest.fixture
def account(monkeypatch):
    entry = SimpleNamespace(pw_name=RECORD["unix_user"], pw_uid=EXPECTED["uid"], pw_gid=EXPECTED["gid"],
                            pw_dir=EXPECTED["home"])
    monkeypatch.setattr(pwd, "getpwnam", lambda name: entry if name == entry.pw_name else pytest.fail("wrong account"))
    return entry


def test_parent_runs_one_real_zone_with_clean_private_home_and_no_network(account, monkeypatch, capsys):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[:8] == ["/usr/bin/unshare", "--net", "--", "/usr/sbin/runuser", "--user",
                               RECORD["unix_user"], "--", "/usr/bin/env"]
        assert command[8] == "-i"
        assert "HOME=" + EXPECTED["home"] in command
        assert "HERMES_HOME=" + EXPECTED["hermes_home"] in command
        assert "PATH=/usr/local/bin:/usr/bin:/bin" in command
        assert command[-6:-3] == ["-I", "-B", "-c"]
        assert command[-3] == PROBE["ZONE_TOOL_PROBE"]
        assert json.loads(command[-2]) == EXPECTED
        assert set(json.loads(command[-1])) == set(PROBE["TOOLS"])
        assert kwargs == {"cwd": "/", "stdin": subprocess.DEVNULL, "capture_output": True,
                          "text": True, "timeout": 360}
        return SimpleNamespace(returncode=0, stdout="sensitive-native-output", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    PROBE["verify_zone_tools"](RECORD, PINS)
    assert len(calls) == 1
    output = capsys.readouterr().out
    assert "PASS: real Zone public toolchain" in output
    assert "sensitive-native-output" not in output


@pytest.mark.parametrize("failure", ["exit", "timeout", "os-error"])
def test_parent_fails_closed_without_exposing_child_output(account, monkeypatch, failure, capsys):
    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("synthetic", 360, output="private-output")
        if failure == "os-error":
            raise OSError("private-output")
        return SimpleNamespace(returncode=1, stdout="private-output", stderr="private-output")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError) as error:
        PROBE["verify_zone_tools"](RECORD, PINS)
    assert "private-output" not in str(error.value)
    assert "PASS:" not in capsys.readouterr().out


@pytest.mark.parametrize("defect", ["root", "wrong-home", "missing-pin", "malformed-pin"])
def test_invalid_identity_or_pins_never_start_a_child(account, monkeypatch, defect):
    pins = dict(PINS)
    if defect == "root":
        account.pw_uid = 0
    elif defect == "wrong-home":
        account.pw_dir = "/home/agk-station"
    elif defect == "missing-pin":
        pins.pop("NODE_VERSION")
    else:
        pins["NODE_VERSION"] = "1.2.3; command"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("unsafe probe started"))
    with pytest.raises(ValueError):
        PROBE["verify_zone_tools"](RECORD, pins)


def test_zone_selection_prefers_engineering_but_accepts_client_only_hosts():
    client = {**RECORD, "id": "acme-prod", "category": "ORGANIZATIONS"}
    system = {**RECORD, "id": "station-maintainer", "category": "SYSTEM"}
    remote = {**RECORD, "id": "remote-dev", "placement": "REMOTE_DESIRED_NOT_APPLIED"}
    assert PROBE["select_zone"]([client, system, RECORD, remote]) == RECORD
    assert PROBE["select_zone"]([remote, system, client]) == client
    with pytest.raises(ValueError):
        PROBE["select_zone"]([system, remote])


@pytest.fixture
def child(monkeypatch):
    environment = {"HOME": EXPECTED["home"], "HERMES_HOME": EXPECTED["hermes_home"],
                   "PATH": "/usr/local/bin:/usr/bin:/bin", "CI": "1"}
    monkeypatch.setattr(os, "environ", environment)
    monkeypatch.setattr(os, "getuid", lambda: EXPECTED["uid"])
    monkeypatch.setattr(os, "getgid", lambda: EXPECTED["gid"])
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/" + name)
    versions = {name: PINS[key] for name, key in PROBE["TOOLS"].items()}
    monkeypatch.setattr(sys, "argv", ["probe", json.dumps(EXPECTED), json.dumps(versions)])
    return environment


def run_child():
    exec(compile(PROBE["ZONE_TOOL_PROBE"], "zone-cli-probe", "exec"), {"__name__": "__main__"})


def test_child_checks_all_public_pins_and_preserves_zone_environment(child, monkeypatch, capsys):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert argv == ["/usr/local/bin/" + Path(argv[0]).name, "--version"]
        assert kwargs["env"] == child
        assert kwargs["env"]["HOME"] == EXPECTED["home"]
        assert kwargs["cwd"] == "/" and kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 30
        return SimpleNamespace(returncode=0, stdout="native v1.2.3\n", stderr="unused-private-output")

    monkeypatch.setattr(subprocess, "run", run)
    run_child()
    assert [Path(argv[0]).name for argv in calls] == list(PROBE["TOOLS"])
    assert "unused-private-output" not in capsys.readouterr().out


@pytest.mark.parametrize("name", list(PROBE["TOOLS"]))
def test_child_rejects_any_wrong_native_version_without_printing_it(child, monkeypatch, name, capsys):
    def run(argv, **kwargs):
        version = "1.2.3.4" if Path(argv[0]).name == name else "1.2.3"
        return SimpleNamespace(returncode=0, stdout="private-output " + version, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match=name) as error:
        run_child()
    assert "private-output" not in str(error.value) + capsys.readouterr().out


@pytest.mark.parametrize("failure", ["missing", "operator-path", "exit", "timeout", "os-error"])
def test_child_rejects_unreachable_or_failed_cli(child, monkeypatch, failure):
    if failure == "missing":
        monkeypatch.setattr(shutil, "which", lambda name: None)
    elif failure == "operator-path":
        monkeypatch.setattr(shutil, "which", lambda name: "/home/agk-station/.local/bin/" + name)

    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("synthetic", 30, output="private-output")
        if failure == "os-error":
            raise OSError("private-output")
        return SimpleNamespace(returncode=1, stdout="1.2.3 private-output", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises((RuntimeError, AssertionError)) as error:
        run_child()
    assert "private-output" not in str(error.value)


@pytest.mark.parametrize("field", ["HOME", "HERMES_HOME", "PATH", "uid", "gid"])
def test_child_validates_actual_identity_and_home_before_running_tools(child, monkeypatch, field):
    if field == "uid":
        monkeypatch.setattr(os, "getuid", lambda: 0)
    elif field == "gid":
        monkeypatch.setattr(os, "getgid", lambda: 0)
    else:
        child[field] = "/home/agk-station"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("invalid identity ran a CLI"))
    with pytest.raises(AssertionError):
        run_child()


def test_acceptance_gate_precedes_evidence_publication_and_shell_is_valid():
    source = SCRIPT.read_text()
    assert source.index("<<'PY_ZONE_TOOLS'") < source.index('--profile "$PROFILE"')
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True, timeout=5)
