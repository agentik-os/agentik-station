"""Instance routing remains explicit, read-only and below live acceptance."""
import json

import pytest

from agentik_station import onboarding
from agentik_station.cli import build_parser
from agentik_station.errors import ValidationError
from test_onboarding import REPO, gates, layout, ready_zone, write_json


def instance(paths, monkeypatch, *, state="CONFIGURED", projects=()):
    zone = ready_zone(paths)
    record = {
        "schema_version": 3, "zone_id": zone["id"], "instance_id": "engineering",
        "organization_id": "alpha", "os_id": "devops-os", "os_version": "1.0.0",
        "state": state, "nano_director": "i-1234567890-atlas",
        "expected_profiles": ["i-1234567890-atlas", "i-1234567890-forge"],
        "role_profile_map": {"atlas": "i-1234567890-atlas", "forge": "i-1234567890-forge"},
        "allowed_project_ids": list(projects), "operational": False,
        "workspace_root": zone["human_root"] + "/os/instances/engineering/workspace",
        "hermes_home": zone["state_root"] + "/os-instances/engineering/hermes",
    }
    write_json(paths.varlib / "registry/os-instances/alpha-dev/engineering.json", record)
    monkeypatch.setattr(onboarding, "_instance_record", lambda *a, **k: record)
    from agentik_station import organizations
    organization = {"schema_version": 1, "id": "alpha", "zone_ids": ["alpha-dev"]}
    monkeypatch.setattr(organizations, "load_organization", lambda *a, **k: organization)
    monkeypatch.setattr(organizations, "validate_organization_zone", lambda *a, **k: organization)
    return zone, record


def test_instance_owns_workspace_without_project_gate(layout, monkeypatch):
    _, record = instance(layout, monkeypatch)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering")
    assert gates(report)["project"]["state"] == "NOT_REQUIRED"
    assert gates(report)["project"]["satisfied"]
    assert gates(report)["os"]["satisfied"]
    assert report["scope"]["project_id"] is None
    assert report["scope"]["organization_id"] == "alpha"
    assert report["scope"]["role_profile_map"] == record["role_profile_map"]
    assert report["next_action"]["argv"] == ["station", "os", "instance", "setup", "--zone", "alpha-dev", "--instance", "engineering"]
    assert "mapped native profile" in report["next_action"]["human_action"]
    assert "transient delegate_task child does not select" in report["next_action"]["human_action"]
    assert not report["operational"]
    assert "station platform setup --zone alpha-dev --instance engineering" in onboarding.render_onboarding_report(report)


def test_declared_project_remains_optional_execution_target(layout, monkeypatch):
    instance(layout, monkeypatch, projects=["workbench"])
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering", project_id="workbench")
    assert gates(report)["project"]["state"] == "LOCAL_PROJECT"
    assert gates(report)["os"]["satisfied"]


def test_project_outside_instance_scope_cannot_route_or_probe(layout, monkeypatch):
    instance(layout, monkeypatch)
    monkeypatch.setattr(onboarding, "_probe_gateway", lambda *a, **k: pytest.fail("out-of-scope probe"))
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering", project_id="workbench", probe=True)
    assert gates(report)["project"]["state"] == "PROJECT_SCOPE_CONFLICT"
    assert "director_profile" not in report["scope"]
    assert gates(report)["accounts"]["next_action"]["argv"] == []


def test_wrong_client_cannot_route_team(layout, monkeypatch):
    instance(layout, monkeypatch)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering", organization_id="other")
    assert gates(report)["os"]["state"] == "INVALID_LOCAL_INSTALL"
    assert "director_profile" not in report["scope"]
    assert not gates(report)["os"]["satisfied"]


def test_partial_instance_resume_preserves_exact_owner_and_project_scope(layout, monkeypatch):
    instance(layout, monkeypatch, state="INSTALLABLE", projects=["workbench"])
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering")
    assert report["next_action"]["argv"] == ["station", "os", "instance", "install", "--zone", "alpha-dev", "--instance", "engineering", "--id", "devops-os", "--organization", "alpha", "--allow-project", "workbench"]
    assert gates(report)["accounts"]["next_action"]["argv"] == []


def test_instance_probe_receives_qualified_director_and_instance(layout, monkeypatch):
    _, record = instance(layout, monkeypatch)
    calls = []
    def probe(zone, director, *, instance_id):
        calls.append((zone["id"], director, instance_id))
        return {"state": "OBSERVED_ACTIVE"}
    monkeypatch.setattr(onboarding, "_probe_gateway", probe)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering", probe=True)
    assert calls == [("alpha-dev", record["nano_director"], "engineering")]
    assert not gates(report)["live_acceptance"]["satisfied"]


def test_unreadable_instance_never_suggests_reinstall(layout, monkeypatch):
    instance(layout, monkeypatch)
    def denied(*a, **k):
        raise PermissionError("private")
    monkeypatch.setattr(onboarding, "_instance_record", denied)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", instance_id="engineering", organization_id="alpha")
    assert gates(report)["os"]["state"] == "UNKNOWN_UNREADABLE"
    assert gates(report)["os"]["next_action"]["argv"] == []
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize("kwargs", [
    {"instance_id": "engineering"},
    {"zone_id": "alpha-dev", "instance_id": "engineering", "os_id": "devops-os"},
    {"zone_id": "alpha-dev", "organization_id": "../alpha"},
])
def test_invalid_instance_selector_fails_before_metadata(layout, monkeypatch, kwargs):
    monkeypatch.setattr(onboarding, "_bootstrap", lambda *a: pytest.fail("unexpected metadata read"))
    with pytest.raises(ValidationError):
        onboarding.build_onboarding_report(layout, REPO, **kwargs)


def test_cli_instance_install_has_no_required_project():
    args = build_parser().parse_args(["os", "instance", "install", "--zone", "alpha-dev", "--instance", "engineering", "--id", "devops-os", "--organization", "alpha"])
    assert args.allow_project == [] and args.instance_command == "install"


@pytest.mark.parametrize("argv", [
    ["setup", "--zone", "alpha-dev", "--instance", "engineering", "--os", "devops-os"],
    ["platform", "setup", "--zone", "alpha-dev", "--instance", "engineering", "--os", "devops-os"],
])
def test_cli_rejects_ambiguous_legacy_and_instance_selectors(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_organization_cli_keeps_explicit_repeated_zone_bindings():
    args = build_parser().parse_args(["organization", "register", "--id", "alpha", "--zone", "alpha-dev", "--zone", "alpha-prod", "--plan"])
    assert args.zone == ["alpha-dev", "alpha-prod"] and args.plan
