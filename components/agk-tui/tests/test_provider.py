import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "scripts/provider.sh"


def test_no_login_install_only_checks_the_provider_binary(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls"
    claude = fake_bin / "claude"
    claude.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' \"$*\" >> \"$PROVIDER_CALLS\"
case \"${1:-}\" in
  --version) echo '1.0.0' ;;
  *) exit 9 ;;
esac
""",
        encoding="utf-8",
    )
    claude.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PROVIDER_CALLS": str(calls),
        }
    )

    result = subprocess.run(
        [str(PROVIDER), "install", "claude", "--no-login"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["--version"]


def test_openrouter_no_login_never_opens_model_setup(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    checkout = tmp_path / "official-hermes"
    (checkout / ".git").mkdir(parents=True)
    calls = tmp_path / "calls"
    for name, script in {
        "hermes": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$PROVIDER_CALLS"\n'
                  'case "$1" in --version) printf "Install directory: %s\\n" "$PROVIDER_INSTALL";; *) exit 91;; esac\n',
        "git": '#!/bin/sh\nprintf "%s\\n" "https://github.com/NousResearch/hermes-agent.git"\n',
    }.items():
        binary = fake_bin / name
        binary.write_text(script)
        binary.chmod(0o755)
    env = {"HOME": str(tmp_path / "home"), "PATH": f"{fake_bin}:/usr/bin:/bin",
           "HERMES_HOME": str(tmp_path / "home/.hermes"), "OPENROUTER_API_KEY": "",
           "PROVIDER_CALLS": str(calls), "PROVIDER_INSTALL": str(checkout),
           "AGK_TERMINAL_ROOT": str(tmp_path / "component")}
    result = subprocess.run([str(PROVIDER), "install", "openrouter", "--no-login"], env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert set(calls.read_text().splitlines()) == {"--version"}
