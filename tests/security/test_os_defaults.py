"""Default teams never infer client scope, adopt instances, or enroll accounts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import os_defaults as defaults, os_lifecycle as lifecycle
from agentik_station.constants import PRODUCT_VERSION
from agentik_station.doctor import _expected_zone_human_path
from agentik_station.errors import SecurityError, ValidationError
from agentik_station.identity import zone_unix_user
from agentik_station.models import InstallSpec, SeedSpec, ZoneSpec
from agentik_station.paths import LayoutPaths


REPO = Path(__file__).resolve().parents[2]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.write_text(json.dumps(value))
    path.chmod(0o600)


@pytest.fixture
def host(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    data = SimpleNamespace(paths=paths, calls=[], failed=None, raise_for=None)
    def configure(role="core", seed=None):
        spec = InstallSpec(role=role, seed=seed, operation_id="op-default-fixture", release_version=PRODUCT_VERSION)
        header = {"schema_version": 1, "host_id": spec.host_id, "role": spec.role,
                  "release_version": spec.release_version, "operation_id": spec.operation_id}
        write(paths.config / "station.json", header)
        write(paths.observed / "host.json", {**header, "state": "READY_FOR_SETUP"})
        write(paths.receipts / f"{spec.operation_id}.json", {"schema_version": 1,
              "operation_id": spec.operation_id, "release_version": spec.release_version,
              "spec": spec.to_dict(), "status": "COMPLETED", "state": "READY_FOR_SETUP"})
        zone_spec = (ZoneSpec("FACTORY", "os", "factory", spec.host_id, "agentik") if seed is None else
                     ZoneSpec(seed.category, seed.name, seed.environment, spec.host_id, seed.organization))
        state = paths.zones_state / zone_spec.zone_id
        human = _expected_zone_human_path(paths, zone_spec)
        user = zone_unix_user(zone_spec.category, zone_spec.name, zone_spec.environment)
        zone = {"schema_version": 2, "id": zone_spec.zone_id, "name": zone_spec.name,
                "category": zone_spec.category, "organization": zone_spec.organization,
                "environment": zone_spec.environment, "host_id": zone_spec.host_id, "unix_user": user,
                "human_root": str(human), "state_root": str(state), "hermes_home": str(state / "hermes"),
                "log_root": str(paths.log / "zones" / zone_spec.zone_id),
                "runtime_root": str(paths.run / "zones" / zone_spec.zone_id),
                "backup_staging_root": str(paths.backups / "zones" / zone_spec.zone_id), "placement": "local",
                "isolation": {"filesystem": "unix-identity", "hermes_home": "dedicated",
                              "credentials": "zone-scoped", "cross_zone_mounts": "deny"}}
        for target in (human / "os", state / "home", state / "hermes", paths.software):
            target.mkdir(mode=0o750, parents=True, exist_ok=True)
        write(paths.config / "zones.d" / f"{zone_spec.zone_id}.json", zone)
        monkeypatch.setattr(lifecycle.pwd, "getpwnam", lambda _name: SimpleNamespace(
            pw_dir=str(state / "home"), pw_uid=os.getuid(), pw_gid=os.getgid()))
        monkeypatch.setattr(lifecycle.grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=os.getgid()))
        data.spec, data.zone = spec, zone
    configure()
    data.configure = configure
    def ledger(instance):
        return defaults.os_instances.instance_paths(paths, data.zone, instance)["ledger"]
    data.ledger = ledger
    def install(source, **kwargs):
        data.calls.append((source, kwargs))
        assert kwargs["zone"] == data.zone
        assert kwargs["allowed_project_ids"] == ()
        assert kwargs["hermes_binary"] == "/fake/hermes" and kwargs["runuser_binary"] == "/fake/runuser"
        instance = kwargs["instance_id"]
        if data.raise_for == instance:
            raise ValidationError("synthetic native failure with private output")
        result = {"instance_id": instance, "os_id": kwargs["os_id"], "os_version": kwargs["os_version"],
                  "organization_id": kwargs["organization_id"],
                  "state": "INSTALLABLE" if data.failed == instance else "CONFIGURED",
                  "expected_profiles": [f"fixture-{instance}-director"],
                  "nano_director": f"fixture-{instance}-director", "hermes_home": str(
                      defaults.os_instances.instance_paths(paths, data.zone, instance)["hermes_home"])}
        write(ledger(instance), result)
        return result
    monkeypatch.setattr(defaults.os_instances, "install_os_instance", install)
    monkeypatch.setattr(defaults.os_instances, "load_os_instance_record", lambda paths, zone, instance_id, require_configured=False:
                        lifecycle._trusted_json(ledger(instance_id), paths, paths.varlib))
    data.plan = lambda: defaults.plan_default_os(REPO, paths)
    data.install = lambda: defaults.install_default_os(REPO, paths, hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    return data


def test_core_plan_selects_only_factory_and_never_writes(host):
    before = {path: path.read_bytes() for path in host.paths.config.rglob("*.json")}
    result = host.plan()
    assert result["ok"] and result["state"] == "PLAN_READY" and not result["mutates"]
    assert [(row["zone_id"], row["instance_id"]) for row in result["instances"]] == [
        ("os", "stepper"), ("os", "builder"), ("os", "librarian")]
    assert all(row["argv"][:4] == ["station", "os", "instance", "install"] for row in result["instances"])
    assert result["organization"] is None and not host.calls
    assert not (host.paths.varlib / "registry").exists()
    assert before == {path: path.read_bytes() for path in host.paths.config.rglob("*.json")}


def test_core_installs_native_teams_without_gateway_auth_or_project_scope(host):
    result = host.install()
    assert result["ok"] and result["state"] == "CONFIGURED"
    assert result["operational"] is False and result["configuration_required"] is True
    assert len(host.calls) == 3
    assert all(kwargs["organization_id"] is None for _, kwargs in host.calls)
    assert list(Path(host.zone["hermes_home"]).iterdir()) == []
    before = {host.ledger(name): host.ledger(name).read_bytes() for name, _ in defaults.DEFAULTS}
    repeated = host.install()["instances"]
    assert all(row["state"] == "PRESERVED" and row["source_version_matches"] is True for row in repeated)
    assert all("next_repair_action" not in row for row in repeated)
    assert len(host.calls) == 3
    assert all(path.read_bytes() == content for path, content in before.items())


def test_team_uses_exact_seed_and_registers_only_matching_organization(host):
    host.configure("team", SeedSpec("ORGANIZATIONS", "acme", "development", "acme", "app"))
    report = host.plan()
    assert report["organization"]["argv"] == ["station", "organization", "register", "--id", "acme", "--zone", "acme-dev"]
    assert not (host.paths.config / "organizations.d").exists()
    result = host.install()
    assert result["ok"] and result["organization"]["state"] == "REGISTERED"
    assert all(kwargs["zone"]["id"] == "acme-dev" and kwargs["organization_id"] == "acme" for _, kwargs in host.calls)
    assert all(row["argv"][-2:] == ["--organization", "acme"] for row in report["instances"])


@pytest.mark.parametrize("role", ["team", "project", "worker", "lab"])
def test_other_host_roles_do_not_guess_client_or_factory_targets(host, role):
    host.configure(role)
    assert host.plan()["state"] == "NOT_APPLICABLE"
    assert host.install()["instances"] == [] and not host.calls


@pytest.mark.parametrize("state", ["CONFIGURED", "INSTALLABLE", "DEGRADED"])
def test_existing_old_version_is_preserved_without_resume_or_reconfiguration(host, state):
    write(host.ledger("builder"), {"os_id": "builder-os", "os_version": "old-reviewed-version",
                                 "organization_id": None, "state": state})
    before = host.ledger("builder").read_bytes()
    result = host.install()
    assert host.ledger("builder").read_bytes() == before
    assert all(kwargs["instance_id"] != "builder" for _, kwargs in host.calls)
    assert result["ok"] is (state == "CONFIGURED")
    assert result["instances"][1]["state"] == "PRESERVED"
    assert result["instances"][1]["source_version_matches"] is False
    if state == "CONFIGURED":
        assert "scoped profile migration" in result["instances"][1]["next_repair_action"]


def test_existing_other_package_blocks_mutation_without_adoption(host):
    write(host.ledger("builder"), {"os_id": "private-os", "os_version": "1.0.0",
                                 "organization_id": None, "state": "CONFIGURED"})
    result = host.install()
    assert not result["ok"] and result["instances"][1]["state"] == "CONFLICT"
    assert not host.calls


def test_stale_configured_ledger_is_not_native_installation_evidence(host, monkeypatch):
    write(host.ledger("builder"), {"os_id": "builder-os", "os_version": "11.12",
                                 "organization_id": None, "state": "CONFIGURED"})
    before = host.ledger("builder").read_bytes()
    original = defaults.os_instances.load_os_instance_record
    reads = []
    def missing_profile(paths, zone, instance_id, require_configured=False):
        reads.append(require_configured)
        if require_configured:
            raise FileNotFoundError("missing native profile config")
        return original(paths, zone, instance_id)
    monkeypatch.setattr(defaults.os_instances, "load_os_instance_record", missing_profile)
    result = host.install()
    assert not result["ok"] and result["state"] == "REVIEW_REQUIRED"
    assert result["instances"][1]["state"] == "PRESERVED"
    assert reads == [False, True] and not host.calls
    assert host.ledger("builder").read_bytes() == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "writable", "fifo"])
def test_hostile_authority_files_are_rejected_before_install(host, kind):
    path = host.paths.config / "station.json"
    if kind in {"symlink", "hardlink", "fifo"}:
        original = path.with_name("saved.json")
        path.rename(original)
        if kind == "symlink":
            path.symlink_to(original)
        elif kind == "hardlink":
            os.link(original, path)
        else:
            os.mkfifo(path)
    else:
        path.chmod(0o666)
    with pytest.raises((SecurityError, OSError)):
        host.install()
    assert not host.calls


@pytest.mark.parametrize("field,value", [("host_id", "foreign"), ("operation_id", "op-other"), ("state", "DEGRADED")])
def test_kernel_authority_mismatch_blocks_all_installation(host, field, value):
    path = host.paths.observed / "host.json"
    payload = json.loads(path.read_text())
    payload[field] = value
    write(path, payload)
    with pytest.raises((ValidationError, SecurityError)):
        host.install()
    assert not host.calls


@pytest.mark.parametrize("field,value", [("organization", "foreign"), ("category", "ORGANIZATIONS"), ("host_id", "foreign-host")])
def test_default_zone_cannot_be_relabelled_as_another_owner(host, field, value):
    path = host.paths.config / "zones.d/os.json"
    zone = json.loads(path.read_text())
    zone[field] = value
    write(path, zone)
    with pytest.raises((ValidationError, SecurityError)):
        host.install()
    assert not host.calls


def test_linked_existing_instance_ledger_is_not_adopted(host):
    ledger = host.ledger("builder")
    other = ledger.with_name("original.json")
    write(other, {"os_id": "builder-os", "os_version": "11.12", "organization_id": None, "state": "CONFIGURED"})
    ledger.symlink_to(other)
    with pytest.raises((SecurityError, OSError)):
        host.install()
    assert ledger.is_symlink() and not host.calls


def test_live_install_rejects_nonroot_before_reading_host_state(monkeypatch):
    monkeypatch.setattr(defaults.os, "geteuid", lambda: 1234)
    with pytest.raises(SecurityError, match="root authority"):
        defaults.install_default_os(REPO, LayoutPaths.live(), hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")


@pytest.mark.parametrize("raises", [False, True])
def test_failed_team_reports_incomplete_and_continues_independent_defaults(host, raises):
    if raises:
        host.raise_for = "builder"
    else:
        host.failed = "builder"
    result = host.install()
    assert result["state"] == "INCOMPLETE" and not result["ok"]
    assert len(host.calls) == 3
    assert result["instances"][2]["state"] == "CONFIGURED"
    assert "private output" not in json.dumps(result)


def test_bootstrap_default_profiles_precede_optional_dependency_failure():
    source = (REPO / "bootstrap.sh").read_text()
    invoke = source.index("/opt/station/current/station os defaults")
    assert source.index("bootstrap_checkpoint kernel-readback success") < invoke
    assert invoke < source.index("/opt/station/current/scripts/station_deps_install.sh --all")
    assert 'if [[ "$INSTALL_HERMES" -eq 1 ]]; then\n  bootstrap_checkpoint os-defaults running' in source
