import os
import pty
import subprocess
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "agk-terminal"
AGK = ROOT / "bin" / "agk"


def composio_fixture(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.log"
    composio = fake_bin / "composio"
    composio.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  whoami)
    if [ -s "$HOME/.composio/user_data.json" ]; then
      echo '{"account_type":"human"}'
    fi
    ;;
  login)
    mkdir -p "$HOME/.composio"
    echo '{"api_key":"test-key"}' > "$HOME/.composio/user_data.json"
    echo login >> "$COMPOSIO_TEST_LOG"
    ;;
  link)
    echo "link:${2:-}" >> "$COMPOSIO_TEST_LOG"
    ;;
  *) exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    composio.chmod(0o755)
    install = tmp_path / "install"
    inventory = install / "scripts/composio_inventory.py"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        "#!/usr/bin/env bash\necho inventory >> \"$COMPOSIO_TEST_LOG\"\n",
        encoding="utf-8",
    )
    inventory.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "AGK_TERMINAL_ROOT": str(install),
            "COMPOSIO_TEST_LOG": str(log),
            "HOME": str(home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        }
    )
    return env, log


def test_composio_connect_logs_in_the_current_profile_then_links(tmp_path: Path):
    env, log = composio_fixture(tmp_path)

    result = subprocess.run(
        [str(CLI), "composio", "connect", "github"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "login required" in result.stdout.lower()
    assert log.read_text(encoding="utf-8").splitlines() == [
        "login",
        "link:github",
        "inventory",
    ]


def test_composio_connect_does_not_repeat_an_existing_login(tmp_path: Path):
    env, log = composio_fixture(tmp_path)
    auth = Path(env["HOME"]) / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key"}\n', encoding="utf-8")

    result = subprocess.run(
        [str(CLI), "composio", "connect", "github"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == ["link:github", "inventory"]


def test_composio_status_explains_profile_local_setup(tmp_path: Path):
    env, _ = composio_fixture(tmp_path)

    result = subprocess.run(
        [str(CLI), "composio", "status"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "SETUP REQUIRED" in result.stdout
    assert "agk composio login" in result.stdout


def test_setup_cli_works_when_systemd_does_not_define_home(tmp_path: Path):
    install = tmp_path / "install"
    topology = install / "scripts/topology.py"
    topology.parent.mkdir(parents=True)
    topology.write_text("#!/bin/sh\nprintf 'topology-ok\\n'\n", encoding="utf-8")
    topology.chmod(0o755)
    env = os.environ.copy()
    env.pop("HOME", None)
    env["AGK_TERMINAL_ROOT"] = str(install)

    result = subprocess.run(
        [str(CLI), "topology", "status"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "topology-ok\n"


@pytest.mark.parametrize("args", [[], ["tui"]])
def test_agk_launcher_exports_current_linux_identity_as_environment(tmp_path: Path, args):
    install = tmp_path / "install"
    tui = install / "bin" / "agk-tui"
    tui.parent.mkdir(parents=True)
    tui.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"${AGK_ENVIRONMENT:-missing}\"\n",
        encoding="utf-8",
    )
    tui.chmod(0o755)
    env = os.environ.copy()
    env.pop("USER", None)
    env.pop("AGK_ENVIRONMENT", None)
    env["AGK_TERMINAL_ROOT"] = str(install)

    master, slave = pty.openpty()
    try:
        result = subprocess.run(
            [str(AGK), *args], env=env, text=True, stdin=slave, stdout=slave,
            stderr=subprocess.PIPE, check=False, timeout=5
        )
        output = os.read(master, 4096).decode()
    finally:
        os.close(slave)
        os.close(master)

    expected = subprocess.run(
        ["id", "-un"], text=True, capture_output=True, check=True
    ).stdout.strip()
    assert result.returncode == 0, result.stderr
    assert output.strip() == expected


@pytest.mark.parametrize("args", [[], ["tui"], ["tui", "--unexpected"]])
def test_noninteractive_empty_agk_never_starts_native_or_python_runtime(tmp_path, args):
    install = tmp_path / "install"
    marker = tmp_path / "unexpected-start"
    for relative in ("bin/agk-tui", "scripts/agk_control.py"):
        file = install / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        file.chmod(0o755)
    env = {**os.environ, "AGK_TERMINAL_ROOT": str(install)}
    result = subprocess.run([str(AGK), *args], env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert "interactive terminal" in result.stderr or "without additional arguments" in result.stderr
    assert not marker.exists()


def test_agk_help_documents_interactive_session_and_setup_surfaces():
    result = subprocess.run(
        [str(AGK), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for command in ("agk new", "agk close", "agk provider", "agk composio", "agk topology"):
        assert command in result.stdout
