import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install"


def test_online_installer_is_valid_bash_and_documents_the_one_liner():
    syntax = subprocess.run(
        ["bash", "-n", str(INSTALL)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    help_result = subprocess.run(
        ["bash", str(INSTALL), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "curl -fsSL" in help_result.stdout
    assert "| sudo bash" in help_result.stdout
    assert "macOS" in help_result.stdout
    assert "| bash" in help_result.stdout
    assert "--core-only" in help_result.stdout
    assert "--dry-run" in help_result.stdout
    assert "--ref REF" in help_result.stdout


def test_online_installer_downloads_a_scoped_archive_and_checks_its_layout():
    source = INSTALL.read_text(encoding="utf-8")

    assert "https://codeload.github.com/$repository/tar.gz/$ref" in source
    assert "--proto '=https'" in source
    assert "--tlsv1.2" in source
    assert "--retry-all-errors" in source
    assert "refusing an archive with unsafe paths" in source
    for expected in (
        "bootstrap-vps.sh",
        "bootstrap-macos.sh",
        "install.sh",
        "scripts/repair-rmux-daemon.sh",
        "apps/agk-tui/Cargo.toml",
    ):
        assert expected in source
    assert "bootstrap=bootstrap-vps.sh" in source
    assert "bootstrap=bootstrap-macos.sh" in source
    assert 'bash "$source_dir/$bootstrap"' in source
