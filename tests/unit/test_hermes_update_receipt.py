import getpass
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def updater(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq is required by the shell updater")
    fake = tmp_path / "hermes-fixture"
    fake.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_ARGV_LOG"
case "$#:$*" in
  '1:--version')
    if [ -e "$FAKE_VERSION_MARKER" ]; then
      probe_rc="$AFTER_VERSION_RC"
      empty="$AFTER_VERSION_EMPTY"
    else
      : > "$FAKE_VERSION_MARKER"
      probe_rc="$BEFORE_VERSION_RC"
      empty="$BEFORE_VERSION_EMPTY"
    fi
    if [ "$probe_rc" -ne 0 ]; then
      echo 'SECRET_VERSION_PROBE_STDOUT'
      echo 'SECRET_VERSION_PROBE_STDERR' >&2
      exit "$probe_rc"
    fi
    [ "$empty" -eq 1 ] && exit 0
    printf 'Hermes fixture\\nSECRET_VERSION_DETAIL\\n';;
  '2:update --check') exit "$CHECK_RC";;
  '3:update --backup --yes') exit "$UPDATE_RC";;
  '1:doctor') exit "$DOCTOR_RC";;
  '2:gateway status') exit "$GATEWAY_RC";;
  *) echo 'unsupported Hermes argv' >&2; exit 99;;
esac
''')
    fake.chmod(0o700)
    receipts = tmp_path / "receipts"
    calls = tmp_path / "argv.log"
    env = {**os.environ, "STATION_USER": getpass.getuser(), "STATION_HOME": str(tmp_path),
           "HERMES_HOME": str(tmp_path / "hermes"), "HERMES_BIN": str(fake),
           "HERMES_UPDATE_RECEIPTS": str(receipts), "HERMES_INSTALL_DIR": str(tmp_path / "not-a-repo"),
           "FAKE_ARGV_LOG": str(calls), "CHECK_RC": "0", "UPDATE_RC": "0",
           "DOCTOR_RC": "0", "GATEWAY_RC": "0",
           "FAKE_VERSION_MARKER": str(tmp_path / "version-probed"),
           "BEFORE_VERSION_RC": "0", "AFTER_VERSION_RC": "0",
           "BEFORE_VERSION_EMPTY": "0", "AFTER_VERSION_EMPTY": "0"}

    def run(mode="update", **returncodes):
        result = subprocess.run(["bash", str(ROOT / "scripts/station_hermes_update.sh"), mode],
                                env={**env, **{name: str(value) for name, value in returncodes.items()}},
                                capture_output=True, text=True, timeout=30)
        receipt_text = (receipts / "latest.json").read_text()
        receipt = json.loads(receipt_text)
        before_rc = returncodes.get("BEFORE_VERSION_RC", 0) or (2 if returncodes.get("BEFORE_VERSION_EMPTY", 0) else 0)
        after_rc = (-1 if before_rc else returncodes.get("AFTER_VERSION_RC", 0)
                    or (2 if returncodes.get("AFTER_VERSION_EMPTY", 0) else 0))
        assert receipt["before"]["version"] == ("" if before_rc else "Hermes fixture")
        assert receipt["after"]["version"] == ("" if after_rc else "Hermes fixture")
        assert receipt["returncodes"]["before_version"] == before_rc
        assert receipt["returncodes"]["after_version"] == after_rc
        assert "SECRET_VERSION_" not in receipt_text + result.stdout + result.stderr
        assert receipt["operational_claim"] is False
        assert (receipts / "latest.json").stat().st_mode & 0o777 == 0o600
        return SimpleNamespace(result=result, receipt=receipt, calls=calls.read_text().splitlines())

    return run


@pytest.mark.parametrize("check_rc", [0, 7])
def test_check_only_uses_exact_native_argv_without_update_or_restore(updater, check_rc):
    observed = updater("check", CHECK_RC=check_rc)
    assert observed.result.returncode == (1 if check_rc else 0), observed.result.stderr
    assert observed.calls == ["--version", "update --check", "--version"]
    assert observed.receipt["status"] == ("CHECK_FAILED" if check_rc else "CHECKED_NOT_APPLIED")
    if check_rc:
        assert "repair upstream access" in observed.receipt["next_repair_action"]
    assert observed.receipt["returncodes"] == {"update": check_rc, "doctor": -1, "gateway": -1, "rollback": -1,
                                               "before_version": 0, "after_version": 0}


@pytest.mark.parametrize("mode", ["update"])
def test_successful_update_uses_exact_native_argv_without_restore(updater, mode):
    observed = updater(mode)
    assert observed.result.returncode == 0, observed.result.stderr
    assert observed.calls == ["--version", "update --backup --yes", "doctor", "gateway status", "--version"]
    assert observed.receipt["status"] == "VERIFIED_UPDATED"
    assert observed.receipt["returncodes"] == {"update": 0, "doctor": 0, "gateway": 0, "rollback": -1,
                                               "before_version": 0, "after_version": 0}


def test_failed_gateway_cannot_produce_successful_update_receipt(updater):
    observed = updater(GATEWAY_RC=3)
    result, receipt = observed.result, observed.receipt
    assert result.returncode == 1, result.stderr
    assert receipt["status"] == "DEGRADED_GATEWAY_FAILED"
    assert receipt["returncodes"]["gateway"] == 3
    assert receipt["returncodes"]["rollback"] == -1
    assert "owning Hermes gateway" in receipt["next_repair_action"]
    assert observed.calls == ["--version", "update --backup --yes", "doctor", "gateway status", "--version"]


def test_failed_native_update_does_not_restore_an_unconfirmed_backup(updater):
    observed = updater(UPDATE_RC=5)
    assert observed.result.returncode == 1, observed.result.stderr
    assert observed.calls == ["--version", "update --backup --yes", "gateway status", "--version"]
    assert observed.receipt["status"] == "UPDATE_FAILED"
    assert observed.receipt["returncodes"] == {"update": 5, "doctor": -1, "gateway": 0, "rollback": -1,
                                               "before_version": 0, "after_version": 0}
    assert "review state and code recovery" in observed.receipt["next_repair_action"]


@pytest.mark.parametrize("gateway_rc", [0, 3])
def test_failed_doctor_requires_manual_recovery_without_inventing_restore_argv(updater, gateway_rc):
    observed = updater(DOCTOR_RC=4, GATEWAY_RC=gateway_rc)
    assert observed.result.returncode == 1, observed.result.stderr
    assert observed.calls == ["--version", "update --backup --yes", "doctor",
                              "gateway status", "--version"]
    assert observed.receipt["status"] == "DEGRADED_DOCTOR_FAILED"
    assert observed.receipt["returncodes"] == {"update": 0, "doctor": 4, "gateway": gateway_rc, "rollback": -1,
                                               "before_version": 0, "after_version": 0}
    assert observed.receipt["logs"]["rollback"] == ""
    repair = observed.receipt["next_repair_action"]
    assert "native Hermes backup" in repair
    assert "review state and code recovery" in repair
    assert "no automatic restore was attempted" in repair
    assert f"NEXT_REPAIR_ACTION={repair}" in observed.result.stdout


@pytest.mark.parametrize("mode", ["check", "update"])
@pytest.mark.parametrize("failure", [{"BEFORE_VERSION_RC": 17}, {"BEFORE_VERSION_EMPTY": 1}])
def test_before_version_failure_records_receipt_without_attempting_update(updater, mode, failure):
    observed = updater(mode, **failure)
    assert observed.result.returncode == 1, observed.result.stderr
    assert observed.calls == ["--version"]
    assert observed.receipt["status"] == "VERSION_PROBE_FAILED"
    for name in ("update", "doctor", "gateway", "rollback", "after_version"):
        assert observed.receipt["returncodes"][name] == -1
    assert all(value == "" for value in observed.receipt["logs"].values())
    assert "no update was attempted" in observed.receipt["next_repair_action"]


@pytest.mark.parametrize("mode", ["check", "update"])
@pytest.mark.parametrize("failure", [{"AFTER_VERSION_RC": 19}, {"AFTER_VERSION_EMPTY": 1}])
def test_after_version_failure_cannot_leave_a_successful_receipt(updater, mode, failure):
    observed = updater(mode, **failure)
    assert observed.result.returncode == 1, observed.result.stderr
    expected = ["--version", "update --check", "--version"] if mode == "check" else [
        "--version", "update --backup --yes", "doctor", "gateway status", "--version"]
    assert observed.calls == expected
    assert observed.receipt["status"] == "VERSION_READBACK_FAILED"
    assert observed.receipt["returncodes"]["update"] == 0
    assert "Repair Hermes --version readback" in observed.receipt["next_repair_action"]


@pytest.mark.parametrize(("mode", "failure", "status"), [
    ("check", {"CHECK_RC": 7}, "CHECK_FAILED"),
    ("update", {"UPDATE_RC": 5}, "UPDATE_FAILED"),
    ("update", {"DOCTOR_RC": 4}, "DEGRADED_DOCTOR_FAILED"),
    ("update", {"GATEWAY_RC": 3}, "DEGRADED_GATEWAY_FAILED"),
])
def test_after_version_failure_preserves_primary_failure(updater, mode, failure, status):
    observed = updater(mode, AFTER_VERSION_RC=19, **failure)
    assert observed.result.returncode == 1, observed.result.stderr
    assert observed.receipt["status"] == status
    assert observed.receipt["returncodes"]["after_version"] == 19
    assert observed.receipt["returncodes"]["rollback"] == -1
    assert "Repair Hermes --version readback" in observed.receipt["next_repair_action"]
    if status in {"UPDATE_FAILED", "DEGRADED_DOCTOR_FAILED"}:
        assert "review state and code recovery" in observed.receipt["next_repair_action"]
