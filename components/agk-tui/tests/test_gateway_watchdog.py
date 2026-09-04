from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "gateway_watchdog.py"
SPEC = importlib.util.spec_from_file_location("gateway_watchdog", MODULE_PATH)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


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
