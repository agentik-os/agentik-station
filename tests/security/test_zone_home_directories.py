"""Managed HOME parents must be usable by the Zone, not just by root Doctor."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agentik_station import doctor
from agentik_station.errors import SecurityError
from agentik_station.identity import Identity
from agentik_station.installer import StationInstaller
from agentik_station.models import InstallSpec, SeedSpec, ZoneSpec
from agentik_station.paths import LayoutPaths

ROOT = Path(__file__).resolve().parents[2]
HOME_COMPONENTS = (".config", ".config/containers", ".local", ".local/share", ".local/share/containers")


def _fixture(tmp_path: Path):
    paths = LayoutPaths.under(tmp_path.resolve() / "root")
    instance = StationInstaller(ROOT, InstallSpec(), paths=paths)
    zone = ZoneSpec("AGENTIK", "dev", "development", "station-core-01")
    state = paths.zones_state / zone.zone_id
    home = state / "home"
    owner = (os.getuid(), os.getgid())
    instance.fs.mkdir(state, 0o700, owner)
    instance.fs.mkdir(home, 0o700, owner)
    identity = Identity("z-agentik-dev", *owner, home)
    return instance, zone, identity, state


def _configure(instance, zone, identity, state):
    instance._configure_zone_rootless(zone, identity, state)


def test_fresh_rootless_configuration_explicitly_owns_every_managed_parent(tmp_path, monkeypatch):
    instance, zone, identity, state = _fixture(tmp_path)
    home = state / "home"
    intended = (61001, 61002)
    ownership_calls = []

    def record_fchown(fd, uid, gid):
        st = os.fstat(fd)
        ownership_calls.append((st.st_ino, uid, gid, stat.S_IMODE(st.st_mode)))

    monkeypatch.setattr(os, "fchown", record_fchown)
    _configure(instance, zone, Identity(identity.name, *intended, home), state)

    # A deep mkdir alone creates implicit root-owned parents on a real VPS.
    for relative in HOME_COMPONENTS:
        directory = home / relative
        assert (directory.stat().st_ino, *intended, 0o700) in ownership_calls
    indexes = [next(i for i, call in enumerate(ownership_calls) if call[0] == (home / p).stat().st_ino)
               for p in HOME_COMPONENTS]
    assert indexes == sorted(indexes)


def test_retry_repairs_only_exact_managed_directories_and_preserves_user_data(tmp_path, monkeypatch):
    instance, zone, identity, state = _fixture(tmp_path)
    _configure(instance, zone, identity, state)
    home = state / "home"
    unrelated = home / ".config" / "unrelated"
    unrelated.mkdir(mode=0o750)
    payload = unrelated / "private.json"
    payload.write_bytes(b"client-owned: preserve exactly\n")
    payload.chmod(0o600)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o750)
    alias = unrelated / "external-link"
    alias.symlink_to(outside, target_is_directory=True)
    storage = home / ".local/share/containers" / "existing-storage"
    storage.mkdir(mode=0o750)
    (storage / "keep").write_text("existing container state")
    retained = {path: (path.lstat(), path.read_bytes() if path.is_file() else None)
                for path in (unrelated, payload, alias, outside, storage, storage / "keep")}
    for relative in HOME_COMPONENTS:
        (home / relative).chmod(0o750)
    ownership_calls = []

    def record_fchown(fd, uid, gid):
        ownership_calls.append((os.fstat(fd).st_ino, uid, gid))

    monkeypatch.setattr(os, "fchown", record_fchown)
    intended = (61001, 61002)
    _configure(instance, zone, Identity(identity.name, *intended, home), state)

    for relative in HOME_COMPONENTS:
        st = (home / relative).stat()
        assert stat.S_IMODE(st.st_mode) == 0o700
        assert (st.st_ino, *intended) in ownership_calls
    for path, (before, content) in retained.items():
        after = path.lstat()
        assert (after.st_ino, after.st_mode, after.st_uid, after.st_gid) == (
            before.st_ino, before.st_mode, before.st_uid, before.st_gid)
        assert not any(call[0] == after.st_ino for call in ownership_calls)
        if content is not None:
            assert path.read_bytes() == content
    assert alias.readlink() == outside


@pytest.mark.parametrize("relative", [".config", ".local", ".local/share"])
@pytest.mark.parametrize("kind", ["symlink", "file", "fifo"])
def test_reconcile_refuses_unsafe_managed_parent_without_touching_target(tmp_path, relative, kind):
    instance, zone, identity, state = _fixture(tmp_path)
    target = state / "home" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o750)
    marker = outside / "keep"
    marker.write_text("unrelated")
    before = outside.stat()
    if kind == "symlink":
        target.symlink_to(outside, target_is_directory=True)
    elif kind == "file":
        target.write_text("preserve non-directory")
    else:
        os.mkfifo(target, 0o600)

    with pytest.raises(SecurityError):
        _configure(instance, zone, identity, state)

    assert marker.read_text() == "unrelated"
    after = outside.stat()
    assert (before.st_mode, before.st_uid, before.st_gid) == (after.st_mode, after.st_uid, after.st_gid)
    if kind == "file":
        assert target.read_text() == "preserve non-directory"
    elif kind == "symlink":
        assert target.readlink() == outside
    else:
        assert stat.S_ISFIFO(target.lstat().st_mode)


def _doctor_fixture(tmp_path):
    instance, zone, identity, state = _fixture(tmp_path)
    _configure(instance, zone, identity, state)
    return state, (identity.uid, identity.gid)


def test_doctor_accepts_private_zone_owned_home_without_runtime_claim(tmp_path):
    state, owner = _doctor_fixture(tmp_path)
    result = doctor.DoctorResult("test")
    assert doctor._check_zone_home_directories(result, state, "home-access", owner)
    assert result.ok
    assert "native runtime not tested" in result.checks[0]["detail"]


@pytest.mark.parametrize("relative", [".", "home", *("home/" + path for path in HOME_COMPONENTS)])
def test_doctor_detects_wrong_owner_even_when_caller_can_traverse(tmp_path, monkeypatch, relative):
    state, owner = _doctor_fixture(tmp_path)
    target = state / relative
    original_lstat = os.lstat

    def wrong_owner(path, *args, **kwargs):
        st = original_lstat(path, *args, **kwargs)
        if Path(path) == target:
            values = list(st)
            values[4] = 0 if owner[0] else 61001
            values[5] = 0 if owner[1] else 61002
            return os.stat_result(values)
        return st

    monkeypatch.setattr(os, "lstat", wrong_owner)
    result = doctor.DoctorResult("test")
    assert not doctor._check_zone_home_directories(result, state, "home-access", owner)
    assert not result.ok
    assert "is owned by" in result.issues[0]["message"]
    assert str(target) in result.issues[0]["message"]


@pytest.mark.parametrize("mode", [0o000, 0o600, 0o500, 0o750, 0o777])
def test_doctor_detects_missing_owner_access_or_privacy_drift(tmp_path, mode):
    state, owner = _doctor_fixture(tmp_path)
    target = state / "home/.config"
    target.chmod(mode)
    try:
        result = doctor.DoctorResult("test")
        assert not doctor._check_zone_home_directories(result, state, "home-access", owner)
        assert "0700" in result.issues[0]["message"]
    finally:
        target.chmod(0o700)


@pytest.mark.parametrize("kind", ["missing", "symlink", "file", "fifo", "permission-error"])
def test_doctor_stops_before_unsafe_or_unreadable_parent(tmp_path, monkeypatch, kind):
    state, owner = _doctor_fixture(tmp_path)
    target = state / "home/.config"
    if kind != "permission-error":
        moved = tmp_path / "preserved-config"
        target.rename(moved)
        if kind == "symlink":
            target.symlink_to(moved, target_is_directory=True)
        elif kind == "file":
            target.write_text("not a directory")
        elif kind == "fifo":
            os.mkfifo(target, 0o600)
    original_lstat = os.lstat

    def bounded_lstat(path, *args, **kwargs):
        path = Path(path)
        assert target not in path.parents, "Doctor descended through an unsafe HOME parent"
        if path == target and kind == "permission-error":
            raise PermissionError("private details must not be included")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", bounded_lstat)
    result = doctor.DoctorResult("test")
    assert not doctor._check_zone_home_directories(result, state, "home-access", owner)
    assert not result.ok
    assert "private details" not in str(result.to_dict())


def test_station_doctor_wires_home_access_guard_before_rootless_files(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve() / "root")
    spec = InstallSpec(
        operation_id="op-zone-home-access", host_id="organization-alpha-prod-01", role="team",
        install_system_packages=False, configure_fail2ban=False, enable_doctor_timer=False,
        seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha"),
    )
    assert StationInstaller(ROOT, spec, paths=paths).apply() == "READY_FOR_SETUP"
    target = paths.zones_state / "organization-alpha-prod" / "home/.config"
    target.chmod(0o750)
    original_check = doctor._check_regular

    def guarded_check(result, path, label):
        assert target not in path.parents, "Rootless leaf checked after HOME access failed"
        return original_check(result, path, label)

    monkeypatch.setattr(doctor, "_check_regular", guarded_check)
    result = doctor.station_doctor(paths, repo_root=ROOT, full=True)
    assert not result.ok
    assert any(item["name"] == "zone:organization-alpha-prod:home-access" for item in result.issues)


@pytest.mark.parametrize("defect", ["closed", "writable", "wrong-owner", "symlink", "file", "fifo", "missing"])
def test_traversal_anchor_requires_real_authority_owned_search_only_directory(tmp_path, monkeypatch, defect):
    directory = tmp_path / "anchor"
    directory.mkdir(mode=0o711)
    if defect == "closed":
        directory.chmod(0o750)
    elif defect == "writable":
        directory.chmod(0o733)
    elif defect == "wrong-owner":
        original = os.lstat

        def foreign_owner(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if Path(path) == directory:
                fields = list(info)
                fields[4] += 10000
                return os.stat_result(fields)
            return info

        monkeypatch.setattr(os, "lstat", foreign_owner)
    else:
        directory.rmdir()
        if defect == "symlink":
            directory.symlink_to(tmp_path)
        elif defect == "file":
            directory.write_text("preserve")
        elif defect == "fifo":
            os.mkfifo(directory)
    result = doctor.DoctorResult("test")
    assert not doctor._check_zone_traversal_directory(result, directory, "anchor", os.getuid())
    assert not result.ok


@pytest.mark.parametrize("anchor", ["state", "logs", "run", "backups"])
def test_doctor_checks_intermediate_zone_traversal_before_private_descendants(tmp_path, monkeypatch, anchor):
    paths = LayoutPaths.under(tmp_path.resolve() / "root")
    spec = InstallSpec(
        operation_id="op-intermediate-traversal", host_id="organization-alpha-prod-01", role="team",
        install_system_packages=False, configure_fail2ban=False, enable_doctor_timer=False,
        seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha"),
    )
    assert StationInstaller(ROOT, spec, paths=paths).apply() == "READY_FOR_SETUP"
    directory = {"state": paths.zones_state, "logs": paths.log / "zones",
                 "run": paths.run / "zones", "backups": paths.backups / "zones"}[anchor]
    directory.chmod(0o750)
    original = os.lstat

    def no_private_descent(path, *args, **kwargs):
        assert directory not in Path(path).parents, "Doctor inspected private paths through a closed shared anchor"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", no_private_descent)
    result = doctor.station_doctor(paths, repo_root=ROOT, full=True)
    assert not result.ok
    assert any(item["name"] == f"mode:zone-traversal:zones-{anchor}" for item in result.issues)
