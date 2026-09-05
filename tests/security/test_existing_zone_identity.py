"""Fail before apt, metadata overwrite or chown when a Zone identity conflicts."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import installer as kernel
from agentik_station.errors import ReconcileError, SecurityError, ValidationError
from agentik_station.models import InstallSpec, SeedSpec, ZoneSpec
from agentik_station.paths import LayoutPaths
from test_organizations import write_zone

ROOT = Path(__file__).resolve().parents[2]


def make_installer(tmp_path, *, category="ORGANIZATIONS", name="acme", organization="acme", host="host-one", dry_run=False):
    paths = LayoutPaths.under(tmp_path.resolve() / "host")
    spec = InstallSpec(host_id=host, role="team" if category == "ORGANIZATIONS" else "project",
                       seed=SeedSpec(category, name, "development", organization),
                       install_system_packages=False, configure_fail2ban=False, enable_doctor_timer=False)
    return kernel.StationInstaller(ROOT, spec, paths, dry_run=dry_run)


def forbid_mutation(monkeypatch, instance):
    def fail(*args, **kwargs):
        pytest.fail("Identity preflight allowed a mutation")
    monkeypatch.setattr(instance.fs, "mkdir", fail)
    monkeypatch.setattr(instance.fs, "write_text", fail)
    monkeypatch.setattr(instance.fs, "rollback", fail)
    monkeypatch.setattr(instance.commands, "run", fail)
    monkeypatch.setattr(kernel, "install_lock", fail)


@pytest.mark.parametrize("old", [
    {"category": "PROJECTS"}, {"organization": "other"}, {"organization": None}, {"host": "host-two"},
])
def test_conflicting_persistent_identity_fails_before_any_mutation(tmp_path, monkeypatch, old):
    instance = make_installer(tmp_path)
    _, path = write_zone(instance.paths, **old)
    before = path.read_bytes()
    forbid_mutation(monkeypatch, instance)
    with pytest.raises((ReconcileError, ValidationError)):
        instance.apply()
    assert path.read_bytes() == before
    assert not instance.paths.varlib.exists()


@pytest.mark.parametrize("kind", ["human", "state", "log", "run", "backup", "binding"])
def test_orphan_state_never_authorizes_adoption(tmp_path, monkeypatch, kind):
    instance = make_installer(tmp_path)
    zone = instance._compiled_zones[-1]
    paths = instance.paths
    root = {"human": instance._zone_human_path(zone), "state": paths.zones_state / zone.zone_id,
            "log": paths.log / "zones" / zone.zone_id, "run": paths.run / "zones" / zone.zone_id,
            "backup": paths.backups / "zones" / zone.zone_id,
            "binding": paths.varlib / "zone-bindings" / f"{zone.zone_id}.json"}[kind]
    if kind == "binding":
        root.parent.mkdir(parents=True)
        root.write_text("{}")
    else:
        root.mkdir(parents=True)
        (root / "keep.txt").write_text("client-owned")
    forbid_mutation(monkeypatch, instance)
    with pytest.raises(ReconcileError, match="without its trusted identity"):
        instance.apply()
    if kind != "binding":
        assert (root / "keep.txt").read_text() == "client-owned"


def test_existing_host_cannot_be_renamed_by_reconcile(tmp_path, monkeypatch):
    instance = make_installer(tmp_path)
    instance.paths.config.mkdir(parents=True)
    (instance.paths.config / "station.json").write_text(json.dumps({"schema_version": 1, "host_id": "other-host"}))
    forbid_mutation(monkeypatch, instance)
    with pytest.raises(ReconcileError, match="Host identity"):
        instance.apply()


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "fifo", "writable", "parent-link", "duplicate-key"])
def test_unsafe_existing_record_refused(tmp_path, monkeypatch, unsafe):
    instance = make_installer(tmp_path)
    _, path = write_zone(instance.paths)
    if unsafe == "symlink":
        target = tmp_path / "target.json"
        path.rename(target)
        path.symlink_to(target)
    elif unsafe == "hardlink":
        os.link(path, tmp_path / "alias.json")
    elif unsafe == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif unsafe == "writable":
        path.chmod(0o666)
    elif unsafe == "parent-link":
        target = tmp_path / "records"
        path.parent.rename(target)
        path.parent.symlink_to(target, target_is_directory=True)
    else:
        path.write_text('{"schema_version":2,"schema_version":2}')
    forbid_mutation(monkeypatch, instance)
    with pytest.raises((SecurityError, ValidationError, OSError)):
        instance.apply()


def test_matching_record_and_runtime_are_safe_to_plan_without_mutations(tmp_path, capsys):
    instance = make_installer(tmp_path, dry_run=True)
    zone, _ = write_zone(instance.paths)
    Path(zone["state_root"]).mkdir(parents=True)
    (Path(zone["state_root"]) / "secret.txt").write_text("keep")
    assert instance.apply() == "PLAN_READY"
    assert not instance.paths.receipts.exists()
    assert not instance.paths.run.exists()
    assert "keep" not in capsys.readouterr().out


def test_preflight_rechecks_immediately_under_lock_before_receipt(tmp_path, monkeypatch):
    instance = make_installer(tmp_path)
    _, path = write_zone(instance.paths)
    @contextmanager
    def lock(*args):
        zone = json.loads(path.read_text())
        zone["organization"] = "other"
        path.write_text(json.dumps(zone))
        yield
    monkeypatch.setattr(kernel, "install_lock", lock)
    monkeypatch.setattr(instance.fs, "mkdir", lambda *a, **k: pytest.fail("receipt/FHS mutation"))
    monkeypatch.setattr(instance.fs, "rollback", lambda: pytest.fail("rollback should not run"))
    with pytest.raises(ReconcileError):
        instance.apply()
    assert not instance.paths.receipts.exists()


def test_distinct_zone_ids_must_not_alias_same_fixed_unix_user(tmp_path):
    instance = make_installer(tmp_path)
    instance._compiled_zones = [ZoneSpec("PRIVATE", "alice", "private", "host-one"),
                                ZoneSpec("PRIVATE", "bob", "private", "host-one")]
    with pytest.raises(ReconcileError, match="alias one Unix identity"):
        instance._preflight_zone_identities()


def test_host_qualified_remote_desired_does_not_claim_local_identity(tmp_path):
    instance = make_installer(tmp_path)
    root = instance.paths.config / "zones.d"
    root.mkdir(parents=True)
    remote = {"schema_version": 1, "id": "acme-dev", "category": "ORGANIZATIONS",
              "organization": "acme", "environment": "development", "host_id": "remote-host",
              "placement": "REMOTE_DESIRED_NOT_APPLIED", "runtime_state": "NOT_INSTALLED",
              "next_repair_action": "Apply the approved remote Host plan."}
    (root / "remote-remote-host-acme-dev.json").write_text(json.dumps(remote))
    instance._preflight_zone_identities()
    assert not instance.paths.run.exists()


def test_plan_keeps_explicit_seed_target_after_identical_zone_deduplication(tmp_path):
    from dataclasses import replace
    from agentik_station.configuration import ZoneTemplate
    from agentik_station.planner import build_plan

    instance = make_installer(tmp_path)
    first = ZoneTemplate("ORGANIZATIONS", "acme", "development", "acme", ())
    last = ZoneTemplate("ORGANIZATIONS", "beta", "development", "beta", ())
    config = replace(instance.config, roles={**instance.config.roles, "team": (first, last)})
    spec = replace(instance.spec, seed=SeedSpec("ORGANIZATIONS", "acme", "development", "acme", "website"))
    project = next(step for step in build_plan(spec, config) if step.id == "project-website")
    assert project.detail["zone_id"] == "acme-dev"


@pytest.mark.parametrize("condition", ["untracked-user", "untracked-group", "home", "interactive", "root", "missing-group", "shared-uid", "shared-gid"])
def test_live_account_readback_does_not_reassign_identities(tmp_path, monkeypatch, condition):
    instance = make_installer(tmp_path)
    zones = [ZoneSpec("ORGANIZATIONS", name, "development", "host-one", name) for name in ("acme", "beta")]
    identities = {"z-o-acme-dev": zones[0], "z-o-beta-dev": zones[1]}
    existing = {z.zone_id: z for z in zones}
    entries = {name: SimpleNamespace(pw_uid=1001 + i, pw_gid=1001 + i,
               pw_dir=str(instance.paths.zones_state / zone.zone_id / "home"), pw_shell="/usr/sbin/nologin")
               for i, (name, zone) in enumerate(identities.items())}
    groups = {name: SimpleNamespace(gr_gid=entry.pw_gid) for name, entry in entries.items()}
    first, second = entries.values()
    if condition.startswith("untracked"):
        existing = {}
        if condition == "untracked-group":
            entries = {}
    elif condition == "home":
        first.pw_dir = "/home/unrelated"
    elif condition == "interactive":
        first.pw_shell = "/bin/bash"
    elif condition == "root":
        first.pw_uid = 0
    elif condition == "missing-group":
        groups = {}
    elif condition == "shared-uid":
        second.pw_uid = first.pw_uid
    elif condition == "shared-gid":
        second.pw_gid = first.pw_gid
        groups["z-o-beta-dev"].gr_gid = first.pw_gid
    monkeypatch.setattr(kernel.pwd, "getpwnam", lambda name: entries[name])
    monkeypatch.setattr(kernel.grp, "getgrnam", lambda name: groups[name])
    with pytest.raises(ReconcileError):
        instance._audit_zone_accounts(identities, existing)


def test_matching_accounts_and_missing_untracked_accounts_are_read_only(tmp_path, monkeypatch):
    instance = make_installer(tmp_path)
    zone = ZoneSpec("ORGANIZATIONS", "acme", "development", "host-one", "acme")
    monkeypatch.setattr(kernel.pwd, "getpwnam", lambda name: SimpleNamespace(
        pw_uid=1001, pw_gid=1001, pw_dir=str(instance.paths.zones_state / zone.zone_id / "home"), pw_shell="/bin/false"))
    monkeypatch.setattr(kernel.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=1001))
    instance._audit_zone_accounts({"z-o-acme-dev": zone}, {zone.zone_id: zone})
    def absent(name):
        raise KeyError(name)
    monkeypatch.setattr(kernel.pwd, "getpwnam", absent)
    monkeypatch.setattr(kernel.grp, "getgrnam", absent)
    instance._audit_zone_accounts({"z-o-acme-dev": zone}, {})
    assert not instance.paths.config.exists()
