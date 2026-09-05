"""Native probes are tested through a supervised fake process, never accounts."""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

import agentik_station.native_process as native_process


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("dependency_probe_under_test", ROOT / "scripts/station_dependency_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pins():
    return {"STRIX_VERSION": "1.6.1", "AI_PYTHON_VERSION": "3.13.15",
            "HONCHO_PYTHON_VERSION": "2.4.0", "HINDSIGHT_PYTHON_VERSION": "0.9.2",
            "LANGFUSE_PYTHON_VERSION": "4.5.0", "CRAWL4AI_PYTHON_VERSION": "0.9.3",
            "SCRAPEGRAPHAI_VERSION": "2.2.2", "PLAYWRIGHT_VERSION": "1.62.0"}


def test_native_hermes_pins_are_independent_of_operator_sdk_versions(probe, pins):
    argv = probe.command(ROOT, Path("/fixture/operator"), "hermes-clients", pins)
    assert argv[:4] == ["/opt/station/tools/hermes/current/venv/bin/python", "-I", "-B", "-c"]
    expected = {
        "honcho-ai": "2.2.0", "hindsight-client": "0.6.1", "mcp": "2.0.0",
        "httpx2": "2.7.0", "starlette": "1.3.1", "langfuse": pins["LANGFUSE_PYTHON_VERSION"],
    }
    assert f"expected={expected!r}" in argv[-1]
    assert "sys.version_info[:2] == (3, 11)" in argv[-1]
    assert "_ensure_mcp_sdk()" in argv[-1]
    assert "Langfuse(" not in argv[-1]
    assert "memory setup" not in argv[-1]


@pytest.mark.parametrize("component,package,version", [
    ("honcho", "honcho-ai", "2.4.0"), ("hindsight", "hindsight-client", "0.9.2"),
])
def test_operator_sdk_probes_use_their_own_interpreters(probe, pins, component, package, version):
    home = Path("/fixture/operator")
    argv = probe.command(ROOT, home, component, pins)
    assert argv[0] == str(home / ".local/share/agentik-station/venvs" / f"{component}-py3.13.15" / "bin/python")
    assert f"expected={{{package!r}: {version!r}}}" in argv[-1]
    assert argv[1:4] == ["-I", "-B", "-c"]


def test_unknown_probe_cannot_select_arbitrary_command(probe, pins):
    with pytest.raises(ValueError, match="Unknown"):
        probe.command(ROOT, Path("/fixture/operator"), "../shell", pins)


@pytest.mark.parametrize("component,version", [("crawl4ai", "0.9.3"), ("scrapegraphai", "2.2.2")])
def test_web_worker_receives_health_json_without_process_stdin(probe, pins, monkeypatch, component, version):
    argv = probe.command(ROOT, Path("/fixture/operator"), component, pins)
    assert argv[:4] == [
        f"/opt/station/tools/web/{component}-{version}-py3.13.15-pw1.62.0/venv/bin/python",
        "-I", "-B", "-c",
    ]
    worker = ROOT / "components/agk-tui/hermes/plugins/agentik_os/scrapegraph_runner.py"
    observed = []

    def run_worker(path, *, run_name):
        observed.append((path, run_name, json.load(sys.stdin), sys.path[0]))

    monkeypatch.setattr(runpy, "run_path", run_worker)
    monkeypatch.setattr(sys, "path", list(sys.path))
    # A supervisor supplies DEVNULL, not a health request. The launch code must
    # supply the request itself before invoking the reviewed worker's main.
    with open(os.devnull) as empty:
        monkeypatch.setattr(sys, "stdin", empty)
        exec(argv[-1], {})
    assert observed == [(str(worker), "__main__", {"component": component, "health": True}, str(worker.parent))]


@pytest.fixture
def invocation(tmp_path, monkeypatch, probe, pins):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config/versions.lock").write_text("".join(f"{key}={value}\n" for key, value in pins.items()))
    private = tmp_path / "probe-home"
    private.mkdir(mode=0o700)
    account_home = tmp_path / "operator-account"
    account_home.mkdir()
    sentinel = account_home / ".env"
    sentinel.write_text("PRIVATE_SENTINEL=do-not-inspect\n")
    before = sentinel.read_bytes()

    @contextlib.contextmanager
    def temporary_directory(*, prefix, dir):
        assert prefix == "station-dependency-probe-" and dir == "/tmp"
        yield str(private)

    monkeypatch.setattr(probe.tempfile, "TemporaryDirectory", temporary_directory)
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1001)
    monkeypatch.setattr(probe.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(account_home)))
    monkeypatch.setattr(probe.sys, "platform", "linux")
    monkeypatch.setattr(probe.sys, "path", list(probe.sys.path))
    monkeypatch.setattr(probe.sys, "argv", ["probe", str(repo), "hermes-clients"])
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE_SENTINEL")
    monkeypatch.setenv("HONCHO_API_KEY", "PRIVATE_SENTINEL")
    monkeypatch.setenv("HINDSIGHT_API_KEY", "PRIVATE_SENTINEL")
    monkeypatch.setenv("PYTHONPATH", "/untrusted/imports")
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"SOFTWARE_IMPORT_OK\n", stderr=b"")

    monkeypatch.setattr(native_process, "run_bounded_native", run)
    yield SimpleNamespace(probe=probe, calls=calls, private=private, account_home=account_home,
                          repo=repo, run=run)
    assert sentinel.read_bytes() == before


def test_probe_runs_in_clean_private_home_with_bounded_supervision(invocation, capsys):
    assert invocation.probe.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {"component": "hermes-clients", "software_verified": True, "account_checked": False}
    argv, options = invocation.calls[0]
    assert argv[:3] == ["/usr/bin/env", "-i", f"--chdir={invocation.private}"]
    assignments = argv[3:argv.index("/opt/station/tools/hermes/current/venv/bin/python")]
    environment = dict(value.split("=", 1) for value in assignments)
    assert environment["HOME"] == str(invocation.private)
    for name in ("HERMES_HOME", "HERMES_MANAGED_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TMPDIR"):
        target = Path(environment[name])
        assert target.parent == invocation.private
        assert target.stat().st_mode & 0o777 == 0o700
    assert all("PRIVATE_SENTINEL" not in value and str(invocation.account_home) not in value for value in argv)
    assert not {"HONCHO_API_KEY", "HINDSIGHT_API_KEY", "OPENAI_API_KEY", "PYTHONPATH"} & environment.keys()
    assert options == {"timeout": 180, "capture": True}


@pytest.mark.parametrize("component,version", [("crawl4ai", "0.9.3"), ("scrapegraphai", "2.2.2")])
def test_web_probe_preserves_clean_home_and_only_pinned_shared_assets(invocation, monkeypatch, capsys, component, version):
    monkeypatch.setattr(invocation.probe.sys, "argv", ["probe", str(invocation.repo), component])
    for key in ("SCRAPEGRAPHAI_OPENAI_API_KEY", "PLAYWRIGHT_BROWSERS_PATH", "TIKTOKEN_CACHE_DIR"):
        monkeypatch.setenv(key, "PRIVATE_SENTINEL")

    def run(argv, **options):
        invocation.calls.append((argv, options))
        return SimpleNamespace(returncode=0, stderr=b"", stdout=json.dumps({
            "success": True, "component": component, "version": version, "browser": "launch-passed",
        }).encode())

    monkeypatch.setattr(native_process, "run_bounded_native", run)
    assert invocation.probe.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {"component": component, "software_verified": True, "account_checked": False}
    argv, options = invocation.calls[0]
    runtime = Path(f"/opt/station/tools/web/{component}-{version}-py3.13.15-pw1.62.0")
    native_index = argv.index(str(runtime / "venv/bin/python"))
    assert argv[:3] == ["/usr/bin/env", "-i", f"--chdir={invocation.private}"]
    environment = dict(value.split("=", 1) for value in argv[3:native_index])
    assert environment["HOME"] == str(invocation.private)
    assert environment["HERMES_HOME"] == str(invocation.private / "hermes")
    assert environment["XDG_CACHE_HOME"] == str(invocation.private / "cache")
    assert environment["PLAYWRIGHT_BROWSERS_PATH"] == str(runtime / "browsers")
    assert environment["TIKTOKEN_CACHE_DIR"] == str(runtime / "tokenizers")
    assert environment["SCRAPEGRAPHAI_TELEMETRY_ENABLED"] == "false"
    assert not {"OPENAI_API_KEY", "SCRAPEGRAPHAI_OPENAI_API_KEY", "HONCHO_API_KEY", "HINDSIGHT_API_KEY", "PYTHONPATH"} & environment.keys()
    assert all("PRIVATE_SENTINEL" not in value and str(invocation.account_home) not in value for value in argv)
    assert options == {"timeout": 180, "capture": True}


@pytest.mark.parametrize("component,version", [("crawl4ai", "0.9.3"), ("scrapegraphai", "2.2.2")])
@pytest.mark.parametrize("changed", [
    {"success": False}, {"success": 1}, {"component": "another-worker"},
    {"version": "99.0.0"}, {"version": 2.2}, {"browser": "not-launched"}, {"browser": None},
])
def test_web_health_requires_exact_native_success_fields(invocation, monkeypatch, capsys, component, version, changed):
    monkeypatch.setattr(invocation.probe.sys, "argv", ["probe", str(invocation.repo), component])
    health = {"success": True, "component": component, "version": version, "browser": "launch-passed"} | changed
    monkeypatch.setattr(native_process, "run_bounded_native", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(health).encode(), stderr=b""))
    assert invocation.probe.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report == {"component": component, "software_verified": False, "account_checked": False}


def test_valid_web_health_cannot_override_native_process_failure(invocation, monkeypatch, capsys):
    monkeypatch.setattr(invocation.probe.sys, "argv", ["probe", str(invocation.repo), "crawl4ai"])
    health = {"success": True, "component": "crawl4ai", "version": "0.9.3", "browser": "launch-passed"}
    monkeypatch.setattr(native_process, "run_bounded_native", lambda *args, **kwargs:
                        SimpleNamespace(returncode=17, stdout=json.dumps(health).encode(), stderr=b"PRIVATE_SENTINEL"))
    assert invocation.probe.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["software_verified"] is False
    assert "PRIVATE_SENTINEL" not in output.out + output.err


@pytest.mark.parametrize("output", [b"PRIVATE_SENTINEL", b"null", b"[]"])
def test_malformed_web_health_is_redacted(invocation, monkeypatch, capsys, output):
    monkeypatch.setattr(invocation.probe.sys, "argv", ["probe", str(invocation.repo), "scrapegraphai"])
    monkeypatch.setattr(native_process, "run_bounded_native", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=output, stderr=b"PRIVATE_SENTINEL"))
    assert invocation.probe.main() == 1
    captured = capsys.readouterr()
    assert "PRIVATE_SENTINEL" not in captured.out + captured.err
    assert "redacted" in captured.err


def test_native_failure_is_reported_false_without_replaying_output(invocation, monkeypatch, capsys):
    monkeypatch.setattr(native_process, "run_bounded_native", lambda *args, **kwargs:
                        SimpleNamespace(returncode=23, stdout=b"PRIVATE_SENTINEL", stderr=b"PRIVATE_SENTINEL"))
    assert invocation.probe.main() == 1
    output = capsys.readouterr()
    assert "PRIVATE_SENTINEL" not in output.out + output.err
    assert json.loads(output.out)["software_verified"] is False
    assert json.loads(output.out)["account_checked"] is False


def test_supervisor_exception_is_redacted(invocation, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_SENTINEL")
    monkeypatch.setattr(native_process, "run_bounded_native", fail)
    assert invocation.probe.main() == 1
    output = capsys.readouterr()
    assert "PRIVATE_SENTINEL" not in output.out + output.err
    assert "redacted" in output.err


@pytest.mark.parametrize("version", ["1.6.10", "11.6.1", "11.6.10"])
def test_strix_version_substrings_do_not_pass_exact_pin(invocation, monkeypatch, capsys, version):
    monkeypatch.setattr(invocation.probe.sys, "argv", ["probe", str(invocation.repo), "strix"])
    monkeypatch.setattr(native_process, "run_bounded_native", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=f"Strix {version}\n".encode(), stderr=b""))
    assert invocation.probe.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["software_verified"] is False
    assert json.loads(output.out)["account_checked"] is False


def test_invalid_repository_is_redacted_without_native_execution(invocation, monkeypatch, capsys):
    monkeypatch.setattr(invocation.probe.sys, "argv", ["probe", str(invocation.repo / "PRIVATE_SENTINEL"), "hermes-clients"])
    assert invocation.probe.main() == 1
    output = capsys.readouterr()
    assert "PRIVATE_SENTINEL" not in output.out + output.err
    assert "redacted" in output.err
    assert not invocation.calls


@pytest.mark.parametrize("platform,uid", [("darwin", 1001), ("linux", 0)])
def test_wrong_platform_or_root_is_rejected_before_native_execution(invocation, monkeypatch, capsys, platform, uid):
    monkeypatch.setattr(invocation.probe.sys, "platform", platform)
    monkeypatch.setattr(invocation.probe.os, "geteuid", lambda: uid)
    assert invocation.probe.main() == 2
    assert not invocation.calls
    assert "non-root Linux" in capsys.readouterr().err
