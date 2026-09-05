"""Synthetic /bin/cat lifecycle in a fresh declared Workstation Project folder."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time


def main() -> None:
    assert os.geteuid() != 0, "Run native acceptance as the ordinary Workstation owner"
    root = Path(sys.argv[1])
    assert root.is_absolute() and root.resolve() == root
    marker = json.loads((root / ".station-workstation.json").read_text())
    assert marker["mode"] == "workstation" and marker["root"] == str(root) and marker["uid"] == os.getuid()
    assert not (root / ".install.lock").exists()
    component = root / "tools/agk-terminal"
    home = root / "personal/home"
    env = {
        "HOME": str(home), "USER": "station-workstation", "LOGNAME": "station-workstation",
        "PATH": f"{root}/bin:{component}/venv/bin:/usr/bin:/bin",
        "HERMES_HOME": str(home / ".hermes/profiles" / marker["profile"]),
        "STATION_WORKSTATION_ROOT": str(root), "AGK_ENVIRONMENT": "private", "AGENTIK_ENVIRONMENT": "private",
        "AGK_TERMINAL_ROOT": str(component), "AGK_ENV_CONFIG": str(home / ".config/agk/environment.yaml"),
        "RMUX_TMPDIR": str(root / "cache/rmux"), "TERM": "xterm-256color", "PYTHONDONTWRITEBYTECODE": "1",
    }
    os.environ.clear()
    os.environ.update(env)
    spec = importlib.util.spec_from_file_location("native_workstation_control", component / "scripts/agk_control.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    selected = module.Environment.current()
    assert selected.home == home and selected.projects == root / "projects" and selected.name == "private"
    registry = module.RuntimeRegistry(selected)
    before = {row["id"] for row in registry.rows(include_archived=True)}
    fixture = Path(tempfile.mkdtemp(prefix="native-acceptance-", dir=selected.projects))
    name = fixture.name
    socket = root / "cache/rmux" / f"rmux-{os.getuid()}" / "default"
    was_running = socket.exists()
    row = None
    report = {"root": str(root), "scope": "synthetic Project /bin/cat only; no model calls", "checks": [], "operational": False}
    try:
        row = registry.create(name=name, kind="shell", cwd=fixture, command=["/bin/cat"])
        assert Path(row["cwd"]) == fixture and row["environment"] == "private"
        assert socket.is_socket() and socket.stat().st_uid == os.getuid()
        report["checks"].append("validated_project_and_private_native_socket")
        message = "STATION_PORTABLE_SYNTHETIC_READBACK"
        registry.runtime.send_input(row["rmux_session"], message)
        deadline = time.monotonic() + 8
        while message not in "\n".join(registry.runtime.snapshot(row["rmux_session"], 20)):
            assert time.monotonic() < deadline, "Synthetic pane readback failed"
            time.sleep(0.05)
        report["checks"].append("literal_input_and_readback")
        row = registry.rename(row, name + "-renamed")
        report["checks"].append("rename")
        row = registry.restart_frontend(row)
        report["checks"].append("respawn")
        row = registry.terminate(row)
        row = registry.archive(row)
        row = registry.restart_frontend(row)
        assert row["archived_at"] is None
        report["checks"].append("restart_archived_and_visible")
    finally:
        if row is not None:
            registry.purge(registry.get(row["id"]))
            report["checks"].append("purge_only_synthetic_session")
        assert {row["id"] for row in registry.rows(include_archived=True)} == before
        registry.db.close()
        assert fixture.parent == selected.projects and fixture.lstat().st_uid == os.getuid() and not fixture.is_symlink()
        fixture.rmdir()  # only the exact empty directory this probe created
        if not was_running and socket.exists():
            assert stat.S_ISSOCK(socket.lstat().st_mode) and socket.stat().st_uid == os.getuid()
            remaining = subprocess.run([str(root / "bin/rmux"), "list-sessions", "-F", "#{session_name}"], capture_output=True, text=True, env=env, timeout=10)
            assert not remaining.stdout.strip(), "New non-synthetic session appeared; preserve daemon"
            subprocess.run([str(root / "bin/rmux"), "kill-server"], capture_output=True, env=env, timeout=10)
            report["checks"].append("close_only_new_empty_private_daemon")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
