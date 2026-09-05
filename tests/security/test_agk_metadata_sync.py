"""Protected metadata crosses into AGK only as a validated, redacted projection."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sync():
    spec = importlib.util.spec_from_file_location("station_agk_sync_test", ROOT / "scripts/station_agk_sync.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sources(sync, tmp_path, monkeypatch):
    directory = tmp_path / "protected"
    directory.mkdir(mode=0o700)
    data = {
        sync.TOOLS: {
            "station_user": "agk-station", "mode": "full", "repository": sync.REPOSITORY,
            "hermes": "Hermes v2026.8.31", "codex": "codex-cli 0.153.2",
            "agk_tui": "a" * 40, "claude": "", "OPENAI_API_KEY": "SECRET_SENTINEL",
        },
        sync.HOST: {
            "schema_version": 1, "host_id": "moonbase-station", "role": "core",
            "state": "READY_FOR_SETUP", "release_version": "11.14", "zones": ["private", "agentik"],
            "failure": {"message": "SECRET_SENTINEL"}, "modules": [{"token": "SECRET_SENTINEL"}],
        },
        sync.DOCTOR: {
            "schema_version": 1, "scope": "station-full", "checked_at": "2026-09-05T16:00:00+00:00",
            "ok": True, "checks": [{"name": "fhs:state", "detail": "SECRET_SENTINEL"}],
            "issues": [], "warnings": [{"message": "SECRET_SENTINEL"}],
            "environment": {"API_KEY": "SECRET_SENTINEL"},
        },
    }
    files = {}
    for index, (source, payload) in enumerate(data.items()):
        destination = directory / f"{index}.json"
        destination.write_text(json.dumps(payload))
        destination.chmod(0o600)
        files[source] = destination
    reader = sync.read_runtime_json
    calls = []

    def read_fixture(path, **kwargs):
        calls.append(path)
        assert kwargs == {"uid": 0, "immutable": True, "limit": 1024 * 1024}
        return reader(files[path], uid=os.getuid(), immutable=True, trusted_root=directory,
                      limit=kwargs["limit"])

    monkeypatch.setattr(sync, "read_runtime_json", read_fixture)
    return SimpleNamespace(files=files, data=data, directory=directory, calls=calls)


@pytest.fixture
def operator(sync, tmp_path, monkeypatch):
    home = tmp_path / "operator"
    home.mkdir(mode=0o700)
    monkeypatch.setattr(sync.os, "geteuid", lambda: max(1, os.getuid()))
    monkeypatch.setattr(sync.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="agk-station", pw_dir=str(home)))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(sync.shutil, "which", lambda name: None)
    return home


def test_export_selects_actual_host_doctor_paths_and_omits_raw_secrets(sync, sources):
    projection = sync.export_projection()
    assert sources.calls == [sync.TOOLS, sync.HOST, sync.DOCTOR]
    assert projection["mode"] == "full"
    assert projection["repository"] == sync.REPOSITORY
    assert projection["tools"]["codex"] == "codex-cli 0.153.2"
    assert set(projection["receipts"]) == {
        "/var/lib/station/observed/host.json", "/var/lib/station/doctor/latest.json"}
    assert projection["receipts"][str(sync.HOST)]["zones"] == ["private", "agentik"]
    assert projection["receipts"][str(sync.DOCTOR)] == {
        "schema_version": 1, "scope": "station-full", "checked_at": "2026-09-05T16:00:00+00:00",
        "ok": True, "checks": 1, "issues": 0, "warnings": 1,
    }
    assert "SECRET_SENTINEL" not in json.dumps(projection)


@pytest.mark.parametrize("source_name", ["TOOLS", "HOST", "DOCTOR"])
def test_missing_required_metadata_cannot_be_a_success(sync, sources, monkeypatch, capsys, source_name):
    sources.files[getattr(sync, source_name)].unlink()
    monkeypatch.setattr(sync.os, "geteuid", lambda: 0)
    assert sync.main(["--export"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "No successful sync" in output.err


@pytest.mark.parametrize("content", ["SECRET_SENTINEL{", "[]", '{"mode":"full","mode":"team"}', '{"x":NaN}'])
def test_invalid_source_data_fails_without_echoing_contents(sync, sources, monkeypatch, capsys, content):
    sources.files[sync.TOOLS].write_text(content)
    monkeypatch.setattr(sync.os, "geteuid", lambda: 0)
    assert sync.main(["--export"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "SECRET_SENTINEL" not in output.err


def test_permission_failure_is_not_swallowed(sync, sources, monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise PermissionError("SECRET_SENTINEL")
    monkeypatch.setattr(sync, "read_runtime_json", denied)
    monkeypatch.setattr(sync.os, "geteuid", lambda: 0)
    assert sync.main(["--export"]) == 1
    output = capsys.readouterr()
    assert not output.out and "SECRET_SENTINEL" not in output.err


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "writable"])
def test_unsafe_metadata_is_rejected(sync, sources, unsafe):
    path = sources.files[sync.TOOLS]
    if unsafe == "symlink":
        original = path.with_suffix(".original")
        path.rename(original)
        path.symlink_to(original)
    elif unsafe == "hardlink":
        os.link(path, path.with_suffix(".link"))
    else:
        path.chmod(0o666)
    with pytest.raises(sync.SyncError, match="invalid"):
        sync.export_projection()


@pytest.mark.parametrize("target,key,value", [
    ("TOOLS", "repository", "/root/other"), ("TOOLS", "station_user", "root"),
    ("HOST", "zones", "private"), ("HOST", "state", "invented"),
    ("HOST", "role", "team"), ("HOST", "schema_version", True),
    ("DOCTOR", "ok", False), ("DOCTOR", "checks", "not-a-list"),
])
def test_incoherent_source_metadata_is_rejected(sync, sources, target, key, value):
    source = getattr(sync, target)
    payload = copy.deepcopy(sources.data[source])
    payload[key] = value
    sources.files[source].write_text(json.dumps(payload))
    with pytest.raises(sync.SyncError):
        sync.export_projection()


def test_operator_writes_complete_private_snapshot_without_reading_system_metadata(sync, sources, operator, monkeypatch):
    projection = sync.export_projection()
    monkeypatch.setattr(sync, "_read_metadata", lambda _: pytest.fail("Operator tried to reread protected metadata"))
    out = sync.write_snapshot(projection)
    stored = json.loads(out.read_text())
    assert stored["tools"] == projection["tools"]
    assert stored["receipts"] == projection["receipts"]
    assert stored["repository"] == sync.REPOSITORY
    assert stored["mode"] == "full"
    assert "SECRET_SENTINEL" not in out.read_text()
    assert out.stat().st_mode & 0o777 == 0o600
    assert out.parent.stat().st_mode & 0o777 == 0o700
    assert out.stat().st_uid == os.getuid()


@pytest.mark.parametrize("payload", [b"", b"SECRET_SENTINEL{", b'{"schema_version":1,"schema_version":1}',
                                     b"x" * 65537, b"[" * 2000 + b"]" * 2000])
def test_failed_import_preserves_prior_snapshot(sync, operator, monkeypatch, capsys, payload):
    state = operator / ".agentik"
    state.mkdir(mode=0o700)
    output = state / "station-sync.json"
    output.write_text("previous snapshot")
    monkeypatch.setattr(sync.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload)))
    assert sync.main(["--from-stdin"]) == 1
    assert output.read_text() == "previous snapshot"
    result = capsys.readouterr()
    assert not result.out and "SECRET_SENTINEL" not in result.err


def test_import_rejects_unexpected_nested_material(sync, sources, operator, monkeypatch):
    projection = sync.export_projection()
    projection["receipts"][str(sync.DOCTOR)]["raw_environment"] = {"API_KEY": "SECRET_SENTINEL"}
    monkeypatch.setattr(sync.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(projection).encode())))
    assert sync.main(["--from-stdin"]) == 1
    assert not (operator / ".agentik").exists()


def test_root_cannot_write_into_operator_home(sync, sources, operator, monkeypatch):
    projection = sync.export_projection()
    monkeypatch.setattr(sync.os, "geteuid", lambda: 0)
    with pytest.raises(sync.SyncError, match="unprivileged"):
        sync.write_snapshot(projection)
    assert not (operator / ".agentik").exists()


@pytest.mark.parametrize("attack", ["wrong-home", "wrong-user", "directory-link", "snapshot-link"])
def test_writer_rejects_identity_and_symlink_redirection(sync, sources, operator, monkeypatch, tmp_path, attack):
    projection = sync.export_projection()
    victim = tmp_path / "victim"
    victim.mkdir()
    target = victim / "target.json"
    target.write_text("untouched")
    if attack == "wrong-home":
        monkeypatch.setenv("HOME", str(victim))
    elif attack == "wrong-user":
        monkeypatch.setattr(sync.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="another-user", pw_dir=str(operator)))
    elif attack == "directory-link":
        (operator / ".agentik").symlink_to(victim, target_is_directory=True)
    else:
        (operator / ".agentik").mkdir()
        (operator / ".agentik/station-sync.json").symlink_to(target)
    with pytest.raises((sync.SyncError, sync.StationError, OSError)):
        sync.write_snapshot(projection)
    assert target.read_text() == "untouched"


@pytest.mark.parametrize("export_rc,writer_rc,expected", [(0, 0, "success"), (23, 0, "failed"), (0, 17, "failed")])
def test_bootstrap_pipeline_records_either_process_failure(tmp_path, export_rc, writer_rc, expected):
    script = (ROOT / "bootstrap.sh").read_text()
    block = script.split("bootstrap_checkpoint agk-metadata-sync running", 1)[1].split("bootstrap_state finish", 1)[0]
    block = "bootstrap_checkpoint agk-metadata-sync running" + block
    fixture = tmp_path / "bin"
    fixture.mkdir()
    python = fixture / "python3"
    python.write_text(f"#!{sys.executable}\nimport os,sys\n"
                      "if '--export' in sys.argv:\n print('{}')\n sys.exit(int(os.environ['EXPORT_RC']))\n"
                      "assert '--from-stdin' in sys.argv\nsys.stdin.read()\nsys.exit(int(os.environ['WRITER_RC']))\n")
    python.chmod(0o755)
    sudo = fixture / "sudo"
    sudo.write_text(f"#!{sys.executable}\nimport os,sys\n"
                    "assert sys.argv[1:4] == ['-u', 'agk-station', '-H']\nos.execvp(sys.argv[4], sys.argv[4:])\n")
    sudo.chmod(0o755)
    wrapper = 'set -euo pipefail\nbootstrap_checkpoint() { printf "%s %s\\n" "$1" "$2"; }\n' + block
    result = subprocess.run(["/bin/bash", "-c", wrapper], text=True, capture_output=True,
                            env=dict(os.environ, PATH=f"{fixture}:/usr/bin:/bin", STATION_USER="agk-station",
                                     STATION_HOME=str(tmp_path), REPO_DIR=str(ROOT), EXPORT_RC=str(export_rc), WRITER_RC=str(writer_rc)),
                            timeout=10)
    assert result.returncode == 0, result.stderr
    assert f"agk-metadata-sync {expected}" in result.stdout
    if expected == "failed":
        assert "agk-metadata-sync success" not in result.stdout
