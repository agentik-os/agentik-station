import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap-vps.sh"


def test_fresh_vps_dry_run_covers_every_runtime_boundary_and_shared_core():
    result = subprocess.run(
        [str(BOOTSTRAP), "--dry-run", "--skip-packages", "--core-only"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for profile in ("operator", "agentik", "mission", "private"):
        assert profile in result.stdout
    for expected in (
        "four Linux runtime boundaries",
        "Composio CLI independently",
        "shared official Hermes",
        "TopologyManager apply",
        "https://agentik-os.com",
        "Credentials were not copied",
    ):
        assert expected in result.stdout


def test_bootstrap_help_documents_safe_scope_controls():
    result = subprocess.run(
        [str(BOOTSTRAP), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--skip-packages" in result.stdout
    assert "--core-only" in result.stdout
