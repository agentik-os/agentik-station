"""Bootstrap lifecycle tests use owned temporary roots and synthetic processes."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agentik_station import bootstrap_state as state_module
from agentik_station.bootstrap_state import BootstrapState, FEATURES, load_bootstrap_report, selected_stages
from agentik_station.constants import PRODUCT_VERSION
from agentik_station.errors import ReconcileError, SecurityError, ValidationError
from agentik_station.models import InstallSpec

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fixture(tmp_path):
    source = tmp_path / "source"
    (source / "config").mkdir(parents=True)
    for name, content in {"VERSION": PRODUCT_VERSION, "RELEASE_PROVENANCE.json": '{}',
                          "config/versions.lock": 'FIXTURE=1\n', "bootstrap.sh": '# fixture\n'}.items():
        (source / name).write_text(content)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(InstallSpec(operation_id="op-fixture-kernel", release_version=PRODUCT_VERSION).to_dict()))
    options = {**{name: False for name in FEATURES}, "mode": "full", "sudo_mode": "password"}
    state = BootstrapState(tmp_path / "state", tmp_path / "lock", owner_uid=os.geteuid())
    lock = state.prepare_lock()
    fd = os.open(lock, os.O_RDWR)
    state.acquire(fd)
    def report():
        return load_bootstrap_report(state.state_root, state.lock_root, _owner_uid=os.geteuid())
    def begin(**kwargs):
        return state.begin(spec_path, source, options, **kwargs)
    def receipt_path(attempt):
        return state.state_root / "attempts" / f"{attempt}.json"
    value = SimpleNamespace(state=state, options=options, source=source, spec=spec_path, fd=fd,
                            begin=begin, report=report, receipt_path=receipt_path)
    try:
        yield value
    finally:
        os.close(fd)


def test_report_missing_roots_is_read_only(tmp_path):
    state, lock = tmp_path / "state", tmp_path / "lock"
    report = load_bootstrap_report(state, lock, _owner_uid=os.geteuid())
    assert report == {"status": "not-started", "evidence_kind": "reported", "operational": False, "next_actions": []}
    assert not state.exists() and not lock.exists()


def test_receipt_binds_exact_spec_options_and_source(fixture, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "never-record-this-secret")
    attempt = fixture.begin()
    receipt = fixture.report()["latest"]
    assert receipt["status"] == "running"
    assert receipt["spec_sha256"] == hashlib.sha256(fixture.spec.read_bytes()).hexdigest()
    assert receipt["options"] == fixture.options
    assert receipt["source_files"]["bootstrap.sh"] == hashlib.sha256((fixture.source / "bootstrap.sh").read_bytes()).hexdigest()
    assert [stage["id"] for stage in receipt["stages"]] == selected_stages(fixture.options)
    assert all(stage["status"] == "pending" for stage in receipt["stages"])
    assert receipt["kernel_receipt"] == "op-fixture-kernel.json"
    assert receipt["operational"] is receipt["rollback_performed"] is False
    assert "never-record-this-secret" not in fixture.receipt_path(attempt).read_text()
    assert fixture.receipt_path(attempt).stat().st_mode & 0o777 == 0o600


def full_options():
    return {**{name: True for name in FEATURES}, "mode": "full", "sudo_mode": "password"}


LEGACY_FULL_STAGES = [
    "system-packages", "tailscale", "operator-account", "operator-sudo",
    "operator-checkout", "operator-profile", "hermes", "toolchain",
    "scrapegraphai", "crawl4ai", "voice", "agk-tui", "kernel-apply",
    "kernel-readback", "ai-stack", "guided-setup", "hermes-update-timer",
    "tool-inventory", "agk-metadata-sync",
]
AGGREGATE_FULL_STAGES = [stage for stage in LEGACY_FULL_STAGES
                         if stage not in {"scrapegraphai", "crawl4ai", "voice"}]
AGGREGATE_FULL_STAGES.insert(AGGREGATE_FULL_STAGES.index("hermes-update-timer"), "full-stack-verify")
DEFAULT_OS_FULL_STAGES = AGGREGATE_FULL_STAGES.copy()
DEFAULT_OS_FULL_STAGES.insert(DEFAULT_OS_FULL_STAGES.index("ai-stack"), "os-defaults")


@pytest.mark.parametrize("version", ["10.99", "11.9", "11.27", "11.27.9", "legacy-label"])
def test_legacy_full_graph_preserves_original_web_and_voice_gates(version):
    assert selected_stages(full_options(), version) == LEGACY_FULL_STAGES


@pytest.mark.parametrize("version", ["11.28", "11.28.0", "11.30"])
def test_full_graph_defers_web_and_voice_to_one_aggregate_stage(version):
    assert selected_stages(full_options(), version) == AGGREGATE_FULL_STAGES


def test_default_graph_uses_current_product_release():
    assert selected_stages(full_options()) == selected_stages(full_options(), PRODUCT_VERSION)
    assert selected_stages(full_options()) == DEFAULT_OS_FULL_STAGES


@pytest.mark.parametrize("version", ["11.31", "11.31.0", "11.100", "12.0"])
def test_default_os_native_teams_precede_optional_stack_and_preserve_old_graphs(version):
    assert selected_stages(full_options(), version) == DEFAULT_OS_FULL_STAGES
    assert "os-defaults" not in selected_stages({**full_options(), "hermes": False}, version)
    assert "os-defaults" in selected_stages({**full_options(), "ai_stack": False}, version)


@pytest.mark.parametrize("version", ["11.27", "11.28"])
def test_minimal_graph_keeps_independent_web_voice_and_parakeet_gates(version):
    options = {**full_options(), "ai_stack": False}
    expected = ["parakeet" if stage == "ai-stack" else stage for stage in LEGACY_FULL_STAGES]
    assert selected_stages(options, version) == expected


@pytest.mark.parametrize("version,expected", [
    ("11.27", LEGACY_FULL_STAGES), ("11.28", AGGREGATE_FULL_STAGES),
    ("11.31", DEFAULT_OS_FULL_STAGES),
])
def test_begin_and_receipt_readback_use_recorded_release_graph(fixture, version, expected):
    fixture.options.update(full_options())
    fixture.spec.write_text(json.dumps(InstallSpec(operation_id="op-fixture-kernel", release_version=version).to_dict()))
    (fixture.source / "VERSION").write_text(version)
    attempt = fixture.begin()
    receipt = fixture.report()["latest"]
    assert receipt["schema_version"] == 1 and receipt["spec"]["release_version"] == version
    assert [stage["id"] for stage in receipt["stages"]] == expected
    for stage in expected:
        fixture.state.checkpoint(attempt, stage, "running")
        fixture.state.checkpoint(attempt, stage, "success")
    fixture.state.finish(attempt, 0)
    before = fixture.receipt_path(attempt).read_bytes()
    report = fixture.report()
    assert report["status"] == "success" and report["operational"] is False
    assert [stage["id"] for stage in report["latest"]["stages"]] == expected
    assert fixture.receipt_path(attempt).read_bytes() == before


@pytest.mark.parametrize("version", ["11.27", "11.28"])
@pytest.mark.parametrize("defect", ["other-release-graph", "reordered"])
def test_receipt_rejects_wrong_release_graph_and_reordered_stages(fixture, version, defect):
    fixture.options.update(full_options())
    fixture.spec.write_text(json.dumps(InstallSpec(operation_id="op-fixture-kernel", release_version=version).to_dict()))
    (fixture.source / "VERSION").write_text(version)
    attempt = fixture.begin()
    path = fixture.receipt_path(attempt)
    payload = json.loads(path.read_text())
    if defect == "other-release-graph":
        other = AGGREGATE_FULL_STAGES if version == "11.27" else LEGACY_FULL_STAGES
        payload["stages"] = [{"id": stage, "status": "pending", "required": stage != "agk-metadata-sync",
                              "repair": state_module.REPAIR[stage]} for stage in other]
    else:
        payload["stages"][0], payload["stages"][1] = payload["stages"][1], payload["stages"][0]
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    assert fixture.report()["status"] == "unavailable"
    with pytest.raises(ValidationError, match="stage sequence"):
        fixture.begin(acknowledge=attempt)
    assert path.read_bytes() == before


def test_failed_full_verification_preserves_installer_success_but_blocks_completion(fixture):
    fixture.options.update(full_options())
    attempt = fixture.begin()
    for stage in DEFAULT_OS_FULL_STAGES[:DEFAULT_OS_FULL_STAGES.index("full-stack-verify")]:
        fixture.state.checkpoint(attempt, stage, "running")
        fixture.state.checkpoint(attempt, stage, "success")
    fixture.state.checkpoint(attempt, "full-stack-verify", "running")
    fixture.state.finish(attempt, 41)
    receipt = fixture.report()["latest"]
    stages = {stage["id"]: stage for stage in receipt["stages"]}
    assert receipt["status"] == "failed" and receipt["exit_code"] == 41
    assert stages["ai-stack"]["status"] == stages["guided-setup"]["status"] == "success"
    assert stages["full-stack-verify"]["status"] == "failed"
    assert stages["full-stack-verify"]["exit_code"] == 41
    assert stages["full-stack-verify"]["required"] is True
    assert all(stages[stage]["status"] == "pending" for stage in
               ("hermes-update-timer", "tool-inventory", "agk-metadata-sync"))
    assert "full-check" in receipt["next_actions"][0]
    assert receipt["operational"] is False
    with pytest.raises(ValidationError, match="already finished"):
        fixture.state.finish(attempt, 0)


def test_failed_stage_preserves_exit_code_and_later_pending(fixture):
    attempt = fixture.begin()
    fixture.state.checkpoint(attempt, "system-packages", "running")
    fixture.state.finish(attempt, 57)
    receipt = fixture.report()["latest"]
    assert receipt["status"] == "failed" and receipt["exit_code"] == 57
    assert receipt["stages"][0]["status"] == "failed"
    assert all(stage["status"] == "pending" for stage in receipt["stages"][1:])
    assert "apt/dpkg" in receipt["next_actions"][0]


def test_uncatchable_interruption_is_reported_without_rewriting_receipt(fixture):
    attempt = fixture.begin()
    fixture.state.checkpoint(attempt, "system-packages", "running")
    before = fixture.receipt_path(attempt).read_bytes()
    fcntl.flock(fixture.fd, fcntl.LOCK_UN)
    report = fixture.report()
    assert report["status"] == "interrupted"
    assert report["latest"]["stages"][0]["status"] == "interrupted"
    assert fixture.receipt_path(attempt).read_bytes() == before


def test_signal_interruption_records_original_signal_exit_code(fixture):
    attempt = fixture.begin()
    fixture.state.checkpoint(attempt, "system-packages", "running")
    fixture.state.finish(attempt, 143, interrupted=True)
    assert fixture.report()["latest"]["exit_code"] == 143
    assert fixture.report()["latest"]["stages"][0]["status"] == "interrupted"


def test_incomplete_attempt_requires_exact_ack_and_never_resumes(fixture):
    old = fixture.begin()
    fixture.state.checkpoint(old, "system-packages", "running")
    fixture.state.finish(old, 19)
    before = fixture.receipt_path(old).read_bytes()
    for ack in (None, "op-wrong"):
        with pytest.raises(ReconcileError, match="Incomplete bootstrap"):
            fixture.begin(acknowledge=ack)
    with pytest.raises(ValidationError):
        fixture.begin(acknowledge="../../outside")
    new = fixture.begin(acknowledge=old)
    receipt = fixture.report()["latest"]
    assert new != old and receipt["previous_incomplete"]["attempt_id"] == old
    assert receipt["previous_incomplete"]["acknowledged"] is True
    assert all(stage["status"] == "pending" for stage in receipt["stages"])
    assert fixture.receipt_path(old).read_bytes() == before
    with pytest.raises(ReconcileError):
        fixture.begin(acknowledge=old)


def test_success_requires_all_gates_and_preserves_optional_failure(fixture):
    attempt = fixture.begin()
    for stage in selected_stages(fixture.options):
        fixture.state.checkpoint(attempt, stage, "running")
        fixture.state.checkpoint(attempt, stage, "failed" if stage == "agk-metadata-sync" else "success", exit_code=23)
    fixture.state.finish(attempt, 0)
    receipt = fixture.report()["latest"]
    assert receipt["status"] == "success" and receipt["exit_code"] == 0
    assert receipt["stages"][-1]["status"] == "failed"
    assert receipt["stages"][-1]["exit_code"] == 23
    assert any("metadata" in action for action in receipt["next_actions"])
    assert receipt["operational"] is False
    with pytest.raises(ValidationError, match="acknowledgement"):
        fixture.begin(acknowledge=attempt)


def test_premature_success_and_out_of_order_or_repeated_stage_are_rejected(fixture):
    attempt = fixture.begin()
    with pytest.raises(ValidationError, match="sequence"):
        fixture.state.checkpoint(attempt, "tailscale", "running")
    fixture.state.checkpoint(attempt, "system-packages", "running")
    with pytest.raises(ValidationError):
        fixture.state.checkpoint(attempt, "system-packages", "running")
    with pytest.raises(ReconcileError, match="incomplete"):
        fixture.state.finish(attempt, 0)
    assert fixture.report()["status"] == "failed"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "world-writable", "fifo"])
def test_lock_rejects_unsafe_existing_file(tmp_path, kind):
    state = BootstrapState(tmp_path / "state", tmp_path / "lock", owner_uid=os.geteuid())
    state.lock_root.mkdir(mode=0o700)
    target = tmp_path / "untouched"
    target.write_text("keep")
    target.chmod(0o600)
    lock = state.lock_root / "bootstrap.lock"
    if kind == "symlink":
        lock.symlink_to(target)
    elif kind == "hardlink":
        os.link(target, lock)
    elif kind == "fifo":
        os.mkfifo(lock, 0o600)
    else:
        lock.write_text("")
        lock.chmod(0o666)
    with pytest.raises((SecurityError, OSError)):
        state.prepare_lock()
    assert target.read_text() == "keep"


def test_lock_rejects_symlinked_or_writable_ancestors(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    state = BootstrapState(tmp_path / "state", link / "lock", owner_uid=os.geteuid())
    with pytest.raises(SecurityError):
        state.prepare_lock()
    assert not (outside / "lock").exists()
    outside.chmod(0o777)
    state = BootstrapState(tmp_path / "state", outside / "lock", owner_uid=os.geteuid())
    with pytest.raises(SecurityError):
        state.prepare_lock()
    assert not (outside / "lock").exists()


def test_competing_open_cannot_acquire_singleton_lock(fixture):
    second = os.open(fixture.state.lock_root / "bootstrap.lock", os.O_RDWR)
    try:
        with pytest.raises(ReconcileError, match="Another bootstrap"):
            fixture.state.acquire(second)
    finally:
        os.close(second)


def test_lock_is_retained_by_parent_after_child_acquires(tmp_path):
    state = BootstrapState(tmp_path / "state", tmp_path / "lock", owner_uid=os.geteuid())
    lock = state.prepare_lock()
    fd = os.open(lock, os.O_RDWR)
    try:
        child = subprocess.run([sys.executable, "-c", "import fcntl,sys; fcntl.flock(int(sys.argv[1]),fcntl.LOCK_EX|fcntl.LOCK_NB)", str(fd)],
                               pass_fds=(fd,), check=True, capture_output=True)
        assert child.returncode == 0
        second = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(ReconcileError):
                state.acquire(second)
        finally:
            os.close(second)
    finally:
        os.close(fd)


def test_report_distinguishes_unreadable_and_discards_debug_fields(fixture, monkeypatch):
    attempt = fixture.begin()
    path = fixture.receipt_path(attempt)
    payload = json.loads(path.read_text())
    payload.update(argv=["sensitive-command"], stdout="sensitive-output", environment={"TOKEN": "secret"}, pid=123)
    payload["stages"][0]["stdout"] = "stage-secret"
    path.write_text(json.dumps(payload))
    report = json.dumps(fixture.report())
    assert not any(secret in report for secret in ("sensitive-command", "sensitive-output", "stage-secret", '"pid"', '"TOKEN"'))
    def denied(*args):
        raise PermissionError("fixture")
    monkeypatch.setattr(state_module, "_read_json", denied)
    assert fixture.report()["status"] == "unreadable"


def test_report_fifo_is_rejected_without_blocking_or_writing(tmp_path):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    pointer = state / "latest.json"
    os.mkfifo(pointer, 0o600)
    report = load_bootstrap_report(state, tmp_path / "lock", _owner_uid=os.geteuid())
    assert report["status"] == "unavailable"
    assert list(state.iterdir()) == [pointer]


@pytest.mark.parametrize("field,value", [
    ("stages", ["not-a-stage"]), ("stages", None), ("status", "OPERATIONAL"),
    ("options", {"environment": {"TOKEN": "never-show"}}), ("spec", []),
    ("operational", True), ("previous_incomplete", "not-a-predecessor"),
])
def test_corrupt_receipt_is_unavailable_and_cannot_be_acknowledged(fixture, field, value):
    attempt = fixture.begin()
    path = fixture.receipt_path(attempt)
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    report = fixture.report()
    assert report["status"] == "unavailable" and report["operational"] is False
    assert "never-show" not in json.dumps(report)
    assert path.read_bytes() == before
    with pytest.raises(ValidationError):
        fixture.begin(acknowledge=attempt)


@pytest.mark.parametrize("data", [
    b'{"attempt_id":"first","attempt_id":"second"}',
    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}', b'{"value":1e999}', b'{"value":-1e999}',
    b'{"value":' + b'[' * 1200 + b'0' + b']' * 1200 + b'}',
    b'{"value":' + b'[' * 40 + b'0' + b']' * 40 + b'}',
])
def test_strict_json_failures_are_read_only_unavailable(fixture, data):
    fixture.begin()
    pointer = fixture.state.state_root / "latest.json"
    pointer.write_bytes(data)
    assert fixture.report()["status"] == "unavailable"
    assert pointer.read_bytes() == data


def test_record_read_is_bounded_even_if_file_grows_after_stat(fixture, monkeypatch):
    fixture.begin()
    pointer = fixture.state.state_root / "latest.json"
    data = pointer.read_bytes() + b" " * 300
    pointer.write_bytes(data)
    monkeypatch.setattr(state_module, "MAX_RECORD_BYTES", 128)
    real_fstat = os.fstat
    def previously_small(fd):
        values = list(real_fstat(fd))
        values[6] = 1  # A file can grow between fstat and the bounded read.
        return os.stat_result(values)
    monkeypatch.setattr(state_module.os, "fstat", previously_small)
    assert fixture.report()["status"] == "unavailable"
    assert pointer.read_bytes() == data


@pytest.mark.parametrize("code", [True, False, "0", "47", -1, 256, None])
def test_invalid_exit_codes_cannot_create_terminal_evidence(fixture, code):
    attempt = fixture.begin()
    fixture.state.checkpoint(attempt, "system-packages", "running")
    before = fixture.receipt_path(attempt).read_bytes()
    with pytest.raises(ValidationError):
        fixture.state.finish(attempt, code)
    with pytest.raises(ValidationError):
        fixture.state.checkpoint(attempt, "system-packages", "failed", exit_code=code)
    assert fixture.receipt_path(attempt).read_bytes() == before


@pytest.mark.parametrize("defect", ["pending-success", "nonzero-success", "missing-exit", "bool-exit", "overlapping", "missing-stage-exit"])
def test_inconsistent_success_or_execution_cannot_be_reported(fixture, defect):
    attempt = fixture.begin()
    for stage in selected_stages(fixture.options):
        fixture.state.checkpoint(attempt, stage, "running")
        fixture.state.checkpoint(attempt, stage, "success")
    fixture.state.finish(attempt, 0)
    path = fixture.receipt_path(attempt)
    payload = json.loads(path.read_text())
    if defect == "pending-success":
        stage = payload["stages"][0]
        stage["status"] = "pending"
        for key in ("started_at", "finished_at", "exit_code"):
            stage.pop(key)
    elif defect == "nonzero-success":
        payload["exit_code"] = 47
    elif defect == "missing-exit":
        payload.pop("exit_code")
    elif defect == "bool-exit":
        payload["exit_code"] = False
    elif defect == "missing-stage-exit":
        payload["stages"][0].pop("exit_code")
    else:
        payload.update(status="running", finished_at=None, exit_code=None)
        for stage in payload["stages"][:2]:
            stage.update(status="running", finished_at=None, exit_code=None)
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    assert fixture.report()["status"] == "unavailable"
    with pytest.raises(ValidationError):
        fixture.begin(acknowledge=attempt)
    assert path.read_bytes() == before


def test_zero_exit_interruption_and_skipping_failed_gate_are_rejected(fixture):
    attempt = fixture.begin()
    fixture.state.checkpoint(attempt, "system-packages", "running")
    fixture.state.checkpoint(attempt, "system-packages", "failed", exit_code=47)
    with pytest.raises(ValidationError):
        fixture.state.checkpoint(attempt, "tailscale", "running")
    with pytest.raises(ValidationError):
        fixture.state.finish(attempt, 0, interrupted=True)
    fixture.state.finish(attempt, 47)
    assert fixture.report()["status"] == "failed"


def test_premature_zero_exit_normalizes_stage_and_attempt_failure(fixture):
    attempt = fixture.begin()
    fixture.state.checkpoint(attempt, "system-packages", "running")
    with pytest.raises(ReconcileError):
        fixture.state.finish(attempt, 0)
    receipt = fixture.report()["latest"]
    assert receipt["exit_code"] == receipt["stages"][0]["exit_code"] == 2
    assert receipt["status"] == receipt["stages"][0]["status"] == "failed"


def test_zero_exit_interruption_is_rejected_even_after_all_stages_succeed(fixture):
    attempt = fixture.begin()
    for stage in selected_stages(fixture.options):
        fixture.state.checkpoint(attempt, stage, "running")
        fixture.state.checkpoint(attempt, stage, "success")
    before = fixture.receipt_path(attempt).read_bytes()
    with pytest.raises(ValidationError):
        fixture.state.finish(attempt, 0, interrupted=True)
    assert fixture.receipt_path(attempt).read_bytes() == before
    fixture.state.finish(attempt, 143, interrupted=True)
    assert fixture.report()["status"] == "interrupted"


def test_report_rejects_pointer_traversal_and_keeps_external_file(fixture):
    attempt = fixture.begin()
    outside = fixture.state.state_root.parent / "outside.json"
    outside.write_text('{"secret":"never-show"}')
    (fixture.state.state_root / "latest.json").write_text('{"attempt_id":"../../outside"}')
    report = fixture.report()
    assert report["status"] == "unavailable"
    assert "never-show" not in json.dumps(report)
    assert fixture.receipt_path(attempt).is_file()


@pytest.mark.parametrize("ending,code,interrupted", [("exit 47", 47, False), ("kill -TERM $$", 143, True)])
def test_actual_exit_trap_preserves_process_status(tmp_path, ending, code, interrupted):
    source = (ROOT / "bootstrap.sh").read_text()
    trap_source = source.split("finish_bootstrap(){", 1)[1].split("bootstrap_checkpoint system-packages running", 1)[0]
    script = "\n".join([
        "set -Eeuo pipefail", "bootstrap_finished=0", "bootstrap_interrupted=0", "bootstrap_attempt=op-fixture",
        'bootstrap_state(){ printf "%s\\n" "$@" > "$1.log"; }',
        "cleanup_bootstrap_plan(){ return 0; }", "finish_bootstrap(){" + trap_source, ending,
    ])
    result = subprocess.run(["/bin/bash", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == code
    args = (tmp_path / "finish.log").read_text().splitlines()
    assert args[args.index("--exit-code") + 1] == str(code)
    assert ("--interrupted" in args) == interrupted


def test_plan_exits_before_lock_or_durable_receipt_setup():
    source = (ROOT / "bootstrap.sh").read_text()
    assert source.index("PLAN_ONLY: no Host changes applied.") < source.index('bootstrap_lock_path="$(bootstrap_state prepare)"')
    assert source.index("bootstrap_state acquire --fd 9") < source.index("bootstrap_checkpoint system-packages running") < source.index("apt-get update")
    assert source.index("bootstrap_state finish --attempt") < source.index("AGK Station bootstrap complete.")


def test_real_shell_failure_and_yes_cannot_bypass_incomplete_attempt(tmp_path):
    """Run only through a synthetic apt failure; every Host path is unreachable."""
    repo, binaries = tmp_path / "repo", tmp_path / "bin"
    repo.mkdir()
    binaries.mkdir()
    (repo / "scripts").mkdir()
    (repo / "config").mkdir()
    state_root, lock_root = tmp_path / "state", tmp_path / "lock"
    source = (ROOT / "bootstrap.sh").read_text()
    source = source.replace('[[ "${EUID}" -eq 0 || "$PLAN_ONLY" -eq 1 ]]', 'true')
    source = source.replace('/run/station/bootstrap/bootstrap.lock', str(lock_root / "bootstrap.lock"))
    (repo / "bootstrap.sh").write_text(source)
    shutil.copyfile(ROOT / "station.sh", repo / "station.sh")
    (repo / "station.sh").chmod(0o755)
    (repo / "VERSION").write_text(PRODUCT_VERSION)
    (repo / "RELEASE_PROVENANCE.json").write_text('{}')
    (repo / "config/versions.lock").write_text('FIXTURE=1\n')
    (repo / "scripts/station_bootstrap_preflight.py").write_text('print("FIXTURE_PREFLIGHT_OK")\n')
    wrapper = f'''import sys
sys.path.insert(0, {str(ROOT / 'src')!r})
from pathlib import Path
import agentik_station.bootstrap_state as module
original = module.BootstrapState
module.BootstrapState = lambda: original(Path({str(state_root)!r}), Path({str(lock_root)!r}), owner_uid={os.geteuid()})
raise SystemExit(module.main())
'''
    (repo / "scripts/station_bootstrap_state.py").write_text(wrapper)
    station = repo / "station"
    station.write_text(f'''#!{sys.executable}
import os, sys
if sys.argv[1] == 'spec':
    os.execv({str(ROOT / 'station')!r}, [{str(ROOT / 'station')!r}, *sys.argv[1:]])
if sys.argv[1] in ('doctor', 'plan'): raise SystemExit(0)
raise SystemExit(78)
''')
    station.chmod(0o755)
    (binaries / "python3").symlink_to(sys.executable)
    awk = binaries / "awk"
    awk.write_text(f'''#!{sys.executable}
import sys
print('ubuntu' if '$1 == "ID"' in sys.argv[2] else 'noble')
''')
    awk.chmod(0o755)
    uname = binaries / "uname"
    uname.write_text(f'''#!{sys.executable}
import sys
print('Linux' if sys.argv[1] == '-s' else 'x86_64')
''')
    uname.chmod(0o755)
    calls = tmp_path / "mutation-calls"
    for name in ("apt-get", "curl", "install", "useradd", "usermod", "chown", "systemctl", "rsync", "sudo"):
        executable = binaries / name
        executable.write_text(f'''#!{sys.executable}
from pathlib import Path
with Path({str(calls)!r}).open('a') as stream: stream.write({name!r} + '\\n')
raise SystemExit(47)
''')
        executable.chmod(0o755)
    env = dict(os.environ, PATH=f"{binaries}:/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1")
    def run(*extra):
        return subprocess.run(["/bin/bash", str(repo / "bootstrap.sh"), "--yes", *extra],
                              cwd=repo, env=env, capture_output=True, text=True, timeout=30)
    first = run()
    assert first.returncode == 47, first.stdout + first.stderr
    report = load_bootstrap_report(state_root, lock_root, _owner_uid=os.geteuid())
    assert report["status"] == "failed" and report["latest"]["exit_code"] == 47
    assert report["latest"]["stages"][0]["status"] == "failed"
    attempt = report["latest"]["attempt_id"]
    old_receipt = (state_root / "attempts" / f"{attempt}.json").read_bytes()
    assert run().returncode == 2
    assert run("--acknowledge-incomplete", "op-wrong").returncode == 2
    assert calls.read_text().splitlines() == ["apt-get"]
    final = run("--acknowledge-incomplete", attempt)
    assert final.returncode == 47, final.stdout + final.stderr
    assert calls.read_text().splitlines() == ["apt-get", "apt-get"]
    assert (state_root / "attempts" / f"{attempt}.json").read_bytes() == old_receipt
    assert load_bootstrap_report(state_root, lock_root, _owner_uid=os.geteuid())["latest"]["previous_incomplete"]["attempt_id"] == attempt
