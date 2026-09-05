"""First-bot setup keeps model enrollment, gateway setup and activation distinct."""
import json
from types import SimpleNamespace

from agentik_station import cli
from test_orchestration_cli import gateway


def test_zone_model_setup_is_public_without_an_os_or_project(gateway, capsys):
    assert cli.main(["platform", "configure", "--zone", "example-dev", "--plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == "default"
    assert result["os_id"] is None and result["instance_id"] is None
    assert result["argv"][-4:] == ["--profile", "default", "setup", "model"]
    assert "gateway" not in result["argv"]
    assert result["claim"] == "PREPARED_NOT_RUN"


def test_setup_plan_explains_native_picker_without_running_it(gateway, capsys):
    assert cli.main(["platform", "setup", "--zone", "example-dev",
                     "--platform", "discord", "--plan"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert captured.err == ""
    assert result["argv"][-2:] == ["gateway", "setup"]
    assert result["setup_guidance"]
    assert result["platform_selection"].startswith("operator-intent-only")
    assert result["operational"] is False


def test_setup_briefing_is_visible_before_the_native_wizard(gateway, monkeypatch, capsys):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    observations = []

    def run(argv, **kwargs):
        captured = capsys.readouterr()
        observations.append((argv, kwargs, captured))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main(["platform", "setup", "--zone", "example-dev", "--platform", "discord"]) == 0
    assert len(observations) == 1
    argv, options, briefing = observations[0]
    assert argv[-2:] == ["gateway", "setup"]
    assert options == {"check": False}
    assert "Zone example-dev, profile default" in briefing.err
    assert briefing.out == ""
    result = json.loads(capsys.readouterr().out)
    assert result["operational"] is False
    assert all(item in briefing.err for item in result["setup_guidance"])


def test_provider_configuration_does_not_open_a_gateway_wizard(gateway, monkeypatch, capsys):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda argv, **kwargs:
                        calls.append(argv) or SimpleNamespace(returncode=0))
    assert cli.main(["platform", "configure", "--zone", "example-dev"]) == 0
    assert len(calls) == 1 and calls[0][-2:] == ["setup", "model"]
    result = json.loads(capsys.readouterr().out)
    assert result["operational"] is False
    assert "setup_guidance" not in result
