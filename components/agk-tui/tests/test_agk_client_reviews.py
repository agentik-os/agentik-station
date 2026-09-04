import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "hermes" / "plugins" / "platforms" / "discord" / "agk_client_reviews.py"
)
SPEC = importlib.util.spec_from_file_location("agk_client_reviews", MODULE_PATH)
assert SPEC and SPEC.loader
reviews = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reviews
SPEC.loader.exec_module(reviews)


def test_review_custom_id_is_strictly_client_and_work_scoped():
    assert reviews.is_agk_client_review(
        "agk:review:test-client:WORK-0123456789AB:approve"
    )
    assert not reviews.is_agk_client_review(
        "agk:review:../private:WORK-0123456789AB:approve"
    )
    assert not reviews.is_agk_client_review(
        "agk:review:test-client:WORK-0123456789AB:delete"
    )


def test_gateway_bridge_invokes_only_the_governed_agk_command(monkeypatch):
    captured = {}
    monkeypatch.setattr(reviews.shutil, "which", lambda name: "/usr/local/bin/agk")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "action": "changes",
                    "client_id": "test-client",
                    "work_id": "WORK-0123456789AB",
                    "status": "in_progress",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(reviews.subprocess, "run", fake_run)
    result = reviews.run_agk_review_action(
        "agk:review:test-client:WORK-0123456789AB:changes",
        actor="discord:42",
        decision_id="discord-99",
        feedback="Fix corrupted files.",
    )

    assert result["status"] == "in_progress"
    assert captured["command"] == [
        "/usr/local/bin/agk",
        "client",
        "work",
        "review-action",
        "agk:review:test-client:WORK-0123456789AB:changes",
        "--actor",
        "discord:42",
        "--decision-id",
        "discord-99",
        "--feedback",
        "Fix corrupted files.",
    ]
    assert captured["kwargs"]["timeout"] == 30


def test_discord_adapter_registers_the_review_listener_without_replacing_events():
    source = (
        ROOT / "hermes" / "plugins" / "platforms" / "discord" / "adapter.py"
    ).read_text(encoding="utf-8")

    assert "register_agk_client_review_listener(self._client, adapter_self)" in source
    module_source = MODULE_PATH.read_text(encoding="utf-8")
    assert '@bot.listen("on_interaction")' in module_source
