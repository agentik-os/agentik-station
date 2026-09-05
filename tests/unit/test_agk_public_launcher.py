from __future__ import annotations

import ast
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

import agentik_station.agk_launcher as launcher
import agentik_station.cli as cli
from agentik_station.errors import SecurityError, StationError, ValidationError
from agentik_station.paths import LayoutPaths


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def installation(tmp_path, monkeypatch):
    home = tmp_path / "home/agk-station"
    paths = LayoutPaths.under(tmp_path / "station")
    paths.bin.mkdir(parents=True)
    account = SimpleNamespace(pw_name="agk-station", pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(home))
    monkeypatch.setattr(launcher, "OPERATOR_HOME", home)
    monkeypatch.setattr(launcher, "_operator", lambda: account)
    for relative in (".local/bin/agk", ".local/lib/agk-terminal/bin/agk-tui",
                     ".local/lib/agk-terminal/bin/rmux", ".local/lib/agk-terminal/scripts/agk_control.py"):
        file = home / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("#!/bin/sh\nexit 0\n")
        file.chmod(0o755)
    home.chmod(0o750)
    return paths, home, account


def test_install_and_idempotent_readback_preserve_private_home(installation):
    paths, home, account = installation
    before = home.stat()
    first = launcher.install_agk_launcher(paths, operator="agk-station")
    assert first["state"] == "INSTALLED"
    assert not first["runtime_verified"] and not first["already_installed"]
    target = paths.bin / "agk"
    assert target.read_text() == launcher._render_launcher(account.pw_uid, account.pw_gid)
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
    second = launcher.install_agk_launcher(paths, operator="agk-station")
    assert second["already_installed"]
    assert (home.stat().st_mode, home.stat().st_uid) == (before.st_mode, before.st_uid)
    assert not (paths.config / "sudoers").exists()


def test_plan_is_pure_and_does_not_acquire_lock(installation):
    paths, _, _ = installation
    result = launcher.install_agk_launcher(paths, operator="agk-station", plan=True)
    assert result["state"] == "PREPARED"
    assert not (paths.bin / "agk").exists()
    assert not paths.run.exists()


@pytest.mark.parametrize("operator", ["root", "moonbase", "agk-station;id", "../agk-station", "-u root", ""])
def test_only_canonical_operator_is_accepted(installation, operator):
    paths, _, _ = installation
    with pytest.raises(ValidationError):
        launcher.install_agk_launcher(paths, operator=operator)
    assert not (paths.bin / "agk").exists()


@pytest.mark.parametrize("kind", ["unrelated", "symlink", "hardlink", "fifo", "writable", "mode", "directory"])
def test_existing_public_command_is_never_clobbered(installation, kind):
    paths, _, account = installation
    target = paths.bin / "agk"
    outside = paths.bin / "existing-tool"
    outside.write_text("keep me")
    if kind == "symlink":
        target.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, target)
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "directory":
        target.mkdir()
    else:
        target.write_text(launcher._render_launcher(account.pw_uid, account.pw_gid) if kind != "unrelated" else "unrelated")
        target.chmod({"writable": 0o777, "mode": 0o644}.get(kind, 0o755))
    with pytest.raises((SecurityError, OSError)):
        launcher.install_agk_launcher(paths, operator="agk-station")
    assert outside.read_text() == "keep me"
    assert target.exists() or target.is_symlink()


@pytest.mark.parametrize("change", ["missing", "symlink", "writable", "not-executable"])
def test_private_payload_must_be_installed_and_safe(installation, change):
    paths, home, _ = installation
    native = home / ".local/lib/agk-terminal/bin/agk-tui"
    if change in {"missing", "symlink"}:
        native.unlink()
        if change == "symlink":
            native.symlink_to(home / ".local/bin/agk")
    else:
        native.chmod(0o777 if change == "writable" else 0o644)
    with pytest.raises((SecurityError, OSError)):
        launcher.install_agk_launcher(paths, operator="agk-station")
    assert not (paths.bin / "agk").exists()


def test_private_symlinked_parent_is_rejected(installation):
    paths, home, _ = installation
    original = home / ".local/lib"
    moved = home / "elsewhere"
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)
    with pytest.raises((SecurityError, OSError)):
        launcher.install_agk_launcher(paths, operator="agk-station")


def test_world_writable_public_parent_is_rejected(installation):
    paths, _, _ = installation
    paths.bin.chmod(0o777)
    with pytest.raises(SecurityError):
        launcher.install_agk_launcher(paths, operator="agk-station")


def test_live_install_requires_existing_root_authorization(monkeypatch):
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 1234)
    with pytest.raises(StationError, match="sudo authorization"):
        launcher.install_agk_launcher(LayoutPaths.live(), operator="agk-station")


@pytest.mark.parametrize("field,value", [("pw_uid", 0), ("pw_gid", 0), ("pw_name", "moonbase"), ("pw_dir", "/root")])
def test_operator_account_identity_must_match(monkeypatch, field, value):
    account = dict(pw_uid=1234, pw_gid=1234, pw_name="agk-station", pw_dir="/home/agk-station")
    account[field] = value
    monkeypatch.setattr(launcher.pwd, "getpwnam", lambda _: SimpleNamespace(**account))
    with pytest.raises(SecurityError):
        launcher._operator()


def test_missing_operator_is_actionable(monkeypatch):
    def missing(_):
        raise KeyError("not installed")
    monkeypatch.setattr(launcher.pwd, "getpwnam", missing)
    with pytest.raises(ValidationError, match="not installed"):
        launcher._operator()


class Executed(Exception):
    def __init__(self, binary, argv, env):
        self.binary, self.argv, self.env = binary, argv, env


def wrapper_runtime(*, uid=2000, gid=2000, args=None, tty=True, account=None):
    source = launcher._render_launcher(2000, 2000)
    ast.parse(source)
    namespace = {}
    exec(compile(source.split("\ntry:\n    raise SystemExit(main())")[0], "public-agk", "exec"), namespace)
    changes = []
    def execute(binary, argv, env):
        raise Executed(binary, argv, env)
    namespace["os"] = SimpleNamespace(
        geteuid=lambda: uid, getuid=lambda: uid, getegid=lambda: gid,
        chdir=changes.append, execve=execute,
        environ={"HOME": "/home/moonbase", "USER": "moonbase", "HERMES_HOME": "/other/secret",
                 "AGK_ENVIRONMENT": "foreign", "AGK_TERMINAL_ROOT": "/tmp/hostile",
                 "PYTHONPATH": "/tmp/python", "BASH_ENV": "/tmp/sh", "RMUX_SOCKET": "/foreign/socket",
                 "OPENAI_API_KEY": "never-forward", "SSH_AUTH_SOCK": "/foreign/agent", "TERM": "xterm-256color"})
    namespace["pwd"] = SimpleNamespace(getpwnam=lambda _: account or SimpleNamespace(pw_uid=2000, pw_gid=2000, pw_dir="/home/agk-station"))
    namespace["sys"] = SimpleNamespace(argv=["/usr/local/bin/agk", *(args or [])],
                                       stdin=SimpleNamespace(isatty=lambda: tty),
                                       stdout=SimpleNamespace(isatty=lambda: tty), stderr=io.StringIO())
    return namespace, changes


@pytest.mark.parametrize("uid,binary,prefix", [
    (0, "/usr/sbin/runuser", ["--user", "agk-station", "--"]),
    (1000, "/usr/bin/sudo", ["-H", "-u", "agk-station", "--"]),
])
def test_human_and_root_handoff_drop_identity_before_private_execution(uid, binary, prefix):
    args = ["new", "shell", "literal; $(touch NEVER)", "--cwd", "/path with spaces", "--", "-danger"]
    runtime, changes = wrapper_runtime(uid=uid, args=args)
    with pytest.raises(Executed) as exc:
        runtime["main"]()
    call = exc.value
    assert call.binary == binary
    assert call.argv == [binary, *prefix, "/usr/local/bin/agk", *args]
    assert changes == ["/"]
    assert set(call.env) == {"PATH", "TERM", "LANG", "LC_ALL"}
    assert not any("never-forward" in value for value in call.env.values())


def test_operator_reentry_executes_private_payload_without_second_sudo():
    runtime, changes = wrapper_runtime(args=["status"])
    with pytest.raises(Executed) as exc:
        runtime["main"]()
    call = exc.value
    assert call.argv == ["/home/agk-station/.local/bin/agk", "status"]
    assert changes == ["/home/agk-station"]
    assert call.env["HOME"] == "/home/agk-station"
    assert call.env["HERMES_HOME"] == "/home/agk-station/.hermes"
    assert call.env["AGK_ENVIRONMENT"] == call.env["USER"] == call.env["LOGNAME"] == "agk-station"
    assert call.env["AGK_TERMINAL_ROOT"] == "/home/agk-station/.local/lib/agk-terminal"
    for name in ("RMUX_SOCKET", "PYTHONPATH", "BASH_ENV", "OPENAI_API_KEY", "SSH_AUTH_SOCK"):
        assert name not in call.env


@pytest.mark.parametrize("bad", ["xterm\nBAD", "$(id)", "", "x" * 81])
def test_terminal_value_cannot_inject_environment(bad):
    runtime, _ = wrapper_runtime(args=["status"])
    runtime["os"].environ["TERM"] = bad
    with pytest.raises(Executed) as exc:
        runtime["main"]()
    assert exc.value.env["TERM"] == "xterm-256color"


def test_recreated_or_redirected_operator_refuses_handoff():
    account = SimpleNamespace(pw_uid=2001, pw_gid=2000, pw_dir="/home/agk-station")
    runtime, changes = wrapper_runtime(uid=0, args=["status"], account=account)
    assert runtime["main"]() == 2
    assert not changes
    assert "identity changed" in runtime["sys"].stderr.getvalue()


def test_wrong_operator_primary_group_is_rejected():
    runtime, changes = wrapper_runtime(gid=1000, args=["status"])
    assert runtime["main"]() == 2
    assert not changes


@pytest.mark.parametrize("args,code", [([], 2), (["tui"], 2), (["tui", "--unexpected"], 2), (["--help"], 0), (["help"], 0)])
def test_public_noninteractive_help_and_empty_invocation_do_not_authenticate(tmp_path, args, code):
    target = tmp_path / "agk"
    target.write_text(launcher._render_launcher(2000, 2000))
    result = subprocess.run([sys.executable, "-I", str(target), *args], stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == code
    assert "AGK" in result.stdout + result.stderr or "agk tui" in result.stderr
    assert "Traceback" not in result.stderr


def test_public_tui_alias_becomes_exact_native_interactive_argv():
    runtime, _ = wrapper_runtime(args=["tui"])
    with pytest.raises(Executed) as exc:
        runtime["main"]()
    assert exc.value.argv == ["/home/agk-station/.local/bin/agk"]


def test_bare_station_is_helpful_without_privileged_launch(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_agk_launcher", lambda: pytest.fail("must not launch AGK"))
    assert cli.main([]) == 0
    assert "tui" in capsys.readouterr().out


def test_tui_preserves_arguments_without_polluting_identity(monkeypatch):
    monkeypatch.setattr(cli, "_agk_launcher", lambda: Path("/public/agk"))
    calls = []
    monkeypatch.setattr(cli.os, "execv", lambda path, argv: calls.append((path, argv)))
    monkeypatch.setenv("AGK_ENVIRONMENT", "caller-environment")
    assert cli.main(["tui", "--", "new", "shell", "literal; argument"]) == 0
    assert calls == [("/public/agk", ["/public/agk", "new", "shell", "literal; argument"])]
    assert os.environ["AGK_ENVIRONMENT"] == "caller-environment"


def test_root_never_executes_private_path_or_source_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "PUBLIC_LAUNCHER", tmp_path / "missing")
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli.shutil, "which", lambda _: pytest.fail("root must not search private PATH"))
    with pytest.raises(StationError, match="tui-install"):
        cli._agk_launcher()


def test_source_launcher_is_not_an_installed_component(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "PUBLIC_LAUNCHER", tmp_path / "missing")
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli.shutil, "which", lambda _: str(ROOT / "components/agk-tui/bin/agk"))
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    with pytest.raises(StationError, match="tui-install"):
        cli._agk_launcher()


def test_public_launcher_preferred_and_validated(monkeypatch, tmp_path):
    public = tmp_path / "agk"
    public.write_text("fixture")
    calls = []
    monkeypatch.setattr(launcher, "PUBLIC_LAUNCHER", public)
    monkeypatch.setattr(launcher, "validate_public_launcher", lambda: calls.append("validated"))
    monkeypatch.setattr(cli.shutil, "which", lambda _: pytest.fail("must use public handoff first"))
    assert cli._agk_launcher() == public
    assert calls == ["validated"]


def test_tui_install_cli_dispatch(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "install_agk_launcher", lambda paths, **kwargs: calls.append(kwargs) or {"state": "PREPARED"})
    assert cli.main(["tui-install", "--operator", "agk-station", "--plan"]) == 0
    assert calls == [{"operator": "agk-station", "plan": True}]
    assert "PREPARED" in capsys.readouterr().out


def test_tui_install_oserror_is_sanitized(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("private credential material must not be printed")
    monkeypatch.setattr(launcher, "install_agk_launcher", fail)
    assert cli.main(["tui-install", "--operator", "agk-station"]) == 2
    assert "private credential material" not in capsys.readouterr().err


def test_bootstrap_publication_is_after_private_build_before_success():
    source = (ROOT / "bootstrap.sh").read_text()
    build = source.index('bash "$agk_src/install.sh" --prefix "$STATION_HOME/.local" --without-hermes')
    publish = source.index('"$REPO_DIR/station" tui-install --operator "$STATION_USER"')
    assert build < publish < source.index("bootstrap_checkpoint agk-tui success")
