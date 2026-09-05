"""Real synthetic descendants cannot outlive a bounded native CLI operation."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import pytest

from agentik_station import native_process
from agentik_station.native_process import NativeOutputLimitError, OUTPUT_LIMIT, run_bounded_native


SECRET = "SECRET_NATIVE_COMMAND_DIAGNOSTIC"
PYTHON = str(Path(sys.executable).resolve())
LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="Linux Host process-group acceptance")


def command(source, *args):
    return [PYTHON, "-I", "-B", "-c", source, *map(str, args)]


@LINUX_ONLY
def test_normal_result_has_bounded_bytes_without_echo_or_raw_args(capsys):
    result = run_bounded_native(command("import os,sys;os.write(1,b'hello');os.write(2,b'warning');sys.exit(7)"),
                                capture=True)
    assert result.returncode == 7
    assert result.stdout == b"hello"
    assert result.stderr == b"warning"
    assert result.args == "native command"
    assert capsys.readouterr().out == ""


@LINUX_ONLY
def test_non_capture_discards_output_and_stdin_is_closed(capsys):
    result = run_bounded_native(command("import os;assert os.read(0,1)==b'';os.write(1,b'private');os.write(2,b'private')"))
    assert result.returncode == 0
    assert result.stdout is result.stderr is None
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@LINUX_ONLY
def test_environment_is_minimal_and_execution_has_new_session_and_root_cwd(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    source = "import os;assert os.getcwd()=='/';assert 'OPENAI_API_KEY' not in os.environ;assert os.getpid()==os.getpgrp()==os.getsid(0)"
    assert run_bounded_native(command(source)).returncode == 0


@LINUX_ONLY
@pytest.mark.parametrize("stream", [1, 2])
def test_exact_capture_limit_is_allowed(stream):
    result = run_bounded_native(command(f"import os;os.write({stream},b'x'*{OUTPUT_LIMIT})"), capture=True)
    assert result.returncode == 0
    assert len(result.stdout if stream == 1 else result.stderr) == OUTPUT_LIMIT


@LINUX_ONLY
@pytest.mark.parametrize("stream", [1, 2])
def test_each_stream_has_its_own_limit(stream):
    source = f"import os;os.write({stream},b'x'*{OUTPUT_LIMIT+1})"
    with pytest.raises(NativeOutputLimitError) as error:
        run_bounded_native(command(source, SECRET), capture=True)
    assert SECRET not in str(error.value)


def _stopped(pid):
    # A killed orphan may remain as a zombie until the Host's PID 1 reaps it.
    # Zombie != a process able to continue mutating after the Station lock exits.
    result = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return result.returncode != 0 or not result.stdout.strip() or result.stdout.strip().startswith("Z")


def _assert_stopped(pid):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if _stopped(pid):
            return
        time.sleep(0.02)
    pytest.fail("Synthetic descendant continued running after bounded execution")


TREE_SOURCE = """
import os,sys,time
from pathlib import Path
pidfile=Path(sys.argv[1])
mode=sys.argv[2]
child=os.fork()
if child==0:
    while True:
        time.sleep(0.1)
pidfile.write_text(str(child))
if mode=='overflow':
    os.write(1,b'x'*1000000)
elif mode=='normal':
    os._exit(0)
elif mode=='closed-pipes':
    os.close(1);os.close(2)
while True:
    time.sleep(0.1)
"""


@LINUX_ONLY
@pytest.mark.parametrize("mode", ["timeout", "overflow", "normal", "closed-pipes"])
def test_real_child_and_grandchild_group_is_terminated_on_every_exit(tmp_path, mode):
    pidfile = tmp_path / "grandchild.pid"
    start = time.monotonic()
    try:
        if mode == "overflow":
            with pytest.raises(NativeOutputLimitError):
                run_bounded_native(command(TREE_SOURCE, pidfile, mode), timeout=2, capture=True)
        elif mode == "normal":
            assert run_bounded_native(command(TREE_SOURCE, pidfile, mode), timeout=2, capture=True).returncode == 0
        else:
            with pytest.raises(subprocess.TimeoutExpired) as error:
                run_bounded_native(command(TREE_SOURCE, pidfile, mode, SECRET), timeout=0.4,
                                   capture=mode == "closed-pipes")
            assert error.value.cmd == "native command"
            assert error.value.output is error.value.stderr is None
            assert SECRET not in str(error.value)
        assert time.monotonic() - start < 3
        _assert_stopped(int(pidfile.read_text()))
    finally:
        # Recover only our fixture PID should an assertion expose a regression.
        if pidfile.exists():
            pid = int(pidfile.read_text())
            if not _stopped(pid):
                os.kill(pid, signal.SIGKILL)


@LINUX_ONLY
@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_real_signal_interrupt_cleans_group_and_restores_handlers(tmp_path, number):
    pidfile = tmp_path / "grandchild.pid"
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}

    def interrupt_when_ready():
        deadline = time.monotonic() + 2
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if pidfile.exists():
            os.kill(os.getpid(), number)

    interrupter = threading.Thread(target=interrupt_when_ready)
    interrupter.start()
    try:
        expected = KeyboardInterrupt if number == signal.SIGINT else InterruptedError
        with pytest.raises(expected):
            run_bounded_native(command(TREE_SOURCE, pidfile, "timeout"), timeout=3)
        _assert_stopped(int(pidfile.read_text()))
        assert {sig: signal.getsignal(sig) for sig in previous} == previous
    finally:
        interrupter.join(timeout=3)
        if pidfile.exists():
            pid = int(pidfile.read_text())
            if not _stopped(pid):
                os.kill(pid, signal.SIGKILL)


@LINUX_ONLY
def test_spawn_error_does_not_disclose_arguments_or_executable():
    with pytest.raises(subprocess.SubprocessError) as error:
        run_bounded_native([f"/missing/{SECRET}", SECRET])
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("argv,options", [("shell string", {}), ([], {}), (["relative"], {}),
                                         (["/bin/true", 4], {}), (["/bin/true", "nul\x00"], {}),
                                         (["/bin/true"], {"timeout": 0}),
                                         (["/bin/true"], {"timeout": float("inf")}),
                                         (["/bin/true"], {"timeout": float("nan")}),
                                         (["/bin/true"], {"timeout": True}),
                                         (["/bin/true"], {"capture": "yes"})])
def test_invalid_call_options_fail_before_spawn(argv, options, monkeypatch):
    monkeypatch.setattr(native_process, "platform", "linux")
    with pytest.raises(subprocess.SubprocessError):
        run_bounded_native(argv, **options)


def test_non_main_thread_fails_before_signal_or_child_creation():
    observed = []
    def run():
        try:
            run_bounded_native(["/bin/true"])
        except subprocess.SubprocessError as error:
            observed.append(str(error))
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert observed == ["Native execution requires the main Linux CLI thread"]


@pytest.mark.parametrize("platform", ["darwin", "win32", "freebsd14"])
def test_unsupported_platform_fails_before_launch_or_changing_signals(monkeypatch, platform):
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(native_process, "platform", platform)
    monkeypatch.setattr(native_process.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Must not launch"))
    with pytest.raises(subprocess.SubprocessError, match="main Linux CLI thread"):
        run_bounded_native(["/bin/true"])
    assert signal.getsignal(signal.SIGTERM) == previous


@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_signal_during_popen_is_deferred_until_cleanup_owns_handle(monkeypatch, number):
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
    observed = []
    monkeypatch.setattr(native_process, "platform", "linux")

    class Process:
        pid = 123456789
        stdout = stderr = None

        def __init__(self, argv, **options):
            observed.append("constructing")
            signal.getsignal(number)(number, None)
            observed.append("constructor returned")

        def wait(self):
            observed.append("reaped")
            return -signal.SIGKILL

    monkeypatch.setattr(native_process.subprocess, "Popen", Process)
    monkeypatch.setattr(native_process.os, "killpg",
                        lambda pid, sig: observed.append((pid, sig)))
    expected = KeyboardInterrupt if number == signal.SIGINT else InterruptedError
    with pytest.raises(expected):
        run_bounded_native(["/bin/true"])
    assert observed == ["constructing", "constructor returned", (123456789, signal.SIGKILL), "reaped"]
    assert {sig: signal.getsignal(sig) for sig in previous} == previous
