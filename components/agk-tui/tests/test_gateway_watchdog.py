from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "gateway_watchdog.py"
SPEC = importlib.util.spec_from_file_location("gateway_watchdog", MODULE_PATH)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


@pytest.mark.parametrize("state", [[], 1, "bad", None,
    {"gateway_state": "running", "pid": 42, "platforms": ["discord"]},
    {"gateway_state": "running", "pid": 42, "platforms": {"discord": ["connected"]}},
])
def test_malformed_profile_state_reports_unhealthy_without_crashing(tmp_path, monkeypatch, state):
    (tmp_path / "gateway_state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(watchdog, "_pid_is_gateway", lambda pid: True)
    profile = watchdog.ProfileBot("synthetic", tmp_path, ("discord",))
    healthy, reason = watchdog.profile_health(profile)
    assert healthy is False
    assert reason


@pytest.mark.parametrize("pid", [float("inf"), float("-inf"), float("nan"), [], {}])
def test_malformed_pid_is_not_a_gateway(pid):
    assert watchdog._pid_is_gateway(pid) is False


@pytest.mark.parametrize("record", [[], ["bad"], "bad", 42,
    {"down_since": "invalid"}, {"down_since": float("nan")},
    {"down_since": float("inf")}, {"down_since": 1e300},
])
def test_malformed_outage_record_restarts_grace_period_without_alert(record):
    sends = []
    result = watchdog.evaluate_profile(
        record, healthy=False, reason="unavailable", now=1000, threshold=600,
        send=lambda: sends.append("alert") or True,
    )
    assert result["down_since"] == 1000
    assert result["alerted"] is False
    assert sends == []


def test_discovery_ignores_profile_symlink_outside_requested_home_root(tmp_path):
    root = tmp_path / "homes"
    operator = root / "operator"
    operator.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.yaml").write_text(
        "platforms:\n  discord:\n    enabled: true\n    extra:\n      offline_alert_enabled: true\n",
        encoding="utf-8",
    )
    (operator / ".hermes").symlink_to(outside, target_is_directory=True)
    assert watchdog.discover_profile_bots(root) == []


@pytest.mark.parametrize("target", [".", "wrong-layout", "other/deep/.hermes"])
def test_discovery_rejects_symlink_to_unrecognized_layout_inside_home_root(tmp_path, target):
    root = tmp_path / "homes"
    operator = root / "operator"
    operator.mkdir(parents=True)
    destination = root / target
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "config.yaml").write_text(
        "platforms:\n  discord:\n    enabled: true\n    extra:\n      offline_alert_enabled: true\n",
        encoding="utf-8",
    )
    (operator / ".hermes").symlink_to(destination, target_is_directory=True)
    assert watchdog.discover_profile_bots(root) == []


def test_outage_alerts_once_after_ten_minutes_and_recovers_silently():
    sends = []

    def send():
        sends.append("alert")
        return True

    record = watchdog.evaluate_profile(
        None,
        healthy=False,
        reason="discord disconnected",
        now=100,
        threshold=600,
        send=send,
    )
    assert record == {
        "down_since": 100,
        "reason": "discord disconnected",
        "alerted": False,
    }
    record = watchdog.evaluate_profile(
        record,
        healthy=False,
        reason="discord disconnected",
        now=699,
        threshold=600,
        send=send,
    )
    assert sends == []
    record = watchdog.evaluate_profile(
        record,
        healthy=False,
        reason="discord disconnected",
        now=700,
        threshold=600,
        send=send,
    )
    assert sends == ["alert"]
    assert record["alerted"] is True
    watchdog.evaluate_profile(
        record,
        healthy=False,
        reason="discord disconnected",
        now=1400,
        threshold=600,
        send=send,
    )
    assert sends == ["alert"]
    assert (
        watchdog.evaluate_profile(
            record,
            healthy=True,
            reason="connected",
            now=1500,
            threshold=600,
            send=send,
        )
        is None
    )
    assert sends == ["alert"]


def test_discovery_includes_main_and_named_profile_bots(tmp_path):
    main = tmp_path / "operator" / ".hermes"
    named = main / "profiles" / "research"
    ignored = tmp_path / "private" / ".hermes"
    for home, config in (
        (
            main,
            "platforms:\n  discord:\n    enabled: true\n    extra:\n      offline_alert_enabled: true\n",
        ),
        (
            named,
            "platforms:\n  telegram:\n    enabled: true\n  discord:\n    extra:\n      offline_alert_enabled: true\n",
        ),
        (ignored, "platforms:\n  discord:\n    enabled: false\n"),
    ):
        home.mkdir(parents=True)
        (home / "config.yaml").write_text(config, encoding="utf-8")

    profiles = watchdog.discover_profile_bots(tmp_path)
    assert [(profile.name, profile.required_platforms) for profile in profiles] == [
        ("operator", ("discord",)),
        ("operator/research", ("telegram",)),
    ]
