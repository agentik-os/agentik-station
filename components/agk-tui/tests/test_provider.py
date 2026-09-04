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
