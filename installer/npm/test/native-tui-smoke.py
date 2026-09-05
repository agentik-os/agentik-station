"""Read-only native Workstation AGK navigation; no model/session/service starts."""
from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import stat
import struct
import subprocess
import sys
import termios
import time


def main() -> None:
    assert os.geteuid() != 0, "Run native acceptance as the ordinary Workstation owner"
    root = Path(sys.argv[1])
    assert root.is_absolute() and root.resolve() == root
    identity = root.lstat()
    assert stat.S_ISDIR(identity.st_mode) and identity.st_uid == os.getuid() and not identity.st_mode & 0o077
    assert not (root / ".install.lock").exists(), "Finish the active installation before acceptance"
    marker = json.loads((root / ".station-workstation.json").read_text())
    assert marker["root"] == str(root) and marker["uid"] == os.getuid() and marker["mode"] == "workstation"
    home = root / "personal/home"
    launcher = root / "bin/agk"
    env = {"HOME": str(home), "PATH": f"{root}/bin:/usr/bin:/bin", "TERM": "xterm-256color"}
    socket = root / "cache/rmux" / f"rmux-{os.getuid()}" / "default"
    socket_existed = socket.exists()
    report = {"root": str(root), "scope": "native AGK commands and read-only navigation; no model/session/service activation", "commands": [], "views": [], "sizes": [], "operational": False}
    for args, expected in ((["commands"], "AGK-TUI"), (["status"], "PRIVATE"), (["doctor", "--offline"], "INSTALLATION_ONLY")):
        result = subprocess.run([str(launcher), *args], env=env, cwd=root / "projects", capture_output=True, text=True, timeout=45)
        assert result.returncode == 0 and expected in result.stdout, f"Native AGK {' '.join(args)} failed"
        report["commands"].append(" ".join(args))
    child, master = pty.fork()
    if child == 0:
        os.chdir(root / "projects")
        os.execve(launcher, [str(launcher)], env)
    width = 140

    def drain(duration=0.25):
        data = bytearray()
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if not select.select([master], [], [], 0.03)[0]:
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            data.extend(chunk)
            assert len(data) < 2 * 1024 * 1024, "Native terminal output exceeded budget"
        return bytes(data)

    def keys(value):
        os.write(master, value)
        return drain()

    def frame(expected):
        nonlocal width, child
        width = 139 if width == 140 else 140
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, width, 0, 0))
        os.kill(child, signal.SIGWINCH)
        data = bytearray()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            data.extend(drain(0.15))
            text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data.decode("utf-8", "replace"))
            if expected in text:
                return
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid:
                child = None
                raise AssertionError(f"Native TUI exited during read-only navigation ({os.waitstatus_to_exitcode(status)})")
        raise AssertionError(f"Native fresh frame missing {expected}")

    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, width, 0, 0))
        drain(1)
        frame("SESSIONS ·")
        for query, title in (
            ("Open Sessions", "SESSIONS ·"),
            ("Open Projects & Missions", "CLIENTS · PROJECTS · MISSIONS"),
            ("Open Agents", "AGENT REGISTRY"),
            ("Open Agentik OS", "AGENTIK OS REGISTRY"),
            ("Open MCP servers", "MCP REGISTRY"),
            ("Open Skills", "INSTALLED SKILLS"),
            ("Open Rules", "RULE DETAIL"),
            ("Open Settings", "APPEARANCE · LIVE PREVIEW"),
            ("Open Help", "COMPLETE KEYBOARD REFERENCE"),
            ("Open System Settings", "SYSTEM & REGISTRY HEALTH"),
        ):
            keys(b"\x10")
            frame("COMMAND PALETTE")
            keys(query.encode())
            keys(b"\r")
            frame(title)
            report["views"].append(query)
        for height, width in ((16, 64), (24, 100), (40, 140)):
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
            os.kill(child, signal.SIGWINCH)
            assert drain(0.35), "No native frame after resize"
            report["sizes"].append(f"{width}x{height}")
        keys(b"\x10")
        keys(b"Detach AGK")
        keys(b"\r")
        deadline = time.monotonic() + 5
        while True:
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid:
                child = None
                assert os.waitstatus_to_exitcode(status) == 0
                report["exit_code"] = 0
                break
            assert time.monotonic() < deadline, "Native TUI did not detach"
            drain(0.1)
    finally:
        if child is not None:
            try:
                os.kill(child, signal.SIGTERM)
                os.waitpid(child, 0)
            except ProcessLookupError:
                pass
        os.close(master)
        if not socket_existed and socket.exists():
            assert stat.S_ISSOCK(socket.lstat().st_mode) and socket.stat().st_uid == os.getuid()
            remaining = subprocess.run([str(root / "bin/rmux"), "list-sessions", "-F", "#{session_name}"], capture_output=True, text=True, env=env, timeout=10)
            assert not remaining.stdout.strip(), "Non-synthetic sessions appeared; preserve private daemon"
            subprocess.run([str(root / "bin/rmux"), "kill-server"], capture_output=True, env=env, timeout=10)
            report["closed_new_empty_private_daemon"] = True
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
