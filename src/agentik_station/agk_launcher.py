"""Publish a narrow operator handoff, never operator software running as root."""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import stat

from .errors import SecurityError, StationError, ValidationError
from .filesystem import SafeFS
from .installer import install_lock
from .models import new_operation_id
from .os_lifecycle import _directory, _read_at
from .paths import LayoutPaths


OPERATOR = "agk-station"
OPERATOR_HOME = Path("/home/agk-station")
PUBLIC_LAUNCHER = Path("/usr/local/bin/agk")


def _operator():
    try:
        account = pwd.getpwnam(OPERATOR)
    except KeyError:
        raise ValidationError("The dedicated agk-station account is not installed") from None
    if (account.pw_name != OPERATOR or account.pw_uid <= 0 or account.pw_gid <= 0
            or account.pw_dir != str(OPERATOR_HOME)):
        raise SecurityError("The AGK operator account does not match the canonical identity")
    return account


def _render_launcher(uid: int, gid: int) -> str:
    # Standalone stdlib-only, isolated Python: no operator/user Python is loaded
    # until AFTER sudo/runuser has switched identity. All execution uses argv.
    return '''#!/usr/bin/python3 -I
# Agentik Station: managed AGK operator handoff, schema 1.
import os
import pwd
import re
import sys

OPERATOR = "agk-station"
HOME = "/home/agk-station"
PUBLIC = "/usr/local/bin/agk"
UID = %d
GID = %d


def main():
    args = sys.argv[1:]
    if args == ["tui"]:
        args = []
    elif args[:1] == ["tui"]:
        print("Use agk tui without additional arguments, or agk help.", file=sys.stderr)
        return 2
    if args[:1] in (["help"], ["-h"], ["--help"]):
        print("AGK · Station operator control surface\\n"
              "  agk | agk tui   Open interactive RMUX sessions\\n"
              "  agk status      Inspect operator sessions\\n"
              "  station tui     Open the same interface\\n"
              "Runs as agk-station using your existing sudo authorization.\\n"
              "No accounts or credentials are copied. Zone/OS gateways remain separate.")
        return 0
    if not args and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        print("AGK requires an interactive terminal; use agk help or agk status.", file=sys.stderr)
        return 2
    try:
        account = pwd.getpwnam(OPERATOR)
    except KeyError:
        print("AGK operator is missing; ask the Station administrator to repair installation.", file=sys.stderr)
        return 2
    if (account.pw_uid, account.pw_gid, account.pw_dir) != (UID, GID, HOME):
        print("AGK operator identity changed; administrator review is required.", file=sys.stderr)
        return 2
    term = os.environ.get("TERM", "xterm-256color")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+_.-]{0,79}", term):
        term = "xterm-256color"
    clean = {"PATH": "/usr/local/bin:/usr/bin:/bin", "TERM": term,
             "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    if os.geteuid() != UID:
        # Re-enter this root-owned launcher ONCE after the existing permission
        # check. No shell, login startup file, caller cwd or environment is used.
        if os.geteuid() == 0:
            binary = "/usr/sbin/runuser"
            argv = [binary, "--user", OPERATOR, "--", PUBLIC, *args]
        else:
            binary = "/usr/bin/sudo"
            argv = [binary, "-H", "-u", OPERATOR, "--", PUBLIC, *args]
        os.chdir("/")
        os.execve(binary, argv, clean)
    if os.getuid() != UID or os.getegid() != GID:
        print("AGK requires the canonical operator identity.", file=sys.stderr)
        return 2
    root = HOME + "/.local/lib/agk-terminal"
    clean.update({"HOME": HOME, "USER": OPERATOR, "LOGNAME": OPERATOR,
                  "HERMES_HOME": HOME + "/.hermes", "AGK_ENVIRONMENT": OPERATOR,
                  "AGK_TERMINAL_ROOT": root,
                  "PATH": root + "/bin:" + HOME + "/.local/bin:" + HOME
                          + "/.cargo/bin:/usr/local/bin:/usr/bin:/bin"})
    os.chdir(HOME)
    launcher = HOME + "/.local/bin/agk"
    os.execve(launcher, [launcher, *args], clean)
    return 0


try:
    raise SystemExit(main())
except OSError:
    print("AGK handoff failed; ask the administrator to run station tui-install --operator agk-station.",
          file=sys.stderr)
    raise SystemExit(2)
''' % (uid, gid)


def _payload_present(account) -> None:
    root = OPERATOR_HOME / ".local/lib/agk-terminal"
    for path in (OPERATOR_HOME / ".local/bin/agk", root / "bin/agk-tui",
                 root / "scripts/agk_control.py"):
        with _directory(path.parent, uid=account.pw_uid, trusted_root=OPERATOR_HOME) as parent:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != account.pw_uid or info.st_mode & 0o022
                    or not info.st_mode & stat.S_IXUSR):
                raise SecurityError("The private AGK installation is missing or unsafe; repair it as its operator")
    # Native install.sh intentionally exposes RMUX through a symlink. This
    # handoff checks AGK presence only; it does not attest the daemon or alias.


def _public_state(paths: LayoutPaths, payload: str, owner: int) -> bool:
    # Live parents must ALL be root-owned and non-writable by other identities.
    # Tests anchor beneath an isolated fixture, never weaken the production path.
    with _directory(paths.bin, uid=owner,
                    trusted_root=paths.bin if paths.test_mode else None) as parent:
        try:
            current = _read_at(parent, "agk", uid=owner, limit=16384, immutable=True)
        except FileNotFoundError:
            return False
        info = os.stat("agk", dir_fd=parent, follow_symlinks=False)
        if current != payload.encode() or stat.S_IMODE(info.st_mode) != 0o755:
            raise SecurityError("Refusing to replace an unrelated or changed public agk launcher")
    return True


def validate_public_launcher() -> None:
    """Do not mistake an unrelated root-owned `agk` for our identity handoff."""
    account = _operator()
    if not _public_state(LayoutPaths.live(), _render_launcher(account.pw_uid, account.pw_gid), 0):
        raise StationError("The public AGK handoff is missing; run station tui-install --operator agk-station")


def install_agk_launcher(paths: LayoutPaths, *, operator: str, plan: bool = False) -> dict:
    """Repair public entry only; no component reinstall, sudo grant or auth copy."""
    if operator != OPERATOR:
        raise ValidationError("Only the canonical agk-station operator may own this AGK entrypoint")
    if not paths.test_mode and paths != LayoutPaths.live():
        raise SecurityError("AGK publication requires the canonical Station paths")
    if not plan and not paths.test_mode and os.geteuid() != 0:
        raise StationError("Installing the public AGK launcher requires the administrator's existing sudo authorization")
    account = _operator()
    payload = _render_launcher(account.pw_uid, account.pw_gid)
    owner = os.getuid() if paths.test_mode else 0

    def inspect():
        _payload_present(account)
        return _public_state(paths, payload, owner)

    if plan:
        exists = inspect()
    else:
        with install_lock(paths, new_operation_id()):
            exists = inspect()
            if not exists:
                SafeFS([paths.bin]).write_text(paths.bin / "agk", payload, mode=0o755,
                                               owner=(owner, os.getgid() if paths.test_mode else 0))
            _public_state(paths, payload, owner)
    return {"schema_version": 1, "state": "PREPARED" if plan else "INSTALLED",
            "operator": OPERATOR, "home": str(OPERATOR_HOME),
            "launcher": str(paths.bin / "agk"), "already_installed": exists,
            "runtime_verified": False,
            "next": "From your SSH terminal run agk (existing sudo authorization is required)."}
