from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("station_controls_refresh", ROOT / "scripts/refresh-controls.py")
assert SPEC and SPEC.loader
refresh = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = refresh
SPEC.loader.exec_module(refresh)


@pytest.fixture
def controls(tmp_path, monkeypatch):
    home = tmp_path / "home"
    prefix = home / ".local"
    source = tmp_path / "source"
    account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_name="agk-station", pw_dir=str(home))
    monkeypatch.setattr(refresh, "_operator", lambda: account)
    previous = {}
    pairs = []
    for relative in refresh.PREVIOUS:
        src = source / relative
        dst = prefix / ("bin/agk" if relative == "bin/agk" else "lib/agk-terminal/scripts/agk_control.py")
        src.parent.mkdir(parents=True, exist_ok=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        old = ("#!/bin/sh\n# old " + relative + "\n").encode()
        new = ("#!/bin/sh\n# new " + relative + "\n").encode()
        src.write_bytes(new)
        dst.write_bytes(old)
        src.chmod(0o755)
        dst.chmod(0o755)
        previous[relative] = hashlib.sha256(old).hexdigest()
        pairs.append((src, dst, old, new))
    monkeypatch.setattr(refresh, "PREVIOUS", previous)
    return source, prefix, pairs


def test_refresh_only_two_reviewed_controls_and_idempotent(controls):
    source, prefix, pairs = controls
    untouched = [prefix / "lib/agk-terminal/bin/agk-tui", prefix / "lib/agk-terminal/config/providers.yaml",
                 prefix.parent / ".hermes/.env", prefix.parent / ".agentik/runtime.db"]
    for path in untouched:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-do-not-touch")
        path.chmod(0o600)
    result = refresh.refresh_controls(source, prefix)
    assert result == {"state": "CONTROLS_REFRESHED", "changed": ["agk", "agk_control.py"], "runtime_verified": False}
    for _, dst, _, new in pairs:
        assert dst.read_bytes() == new
        assert stat.S_IMODE(dst.stat().st_mode) == 0o755
    assert all(path.read_bytes() == b"synthetic-do-not-touch" for path in untouched)
    assert refresh.refresh_controls(source, prefix)["changed"] == []


@pytest.mark.parametrize("which", [0, 1])
def test_customized_controls_preserved_before_any_write(controls, which):
    source, prefix, pairs = controls
    pairs[which][1].write_bytes(b"operator customized script")
    before = [dst.read_bytes() for _, dst, _, _ in pairs]
    with pytest.raises(ValueError, match="customized"):
        refresh.refresh_controls(source, prefix)
    assert [dst.read_bytes() for _, dst, _, _ in pairs] == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "writable", "missing"])
def test_unsafe_controls_are_not_followed_or_replaced(controls, kind):
    source, prefix, pairs = controls
    src, dst, _, _ = pairs[1]
    if kind in {"symlink", "hardlink", "fifo", "missing"}:
        dst.unlink()
        if kind == "symlink":
            dst.symlink_to(src)
        elif kind == "hardlink":
            os.link(src, dst)
        elif kind == "fifo":
            os.mkfifo(dst)
    else:
        dst.chmod(0o777)
    with pytest.raises((ValueError, OSError)):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


def test_symlinked_destination_parent_is_refused(controls):
    source, prefix, pairs = controls
    parent = pairs[1][1].parent
    moved = parent.with_name("moved")
    parent.rename(moved)
    parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises(OSError):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


def test_unexpected_prefix_is_refused(controls):
    source, prefix, _ = controls
    with pytest.raises(ValueError, match="canonical"):
        refresh.refresh_controls(source, prefix.parent / "elsewhere")


def test_changed_target_between_preflight_and_write_is_preserved(controls, monkeypatch):
    source, prefix, pairs = controls
    read = refresh._read
    count = 0
    def racing_read(*args):
        nonlocal count
        count += 1
        if count == 5:
            pairs[0][1].write_bytes(b"concurrent operator edit")
        return read(*args)
    monkeypatch.setattr(refresh, "_read", racing_read)
    with pytest.raises(ValueError, match="changed during"):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == b"concurrent operator edit"
    assert pairs[1][1].read_bytes() == pairs[1][2]


def test_parent_rename_cannot_claim_readback_of_obsolete_directory(controls, monkeypatch):
    source, prefix, pairs = controls
    read = refresh._read
    count = 0
    def renamed_read(*args):
        nonlocal count
        count += 1
        data = read(*args)
        if count == 6:
            parent = pairs[0][1].parent
            parent.rename(parent.with_name("obsolete-bin"))
            parent.mkdir()
            pairs[0][1].write_bytes(pairs[0][2])
            pairs[0][1].chmod(0o755)
        return data
    monkeypatch.setattr(refresh, "_read", renamed_read)
    with pytest.raises(ValueError, match="directory changed"):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]
    assert pairs[1][1].read_bytes() == pairs[1][2]


def test_read_rejects_replaced_file_identity(controls, monkeypatch):
    source, prefix, pairs = controls
    original_stat = refresh.os.stat
    swapped = False
    def changed_stat(path, *args, **kwargs):
        nonlocal swapped
        if path == "agk" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            target = pairs[0][0]
            target.rename(target.with_name("old-agk"))
            target.write_bytes(pairs[0][3])
            target.chmod(0o755)
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(refresh.os, "stat", changed_stat)
    with pytest.raises(ValueError, match="file changed while"):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


def test_partial_write_failure_can_retry_without_claiming_rollback(controls, monkeypatch):
    source, prefix, pairs = controls
    replace = refresh.os.replace
    count = 0
    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("fixture unavailable")
        return replace(*args, **kwargs)
    monkeypatch.setattr(refresh.os, "replace", fail_second)
    with pytest.raises(OSError):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][3]
    assert pairs[1][1].read_bytes() == pairs[1][2]
    assert not list(prefix.rglob(".station-control-*"))
    assert refresh.refresh_controls(source, prefix)["changed"] == ["agk_control.py"]


@pytest.mark.parametrize("uid,user,home", [(0, "agk-station", "/home/agk-station"), (1000, "moonbase", "/home/moonbase"), (2000, "agk-station", "/other/home")])
def test_refresh_requires_nonroot_canonical_identity(monkeypatch, uid, user, home):
    monkeypatch.setattr(refresh.os, "geteuid", lambda: uid)
    monkeypatch.setattr(refresh.os, "getuid", lambda: uid)
    monkeypatch.setattr(refresh.pwd, "getpwuid", lambda _: SimpleNamespace(pw_uid=uid, pw_name=user, pw_dir=home))
    with pytest.raises(ValueError, match="non-root"):
        refresh._operator()


def test_component_controls_path_exits_before_build_network_or_hermes():
    source = (ROOT / "install.sh").read_text()
    invoke = source.index('exec /usr/bin/python3 -I "$repo_root/scripts/refresh-controls.py"')
    assert invoke < source.index("install_rmux\n")
    assert invoke < source.index("build --locked --release")
    assert invoke < source.index('pip install')
