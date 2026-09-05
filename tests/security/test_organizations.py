"""Organization identity tests use only synthetic temporary-root metadata."""
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from agentik_station import organizations
from agentik_station.doctor import _expected_zone_human_path
from agentik_station.errors import SecurityError, ValidationError
from agentik_station.identity import zone_unix_user
from agentik_station.models import ZoneSpec
from agentik_station.paths import LayoutPaths


def write_zone(paths, *, name="acme", environment="development", organization="acme", category="ORGANIZATIONS", host="host-one"):
    spec = ZoneSpec(category, name, environment, host, organization)
    state = paths.zones_state / spec.zone_id
    value = {"schema_version": 2, "id": spec.zone_id, "name": spec.name,
             "category": spec.category, "organization": spec.organization,
             "environment": spec.environment, "host_id": spec.host_id,
             "unix_user": zone_unix_user(spec.category, spec.name, spec.environment),
             "human_root": str(_expected_zone_human_path(paths, spec)), "state_root": str(state),
             "hermes_home": str(state / "hermes"), "log_root": str(paths.log / "zones" / spec.zone_id),
             "runtime_root": str(paths.run / "zones" / spec.zone_id),
             "backup_staging_root": str(paths.backups / "zones" / spec.zone_id), "placement": "local",
             "isolation": {"filesystem": "unix-identity", "hermes_home": "dedicated",
                           "credentials": "zone-scoped", "cross_zone_mounts": "deny"}}
    path = paths.config / "zones.d" / f"{spec.zone_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.write_text(json.dumps(value))
    path.chmod(0o640)
    return value, path


@pytest.fixture
def registry(tmp_path):
    paths = LayoutPaths.under(tmp_path.resolve() / "host")
    zone, path = write_zone(paths)
    (paths.config / "station.json").write_text(json.dumps({"schema_version": 1, "host_id": "host-one"}))
    return paths, zone, path


def snapshot(root):
    return {str(p.relative_to(root)): (p.lstat().st_ino, p.lstat().st_mtime_ns, p.lstat().st_mode,
                                      p.read_bytes() if p.is_file() and not p.is_symlink() else None)
            for p in root.rglob("*")}


def test_registration_plan_is_read_only_and_explicit(registry):
    paths, zone, _ = registry
    before = snapshot(paths.config.parent)
    value = organizations.register_organization(paths, organization_id="acme", zone_ids=[zone["id"]], plan=True)
    assert value["kind"] == "OrganizationRegistrationPlan"
    assert value["mutates"] is False and value["operational"] is False
    assert value["organization"] == {"schema_version": 1, "id": "acme", "zone_ids": ["acme-dev"]}
    assert snapshot(paths.config.parent) == before
    assert not paths.run.exists()


def test_registration_exact_schema_private_and_idempotent(registry):
    paths, zone, _ = registry
    expected = {"schema_version": 1, "id": "acme", "zone_ids": ["acme-dev"]}
    assert organizations.register_organization(paths, organization_id="acme", zone_ids=[zone["id"]]) == expected
    path = paths.config / "organizations.d/acme.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_uid == os.getuid()
    before = (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes())
    assert organizations.register_organization(paths, organization_id="acme", zone_ids=[zone["id"]]) == expected
    assert (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes()) == before
    assert organizations.load_organization(paths, organization_id="acme") == expected
    assert organizations.validate_organization_zone(paths, organization_id="acme", zone=zone) == expected


def test_multiple_environment_bindings_are_sorted_and_no_cross_project_scope(registry):
    paths, _, _ = registry
    write_zone(paths, environment="production")
    value = organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-prod", "acme-dev"])
    assert value["zone_ids"] == ["acme-dev", "acme-prod"]
    assert set(value) == {"schema_version", "id", "zone_ids"}


@pytest.mark.parametrize("field,value", [
    ("organization", None), ("organization", "other"), ("name", "other"),
    ("category", "PROJECTS"), ("host_id", "host-two"),
    ("human_root", "/tmp/untrusted-client"), ("hermes_home", "/tmp/untrusted-hermes"),
])
def test_registration_rejects_mismatched_client_identity_without_relabel(registry, field, value):
    paths, zone, path = registry
    zone[field] = value
    path.write_text(json.dumps(zone))
    before = snapshot(paths.config)
    with pytest.raises((ValidationError, SecurityError)):
        organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"])
    assert snapshot(paths.config) == before
    assert not paths.run.exists()


@pytest.mark.parametrize("zone_ids", [[], ["acme-dev", "acme-dev"], ["missing"], ["../other"], "acme-dev"])
def test_registration_rejects_missing_duplicate_invalid_bindings(registry, zone_ids):
    paths, _, _ = registry
    with pytest.raises((ValidationError, FileNotFoundError)):
        organizations.register_organization(paths, organization_id="acme", zone_ids=zone_ids)
    assert not (paths.config / "organizations.d").exists()


def test_existing_binding_cannot_be_silently_extended(registry):
    paths, _, _ = registry
    organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"])
    write_zone(paths, environment="production")
    with pytest.raises(ValidationError, match="migration"):
        organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev", "acme-prod"])
    assert organizations.load_organization(paths, organization_id="acme")["zone_ids"] == ["acme-dev"]


def test_other_organization_claim_is_rejected(registry):
    paths, _, _ = registry
    root = paths.config / "organizations.d"
    root.mkdir(mode=0o700)
    (root / "other.json").write_text(json.dumps({"schema_version": 1, "id": "other", "zone_ids": ["acme-dev"]}))
    with pytest.raises(ValidationError, match="another Organization"):
        organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"])


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "fifo", "writable", "duplicate-keys"])
def test_untrusted_zone_record_fails_closed(registry, tmp_path, unsafe):
    paths, _, path = registry
    if unsafe == "symlink":
        target = tmp_path / "external.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    elif unsafe == "hardlink":
        os.link(path, tmp_path / "alias.json")
    elif unsafe == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif unsafe == "writable":
        path.chmod(0o666)
    else:
        path.write_text('{"schema_version":2,"schema_version":2}')
    with pytest.raises((SecurityError, ValidationError, OSError)):
        organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"], plan=True)
    assert not (paths.config / "organizations.d").exists()


def test_validate_rejects_supplied_record_drift_and_unenrolled_zone(registry):
    paths, zone, _ = registry
    organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"])
    with pytest.raises(SecurityError):
        organizations.validate_organization_zone(paths, organization_id="acme", zone={**zone, "organization": "other"})
    prod, _ = write_zone(paths, environment="production")
    with pytest.raises(ValidationError, match="not explicitly enrolled"):
        organizations.validate_organization_zone(paths, organization_id="acme", zone=prod)


def test_apply_requires_root_outside_test_layout(registry, monkeypatch):
    paths, _, _ = registry
    monkeypatch.setattr(organizations.os, "geteuid", lambda: 501)
    with pytest.raises(SecurityError, match="root authority"):
        organizations.register_organization(replace(paths, test_mode=False), organization_id="acme", zone_ids=["acme-dev"])


def test_registry_symlink_and_parent_writable_refused(registry, tmp_path):
    paths, _, _ = registry
    outside = tmp_path / "outside"
    outside.mkdir()
    (paths.config / "organizations.d").symlink_to(outside, target_is_directory=True)
    with pytest.raises((SecurityError, OSError)):
        organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"])
    assert not list(outside.iterdir())


def test_registration_rechecks_identity_under_lock(registry, monkeypatch):
    from contextlib import contextmanager
    from agentik_station import installer

    paths, zone, path = registry
    @contextmanager
    def lock(*args):
        path.write_text(json.dumps({**zone, "organization": "other"}))
        yield
    monkeypatch.setattr(installer, "install_lock", lock)
    with pytest.raises(ValidationError):
        organizations.register_organization(paths, organization_id="acme", zone_ids=["acme-dev"])
    assert not (paths.config / "organizations.d").exists()
