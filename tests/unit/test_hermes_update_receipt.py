import getpass
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_failed_gateway_cannot_produce_successful_update_receipt(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq is required by the shell updater")
    fake = tmp_path / "hermes-fixture"
    fake.write_text('#!/bin/sh\ncase "$1" in\nversion) echo fixture;;\nupdate|doctor) exit 0;;\ngateway) exit 3;;\n*) exit 99;;\nesac\n')
    fake.chmod(0o700)
    receipts = tmp_path / "receipts"
    env = {**os.environ, "STATION_USER": getpass.getuser(), "STATION_HOME": str(tmp_path),
           "HERMES_HOME": str(tmp_path / "hermes"), "HERMES_BIN": str(fake),
           "HERMES_UPDATE_RECEIPTS": str(receipts), "HERMES_INSTALL_DIR": str(tmp_path / "not-a-repo")}
    result = subprocess.run(["bash", str(ROOT / "scripts/station_hermes_update.sh"), "update"], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stderr
    receipt = json.loads((receipts / "latest.json").read_text())
    assert receipt["status"] == "DEGRADED_GATEWAY_FAILED"
    assert receipt["returncodes"]["gateway"] == 3
    assert receipt["operational_claim"] is False
