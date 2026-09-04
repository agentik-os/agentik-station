import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "agk_composio_inventory", ROOT / "scripts/composio_inventory.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_sanitize_keeps_only_toolkit_status_and_connection_count():
    result = MODULE.sanitize({
        "github": [{"status": "ACTIVE", "word_id": "secret-id", "alias": "work"}],
        "youtube": [{"status": "EXPIRED", "word_id": "other-secret"}],
    })
    assert result == [
        {"name": "github", "status": "active", "connections": 1},
        {"name": "youtube", "status": "expired", "connections": 1},
    ]
    assert "secret" not in repr(result)
    assert "work" not in repr(result)


def test_refresh_writes_a_private_redacted_profile_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USER", "operator")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key"}', encoding="utf-8")
    payload = {
        "discord": [{"status": "ACTIVE", "word_id": "never-cache-this"}],
    }
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr=""
        ),
    )

    document = MODULE.refresh()

    assert document["authenticated"] is True
    assert document["toolkits"] == [
        {"name": "discord", "status": "active", "connections": 1}
    ]
    cache = tmp_path / ".agentik/composio-connections.json"
    assert cache.stat().st_mode & 0o777 == 0o600
    assert "never-cache-this" not in cache.read_text(encoding="utf-8")


def test_refresh_marks_placeholder_auth_as_setup_required(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USER", "mission")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":null}', encoding="utf-8")

    document = MODULE.refresh()

    assert document["authenticated"] is False
    assert document["toolkits"] == []


def test_refresh_reports_cli_failure_without_leaking_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key"}', encoding="utf-8")
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=7, stdout="", stderr="Bearer never-expose-this"
        ),
    )

    try:
        MODULE.refresh()
    except RuntimeError as error:
        assert str(error) == "Composio connections list failed with exit code 7"
        assert "never-expose-this" not in str(error)
    else:
        raise AssertionError("a failed Composio refresh was accepted")


def test_refresh_reports_missing_cli_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key"}', encoding="utf-8")

    def missing_cli(*args, **kwargs):
        raise FileNotFoundError("composio")

    monkeypatch.setattr(MODULE.subprocess, "run", missing_cli)

    try:
        MODULE.refresh()
    except RuntimeError as error:
        assert str(error) == "Composio CLI is unavailable in this profile"
    else:
        raise AssertionError("a missing Composio CLI was accepted")
