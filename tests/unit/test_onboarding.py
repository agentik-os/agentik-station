import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import onboarding
from agentik_station.errors import ValidationError
from agentik_station.paths import LayoutPaths

REPO = Path(__file__).resolve().parents[2]


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    path.chmod(0o600)


@pytest.fixture
def layout(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    monkeypatch.setattr(onboarding, "_bootstrap", lambda _: {"status": "not-started", "operational": False})
    monkeypatch.setattr(onboarding.subprocess, "run", lambda *a, **k: pytest.fail("default report must not execute commands"))
    from agentik_station import os_lifecycle
    monkeypatch.setattr(onboarding.pwd, "getpwnam", lambda _: SimpleNamespace(
        pw_dir=str(paths.zones_state / "alpha-dev" / "home"), pw_uid=os.getuid(), pw_gid=os.getgid()))
    monkeypatch.setattr(os_lifecycle.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=os.getgid()))
    return paths


def ready_zone(paths):
    write_json(paths.observed / "host.json", {"schema_version": 1, "host_id": "test-host", "state": "READY_FOR_SETUP"})
    state = paths.zones_state / "alpha-dev"
    human = paths.runtime / "2_ZONES" / "4_ORGANIZATIONS" / "alpha" / "dev"
    zone = {
        "schema_version": 2, "id": "alpha-dev", "name": "alpha", "category": "ORGANIZATIONS",
        "organization": "alpha", "environment": "development", "host_id": "test-host",
        "unix_user": "z-o-alpha-dev", "human_root": str(human), "state_root": str(state),
        "hermes_home": str(state / "hermes"), "log_root": str(paths.log / "zones" / "alpha-dev"),
        "runtime_root": str(paths.run / "zones" / "alpha-dev"),
        "backup_staging_root": str(paths.backups / "zones" / "alpha-dev"), "placement": "local",
        "isolation": {"filesystem": "unix-identity", "hermes_home": "dedicated", "credentials": "zone-scoped", "cross_zone_mounts": "deny"},
    }
    write_json(paths.config / "zones.d" / "alpha-dev.json", zone)
    for path in (state / "home", state / "hermes", state / "projects/workbench"):
        path.mkdir(parents=True, exist_ok=True)
    project = human / "projects" / "workbench"
    write_json(project / "PROJECT.json", {"schema_version": 2, "id": "workbench", "zone_id": "alpha-dev",
               "organization": "alpha", "environment": "development", "human_root": str(project),
               "runtime_state_root": str(state / "projects/workbench"), "repos": [], "credential_references": []})
    return zone


def installed(paths, monkeypatch, *, state="CONFIGURED"):
    zone = ready_zone(paths)
    record = {"schema_version": 2, "zone_id": zone["id"], "project_id": "workbench", "os_id": "builder-os",
              "state": state, "nano_director": "forge", "expected_profiles": ["forge"], "operational": False}
    write_json(paths.varlib / "registry" / "os" / zone["id"] / "builder-os.json", record)
    calls = []

    def load(paths, zone, os_id, *, configured):
        calls.append(configured)
        return record

    monkeypatch.setattr(onboarding, "_os_record", load)
    return zone, record, calls


def gates(report):
    return {gate["id"]: gate for gate in report["gates"]}


def test_fresh_checkout_is_not_an_installed_host_or_os(layout):
    report = onboarding.build_onboarding_report(layout, REPO)
    assert gates(report)["foundation"]["state"] == "NOT_INSTALLED"
    assert gates(report)["os"]["state"] == "SELECTION_REQUIRED"
    assert "builder-os" in report["choices"]["os"]
    assert report["catalog_claim"] == "SOURCE_PACKAGES_ONLY_NOT_INSTALLED_RUNTIME"
    assert report["scope"] == {"zone_id": None, "project_id": None, "os_id": None}
    assert report["next_action"]["argv"] == ["./bootstrap.sh", "--plan"]
    assert not layout.config.exists() and not layout.varlib.exists()


@pytest.mark.parametrize("status", ["failed", "interrupted", "running", "unreadable", "unavailable", "invalid"])
def test_failed_or_incomplete_bootstrap_overrides_stale_host_ready(layout, monkeypatch, status):
    ready_zone(layout)
    monkeypatch.setattr(onboarding, "_bootstrap", lambda _: {"status": status})
    report = onboarding.build_onboarding_report(layout, REPO)
    expected = "BOOTSTRAP_" + status.upper() if status in {"failed", "interrupted", "running"} else "UNKNOWN_BOOTSTRAP_EVIDENCE"
    assert gates(report)["foundation"]["state"] == expected
    assert not gates(report)["foundation"]["satisfied"]


def test_choices_are_not_guessed_defaults(layout):
    ready_zone(layout)
    report = onboarding.build_onboarding_report(layout, REPO)
    assert report["choices"]["zones"] == ["alpha-dev"]
    assert report["scope"]["zone_id"] is None
    assert report["next_action"]["gate"] == "scope"
    assert report["next_action"]["argv"] == []


def test_catalog_and_old_zone_owned_projection_do_not_satisfy_os(layout):
    zone = ready_zone(layout)
    write_json(Path(zone["state_root"]) / "os" / "builder-os.runtime.json", {"state": "CONFIGURED"})
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", project_id="workbench", os_id="builder-os")
    assert gates(report)["scope"]["satisfied"]
    assert gates(report)["os"]["state"] == "NOT_INSTALLED"
    assert report["choices"]["projects"] == ["workbench"]
    assert report["next_action"]["argv"] == ["station", "os", "install", "--id", "builder-os", "--zone", "alpha-dev", "--project", "workbench"]


@pytest.mark.parametrize("state", ["CONFIGURED", "VERIFIED"])
def test_local_os_readback_never_implies_accounts_chat_or_acceptance(layout, monkeypatch, state):
    _, _, calls = installed(layout, monkeypatch, state=state)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os")
    assert calls == [False, True]
    assert gates(report)["os"]["state"] == "LOCAL_" + state
    assert report["scope"]["project_id"] == "workbench"
    assert report["scope"]["director_profile"] == "forge"
    assert report["next_action"]["argv"] == ["station", "os", "setup", "--id", "builder-os", "--zone", "alpha-dev"]
    assert gates(report)["accounts"]["state"] == "UNKNOWN_NOT_AUTHENTICATED"
    assert gates(report)["gateway"]["state"] == "UNKNOWN_NOT_PROBED"
    assert gates(report)["live_acceptance"]["state"] == "PENDING_HUMAN_ACCEPTANCE"
    assert all(not gate["operational"] for gate in report["gates"])
    assert not report["operational"]


def test_partial_install_proposes_resume_not_setup(layout, monkeypatch):
    _, _, calls = installed(layout, monkeypatch, state="INSTALLING")
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os", project_id="workbench")
    assert calls == [False]
    assert gates(report)["os"]["state"] == "INSTALL_INCOMPLETE"
    assert report["next_action"]["argv"][1:3] == ["os", "install"]
    assert gates(report)["accounts"]["next_action"]["argv"] == []


def test_project_mismatch_cannot_route_director(layout, monkeypatch):
    installed(layout, monkeypatch)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os", project_id="other")
    assert gates(report)["os"]["state"] == "INVALID_LOCAL_INSTALL"
    assert "director_profile" not in report["scope"]
    assert gates(report)["project"]["state"] == "OS_PROJECT_CONFLICT"
    assert report["next_action"]["argv"] == []


def test_failed_native_readback_cannot_route_or_probe(layout, monkeypatch):
    installed(layout, monkeypatch)

    def reject(*args, **kwargs):
        raise ValidationError("secret-looking-native-detail")

    monkeypatch.setattr(onboarding, "_os_record", reject)
    monkeypatch.setattr(onboarding, "_probe_gateway", lambda *a: pytest.fail("untrusted OS cannot probe"))
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os", probe=True)
    assert gates(report)["os"]["state"] == "INVALID_LOCAL_INSTALL"
    assert "secret-looking-native-detail" not in json.dumps(report)


@pytest.mark.parametrize("kind", ["leaf_link", "parent_link", "hardlink", "fifo", "writable", "duplicate", "oversize"])
def test_unsafe_host_metadata_is_not_followed_or_trusted(layout, tmp_path, kind):
    path = layout.observed / "host.json"
    write_json(path, {"schema_version": 1, "state": "READY_FOR_SETUP"})
    if kind == "leaf_link":
        outside = tmp_path / "external-secret"
        outside.write_text("DO_NOT_REPORT")
        path.unlink()
        path.symlink_to(outside)
    elif kind == "parent_link":
        moved = layout.varlib / "elsewhere"
        layout.observed.rename(moved)
        layout.observed.symlink_to(moved, target_is_directory=True)
    elif kind == "hardlink":
        os.link(path, tmp_path / "shared")
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif kind == "writable":
        path.chmod(0o666)
    elif kind == "duplicate":
        path.write_text('{"schema_version":1,"state":"DEGRADED","state":"READY_FOR_SETUP"}')
    elif kind == "oversize":
        path.write_text(" " * 65537)
    report = onboarding.build_onboarding_report(layout, REPO)
    assert gates(report)["foundation"]["state"] == "INVALID_EVIDENCE"
    assert "DO_NOT_REPORT" not in json.dumps(report)


def test_unreadable_metadata_is_unknown_not_absent(layout, monkeypatch):
    ready_zone(layout)
    original = onboarding.os.open

    def denied(path, *args, **kwargs):
        if path == "host.json":
            raise PermissionError("private")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(onboarding.os, "open", denied)
    report = onboarding.build_onboarding_report(layout, REPO)
    assert gates(report)["foundation"]["state"] == "UNKNOWN_UNREADABLE"
    assert report["next_action"]["argv"] == ["station", "setup", "--json"]
    assert report["next_action"]["requires_sudo"]
    assert "Do not reinstall" in report["next_action"]["human_action"]


def test_default_report_never_touches_credentials_or_writes(layout, monkeypatch):
    zone, _, _ = installed(layout, monkeypatch)
    secret = Path(zone["hermes_home"]) / "profiles" / "forge" / ".env"
    secret.parent.mkdir(parents=True)
    secret.write_text("SECRET_MUST_NOT_APPEAR=private")
    before = {str(p): p.read_bytes() for p in layout.varlib.rglob("*") if p.is_file()}
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: pytest.fail("read-only report must not mkdir"))
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: pytest.fail("read-only report must not write"))
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os")
    assert "private" not in json.dumps(report)
    assert before == {str(p): p.read_bytes() for p in layout.varlib.rglob("*") if p.is_file()}


@pytest.mark.parametrize("kwargs", [{"zone_id": "../other"}, {"os_id": "--profile"}, {"project_id": "workbench"}])
def test_invalid_scope_fails_before_any_metadata_read(layout, monkeypatch, kwargs):
    monkeypatch.setattr(onboarding, "_bootstrap", lambda *a: pytest.fail("invalid scope read metadata"))
    with pytest.raises(ValidationError):
        onboarding.build_onboarding_report(layout, REPO, **kwargs)


def test_probe_is_one_bounded_systemctl_query_without_hermes_or_output_leaks(layout, monkeypatch):
    zone, _, _ = installed(layout, monkeypatch)
    calls = []
    monkeypatch.setattr(onboarding.os, "geteuid", lambda: 0)
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda p: True if str(p) == "/run/systemd/system" else original_is_dir(p))
    monkeypatch.setattr(onboarding, "_project_state", lambda *a: "LOCAL_PROJECT")
    monkeypatch.setattr(onboarding.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=12001))

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="LoadState=loaded\nActiveState=active\nSecret=DO_NOT_REPORT\n")

    monkeypatch.setattr(onboarding.subprocess, "run", run)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os", probe=True)
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:4] == ["/usr/sbin/runuser", "--user", zone["unix_user"], "--"]
    assert argv[4:6] == ["/usr/bin/env", "-i"]
    assert "HERMES_HOME=" + zone["hermes_home"] in argv
    assert "/usr/local/bin/hermes" not in argv
    assert argv[-7:] == ["/usr/bin/systemctl", "--user", "--no-pager", "show", "hermes-gateway-forge.service", "--property=LoadState", "--property=ActiveState"]
    assert kwargs["timeout"] == 10 and kwargs["stdin"] == onboarding.subprocess.DEVNULL
    assert report["gateway_observation"]["state"] == "OBSERVED_ACTIVE"
    assert not gates(report)["live_acceptance"]["satisfied"]
    assert "DO_NOT_REPORT" not in json.dumps(report)


def test_probe_permission_failure_is_unknown_without_commands(layout, monkeypatch):
    installed(layout, monkeypatch)
    monkeypatch.setattr(onboarding.os, "geteuid", lambda: 1000)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os", probe=True)
    assert report["gateway_observation"]["reason"] == "ROOT_REQUIRED_FOR_ZONE_IDENTITY"
    assert report["gateway_observation"]["state"] == "UNKNOWN"


def test_human_output_preserves_next_action_and_lower_truth(layout):
    report = onboarding.build_onboarding_report(layout, REPO)
    text = onboarding.render_onboarding_report(report)
    assert "not live acceptance" in text
    assert "./bootstrap.sh --plan" in text
    assert "not installed runtimes" in text


def test_catalog_uses_canonical_case_sensitive_filename(layout, monkeypatch):
    from agentik_station import maturity

    original = maturity.load_os_catalog

    def check(path):
        assert path.name == "CATALOG.json"
        return original(path)

    monkeypatch.setattr(maturity, "load_os_catalog", check)
    report = onboarding.build_onboarding_report(layout, REPO)
    assert "builder-os" in report["choices"]["os"]


def test_missing_project_suggests_only_project_plan_before_os_install(layout):
    ready_zone(layout)
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", project_id="new-project", os_id="builder-os")
    assert gates(report)["project"]["state"] == "NOT_CREATED"
    assert report["next_action"]["argv"] == ["station", "project", "create", "--zone", "alpha-dev", "--id", "new-project", "--plan"]
    assert gates(report)["os"]["next_action"]["argv"] == []
    assert not report["next_action"]["mutates"]


@pytest.mark.parametrize("where", ["human", "runtime"])
def test_partial_project_never_suggests_overwrite_or_os_install(layout, where):
    zone = ready_zone(layout)
    root = Path(zone["human_root"] if where == "human" else zone["state_root"])
    (root / "projects/partial").mkdir()
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", project_id="partial", os_id="builder-os")
    assert gates(report)["project"]["state"] == "PARTIAL_PROJECT"
    assert report["next_action"]["argv"] == ["station", "doctor", "--full", "--json"]
    assert gates(report)["os"]["next_action"]["argv"] == []


def test_tampered_project_descriptor_blocks_os_install(layout):
    zone = ready_zone(layout)
    path = Path(zone["human_root"]) / "projects/workbench/PROJECT.json"
    payload = json.loads(path.read_text())
    payload["zone_id"] = "another"
    path.write_text(json.dumps(payload))
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", project_id="workbench", os_id="builder-os")
    assert gates(report)["project"]["state"] == "INVALID_PROJECT"
    assert gates(report)["os"]["next_action"]["argv"] == []


def test_complete_degraded_os_exposes_provider_repair_without_reinstall(layout, monkeypatch):
    _, _, calls = installed(layout, monkeypatch, state="DEGRADED")
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os")
    assert calls == [False, True]
    assert gates(report)["os"]["state"] == "LOCAL_DEGRADED"
    assert not gates(report)["os"]["satisfied"]
    assert report["next_action"]["argv"][1:3] == ["os", "setup"]
    assert "station platform setup" in onboarding.render_onboarding_report(report)
    assert "station os verify" in onboarding.render_onboarding_report(report)


def test_human_report_exposes_chat_sequence_despite_unobserved_accounts(layout, monkeypatch):
    installed(layout, monkeypatch, state="VERIFIED")
    report = onboarding.build_onboarding_report(layout, REPO, zone_id="alpha-dev", os_id="builder-os")
    text = onboarding.render_onboarding_report(report)
    assert "station os setup" in text and "station platform setup" in text
    assert "UNKNOWN_NOT_AUTHENTICATED" in text


def test_bootstrap_adapter_uses_fixture_owner_and_remains_read_only(layout, monkeypatch):
    from agentik_station import bootstrap_state

    monkeypatch.undo()
    calls = []
    original = bootstrap_state.load_bootstrap_report

    def load(state, lock, **kwargs):
        calls.append(kwargs)
        return original(state, lock, **kwargs)

    monkeypatch.setattr(bootstrap_state, "load_bootstrap_report", load)
    assert onboarding._bootstrap(layout)["status"] == "not-started"
    assert calls == [{"_owner_uid": os.getuid()}]
    assert not layout.varlib.exists() and not layout.run.exists()
