import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap-macos.sh"
RMUX_REPAIR = ROOT / "scripts/repair-rmux-daemon.sh"


def test_macos_bootstrap_is_valid_and_stays_single_user():
    result = subprocess.run(
        ["bash", "-n", str(BOOTSTRAP)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "rmux-$rmux_version-macos-$machine.tar.gz" in source
    assert "shasum -a 256 -c -" in source
    assert "cargo build --locked --release" in source
    assert "uv python install 3.12" in source
    assert "install hermes --no-login" in source
    assert "without sudo" in source
    assert "useradd" not in source
    assert "systemctl" not in source
    assert "apt-get" not in source
    assert "repair-rmux-daemon.sh" in source


def test_macos_bootstrap_installs_the_client_control_plane_contract():
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert '"$install_root/client"' in source
    assert "client_control.py" in source
    assert 'cp -R "$repo_root/client" "$install_root/client"' in source
    assert "client-init client-doctor client-status client-env provision-client" in source


def test_launchers_derive_their_install_root_from_the_prefix():
    for launcher in (ROOT / "bin/agk", ROOT / "bin/agk-terminal"):
        source = launcher.read_text(encoding="utf-8")
        assert 'launcher=$(resolve_launcher "${BASH_SOURCE[0]}")' in source
        assert 'prefix_root=$(cd "$(dirname "$launcher")/.."' in source
        assert "AGK_TERMINAL_ROOT:-$prefix_root/lib/agk-terminal" in source


def test_incompatible_current_user_rmux_daemon_is_replaced_safely(tmp_path):
    endpoint = tmp_path / "default"
    ready = tmp_path / "ready"
    daemon_script = tmp_path / "rmux-old-daemon.py"
    daemon_script.write_text(
        """import socket, sys, time
sock = socket.socket(socket.AF_UNIX)
sock.bind(sys.argv[1])
sock.listen(1)
open(sys.argv[2], 'w').close()
while True:
    time.sleep(1)
""",
        encoding="utf-8",
    )
    daemon = subprocess.Popen(
        [sys.executable, str(daemon_script), str(endpoint), str(ready)]
    )
    try:
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.01)
        assert ready.exists()

        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        lsof = fake_bin / "lsof"
        lsof.write_text(f"#!/bin/sh\necho {daemon.pid}\n", encoding="utf-8")
        lsof.chmod(0o755)
        rmux = fake_bin / "rmux"
        rmux.write_text(
            f"""#!/bin/sh
if [ -S {endpoint} ]; then
  echo '{endpoint}: protocol error: unsupported RMUX wire version 1; supported range is 8..=8' >&2
  exit 1
fi
exit 0
""",
            encoding="utf-8",
        )
        rmux.chmod(0o755)

        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        result = subprocess.run(
            ["bash", str(RMUX_REPAIR), str(rmux)],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "replacing incompatible current-user RMUX daemon" in result.stdout
        assert "protocol is compatible" in result.stdout
        assert not endpoint.exists()
        assert list(tmp_path.glob("default.agk-incompatible.*"))
    finally:
        if daemon.poll() is None:
            daemon.terminate()
        daemon.wait(timeout=5)


def test_rmux_repair_does_not_mask_unrelated_failures(tmp_path):
    rmux = tmp_path / "rmux"
    rmux.write_text("#!/bin/sh\necho 'ordinary failure' >&2\nexit 7\n", encoding="utf-8")
    rmux.chmod(0o755)
    result = subprocess.run(
        ["bash", str(RMUX_REPAIR), str(rmux)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 7
    assert "ordinary failure" in result.stderr
