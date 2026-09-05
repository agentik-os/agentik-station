"""Bounded Linux CLI execution, with cleanup of its own POSIX process group.

This supervises trusted native commands, not hostile daemons: a descendant that
deliberately creates another session is outside this process-group mechanism.
Callers supply validated absolute argv, including the explicit Zone/env identity
boundary. No shell, credential inheritance, disk spool or raw exception output.
"""
from __future__ import annotations

import math
import os
import selectors
import signal
import subprocess
from sys import platform
import threading
import time


OUTPUT_LIMIT = 64 * 1024
POLL_SECONDS = 0.05
COMMAND_LABEL = "native command"


class NativeOutputLimitError(subprocess.SubprocessError):
    """A native command exceeded one of the bounded captured streams."""


def _leader_exited(pid):
    # Keep the leader unreaped until after killpg. Its reserved PID prevents an
    # unrelated process group from acquiring that identifier before cleanup.
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def _read_ready(selector, buffers, wait):
    for key, _ in selector.select(wait):
        chunk = os.read(key.fd, 16 * 1024)
        if not chunk:
            selector.unregister(key.fileobj)
            continue
        target = buffers[key.data]
        if len(target) + len(chunk) > OUTPUT_LIMIT:
            raise NativeOutputLimitError("Native command exceeded the bounded output limit")
        target.extend(chunk)


def run_bounded_native(argv, *, timeout=300, capture=False):
    """Run a main-thread Linux native CLI; return bytes output only when requested.

    Timeout raises a redacted ``TimeoutExpired``; output overflow raises
    ``NativeOutputLimitError``. Spawn/execution errors are redacted
    ``SubprocessError``. Both normal and exceptional exits kill the owned group
    before reaping its leader. SIGTERM/SIGHUP are converted into cleanup-safe
    interruption; original signal handlers are restored afterward.

    Station's Host target is Linux. macOS reports an ambiguous EPERM when
    killpg sees only zombies, which cannot safely be treated as success here.
    """
    if (threading.current_thread() is not threading.main_thread()
            or platform != "linux" or not hasattr(os, "WNOWAIT")):
        raise subprocess.SubprocessError("Native execution requires the main Linux CLI thread")
    if (not isinstance(argv, (list, tuple)) or not argv
            or any(not isinstance(item, str) or "\x00" in item for item in argv)
            or not argv[0].startswith("/") or not isinstance(capture, bool)
            or isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise subprocess.SubprocessError("Invalid bounded native command options")

    process = None
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    previous = {number: signal.getsignal(number) for number in
                (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
    constructing = True
    pending_signal = None

    def interrupted(number, frame):
        nonlocal pending_signal
        if number == signal.SIGINT and previous[number] == signal.SIG_IGN:
            return
        if constructing:
            # A signal raised inside Popen could otherwise lose the child
            # handle before assignment. Defer it without changing the child's
            # inherited signal mask, then deliver once cleanup owns the handle.
            pending_signal = (number, frame)
            return
        if number == signal.SIGINT:
            if callable(previous[number]):
                return previous[number](number, frame)
            raise KeyboardInterrupt
        raise InterruptedError("Native command interrupted; process-group cleanup required")

    deadline = time.monotonic() + timeout
    try:
        for number in previous:
            signal.signal(number, interrupted)
        process = subprocess.Popen(
            list(argv), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
            cwd="/", env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8",
                          "LC_ALL": "C.UTF-8"},
            shell=False, start_new_session=True,
        )
        constructing = False
        if pending_signal is not None:
            interrupted(*pending_signal)
        if capture:
            for name in buffers:
                stream = getattr(process, name)
                selector.register(stream, selectors.EVENT_READ, name)
        while not _leader_exited(process.pid):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(COMMAND_LABEL, timeout)
            if capture and selector.get_map():
                _read_ready(selector, buffers, min(POLL_SECONDS, remaining))
            else:
                time.sleep(min(POLL_SECONDS, remaining))
        # Cleanup occurs even when the leader exits normally with background
        # children. Drain its remaining pipe bytes only after that group is dead.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if capture:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(COMMAND_LABEL, timeout)
                _read_ready(selector, buffers, min(POLL_SECONDS, remaining))
        # Do not call wait/poll here: finally owns the sole reap after group kill.
    except (subprocess.TimeoutExpired, NativeOutputLimitError, InterruptedError):
        raise
    except (OSError, subprocess.SubprocessError, ValueError):
        raise subprocess.SubprocessError("Native command could not complete safely") from None
    finally:
        # Repeated terminal signals must not interrupt cleanup between kill and
        # reap. SIGKILL of this supervisor is inherently outside this mechanism.
        for number in previous:
            signal.signal(number, signal.SIG_IGN)
        try:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            selector.close()
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)

    return subprocess.CompletedProcess(
        COMMAND_LABEL, process.returncode,
        bytes(buffers["stdout"]) if capture else None,
        bytes(buffers["stderr"]) if capture else None,
    )
