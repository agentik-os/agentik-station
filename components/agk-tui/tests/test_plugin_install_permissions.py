from pathlib import Path
import re
import shutil
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("install.sh", "bootstrap-macos.sh", "scripts/sync-hermes.sh")


@pytest.mark.parametrize("script", SCRIPTS)
def test_new_plugin_copy_restricts_checkout_modes_without_opening_other_files(tmp_path, script):
    source = (ROOT / script).read_text(encoding="utf-8")
    match = re.search(r"(?m)^restrict_plugin_modes\(\) \{\n.*?^\}", source, re.DOTALL)
    assert match
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o775)
    checkout.chmod(0o775)
    helper = checkout / "agk_session_panel.py"
    helper.write_text("# synthetic software\n", encoding="utf-8")
    helper.chmod(0o664)
    private = checkout / "private-reference"
    private.write_text("synthetic private fixture", encoding="utf-8")
    private.chmod(0o600)
    outside = tmp_path / "outside"
    outside.write_text("untouched fixture", encoding="utf-8")
    outside.chmod(0o666)
    (checkout / "unfollowed-link").symlink_to(outside)
    installed = tmp_path / "installed"
    shutil.copytree(checkout, installed, symlinks=True)
    result = subprocess.run(
        ["bash", "-c", match.group(0) + '\numask 0002\nrestrict_plugin_modes "$1"\n',
         "plugin-mode-fixture", str(installed)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(installed.stat().st_mode) == 0o755
    assert stat.S_IMODE((installed / helper.name).stat().st_mode) == 0o644
    assert (installed / helper.name).read_bytes() == helper.read_bytes()
    assert stat.S_IMODE((installed / private.name).stat().st_mode) == 0o600
    assert stat.S_IMODE(outside.stat().st_mode) == 0o666
    assert (installed / "unfollowed-link").is_symlink()
    if script == "scripts/sync-hermes.sh":
        assert source.index('cp -a "$install_root/hermes/plugins/$plugin_path"') < source.index(
            'restrict_plugin_modes "$plugin_target.new"') < source.index('mv "$plugin_target.new" "$plugin_target"')
    else:
        assert source.index('cp -a "$repo_root/hermes/plugins/platforms/discord"'
                            if script == "install.sh" else 'cp -R "$repo_root/hermes/plugins/platforms/discord"') < source.index(
            'restrict_plugin_modes "$install_root/hermes/plugins/agentik_os"')
