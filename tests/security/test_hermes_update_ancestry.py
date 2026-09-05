from dataclasses import replace
from pathlib import Path
import os
import stat
import tempfile
from types import SimpleNamespace

import pytest

from agentik_station import hermes_updates
from agentik_station.errors import ValidationError
from agentik_station.paths import LayoutPaths


@pytest.fixture
def private_tmp_root():
    # Use the real, canonical sticky temporary directory on both Linux and macOS.
    temporary_root = Path('/tmp').resolve(strict=True)
    info = temporary_root.stat()
    assert info.st_uid == 0 and info.st_mode & stat.S_ISVTX
    with tempfile.TemporaryDirectory(prefix='station-hermes-ancestry-', dir=temporary_root) as name:
        yield Path(name)


def record(paths):
    return hermes_updates.run_check(
        paths, record=True,
        fetch=lambda *args: {'status': 'OBSERVED_NOT_ACCEPTED', 'latest': 'v2026.8.31'},
    )


def test_private_fixture_below_real_sticky_tmp_records_private_receipt(private_tmp_root):
    paths = LayoutPaths.under(private_tmp_root)
    result = record(paths)
    receipt = Path(result['receipt'])
    assert receipt.parent == paths.varlib / 'hermes-updates'
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt.parent.stat().st_mode) == 0o700
    assert result['commands'] == [] and result['applied'] is False


@pytest.mark.parametrize('location', ['external', 'fixture', 'managed', 'evidence'])
@pytest.mark.parametrize('mode', [0o777, 0o1777])
def test_writable_fixture_or_untrusted_external_parent_is_rejected(private_tmp_root, location, mode, monkeypatch):
    anchor = private_tmp_root / 'fixture'
    anchor.mkdir(mode=0o700)
    paths = LayoutPaths.under(anchor)
    parent = {
        'external': private_tmp_root,
        'fixture': anchor,
        'managed': paths.varlib,
        'evidence': paths.varlib / 'hermes-updates',
    }[location]
    parent.mkdir(parents=True, exist_ok=True)
    parent.chmod(mode)
    if location == 'external' and mode & stat.S_ISVTX:
        # Even when tests run as root, an attacker-owned sticky ancestor is not
        # equivalent to root-owned /tmp. Keep the fixture itself truly private.
        original_lstat = Path.lstat

        def untrusted_owner(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == parent:
                values = list(info)
                values[4] = os.getuid() or 65534
                return os.stat_result(values)
            return info

        monkeypatch.setattr(Path, 'lstat', untrusted_owner)
    with pytest.raises(ValidationError, match='Unsafe update evidence ancestry'):
        record(paths)
    assert not list((paths.varlib / 'hermes-updates').glob('check-*.json'))


def test_inconsistent_test_layout_cannot_enable_tmp_exception(private_tmp_root):
    paths = replace(LayoutPaths.under(private_tmp_root), software=private_tmp_root / 'other-software')
    with pytest.raises(ValidationError, match='Invalid update evidence test layout'):
        record(paths)
    assert not paths.varlib.exists()


def test_live_mode_does_not_receive_sticky_tmp_exception(private_tmp_root, monkeypatch):
    paths = replace(LayoutPaths.under(private_tmp_root), test_mode=False)
    monkeypatch.setattr(hermes_updates.os, 'geteuid', lambda: 0)
    with pytest.raises(ValidationError, match='Unsafe update evidence ancestry'):
        record(paths)
    assert not paths.varlib.exists()


def test_symlinked_external_parent_is_rejected(private_tmp_root):
    actual = private_tmp_root / 'actual'
    actual.mkdir(mode=0o700)
    linked = private_tmp_root / 'linked'
    linked.symlink_to(actual, target_is_directory=True)
    paths = LayoutPaths.under(linked / 'fixture')
    with pytest.raises(ValidationError, match='Unsafe update evidence ancestry'):
        record(paths)
    assert not paths.varlib.exists()


@pytest.mark.skipif(os.name == 'nt' or os.geteuid() == 0, reason='requires native non-root directory permissions')
def test_watcher_receipt_traverses_execute_only_ancestor_without_listing(private_tmp_root):
    ancestor = private_tmp_root / 'execute-only'
    parent = ancestor / 'system'
    parent.mkdir(parents=True, mode=0o700)
    ancestor.chmod(0o111)
    try:
        with pytest.raises(PermissionError):
            os.listdir(ancestor)
        with pytest.raises(PermissionError):
            os.open(ancestor, os.O_RDONLY | os.O_DIRECTORY)
        target = hermes_updates._write_watcher_receipt(parent, '{"applied": false}\n')
        assert target.read_text() == '{"applied": false}\n'
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(ancestor.stat().st_mode) == 0o111
    finally:
        ancestor.chmod(0o700)


@pytest.mark.parametrize('location', ['parent', 'leaf'])
@pytest.mark.parametrize('mode', [0o755, 0o770, 0o1777])
def test_watcher_receipt_rejects_nonprivate_directories(private_tmp_root, location, mode):
    parent = private_tmp_root / 'system'
    leaf = parent / 'hermes-updates'
    leaf.mkdir(parents=True, mode=0o700)
    parent.chmod(0o700)
    (parent if location == 'parent' else leaf).chmod(mode)
    with pytest.raises(ValidationError, match='Unsafe private watcher evidence directory'):
        hermes_updates._write_watcher_receipt(parent, '{}\n')
    assert not list(leaf.iterdir())


@pytest.mark.parametrize('location', ['parent', 'leaf'])
def test_watcher_receipt_rejects_foreign_directory_ownership(private_tmp_root, location, monkeypatch):
    parent = private_tmp_root / 'system'
    leaf = parent / 'hermes-updates'
    leaf.mkdir(parents=True, mode=0o700)
    parent.chmod(0o700)
    foreign_inode = (parent if location == 'parent' else leaf).stat().st_ino
    original_fstat = os.fstat

    def foreign_owner(fd):
        info = original_fstat(fd)
        if info.st_ino == foreign_inode:
            values = list(info)
            values[4] = os.geteuid() + 1
            return os.stat_result(values)
        return info

    monkeypatch.setattr(os, 'fstat', foreign_owner)
    with pytest.raises(ValidationError, match='Unsafe private watcher evidence directory'):
        hermes_updates._write_watcher_receipt(parent, '{}\n')
    assert not list(leaf.iterdir())


@pytest.mark.parametrize('location', ['parent', 'leaf'])
def test_watcher_receipt_rejects_symlinked_directories(private_tmp_root, location):
    parent = private_tmp_root / 'system'
    parent.mkdir(mode=0o700)
    outside = private_tmp_root / 'outside'
    outside.mkdir(mode=0o700)
    if location == 'parent':
        linked = private_tmp_root / 'linked-system'
        linked.symlink_to(parent, target_is_directory=True)
        parent = linked
    else:
        (parent / 'hermes-updates').symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        hermes_updates._write_watcher_receipt(parent, '{}\n')
    assert not list(outside.iterdir())


def test_existing_watcher_leaf_needs_no_parent_mutation(private_tmp_root, monkeypatch):
    parent = private_tmp_root / 'system'
    leaf = parent / 'hermes-updates'
    leaf.mkdir(parents=True, mode=0o700)
    parent.chmod(0o700)
    monkeypatch.setattr(os, 'mkdir', lambda *a, **kw: pytest.fail('existing watcher parent may be mounted read-only'))
    target = hermes_updates._write_watcher_receipt(parent, '{}\n')
    assert target.parent == leaf and target.read_text() == '{}\n'


def test_watcher_receipt_collision_never_overwrites_or_unlinks_existing_file(private_tmp_root, monkeypatch):
    parent = private_tmp_root / 'system'
    parent.mkdir(mode=0o700)
    monkeypatch.setattr(hermes_updates, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    target = hermes_updates._write_watcher_receipt(parent, 'first\n')
    with pytest.raises(FileExistsError):
        hermes_updates._write_watcher_receipt(parent, 'second\n')
    assert target.read_text() == 'first\n'


def test_watcher_receipt_failed_write_removes_only_new_partial_file(private_tmp_root, monkeypatch):
    parent = private_tmp_root / 'system'
    parent.mkdir(mode=0o700)
    previous = hermes_updates._write_watcher_receipt(parent, 'previous\n')

    def failed_write(*args):
        raise OSError('synthetic write failure')

    monkeypatch.setattr(os, 'write', failed_write)
    with pytest.raises(OSError, match='synthetic write failure'):
        hermes_updates._write_watcher_receipt(parent, 'incomplete\n')
    assert list(previous.parent.iterdir()) == [previous]
    assert previous.read_text() == 'previous\n'


def test_fixture_receipts_never_use_watcher_writer(private_tmp_root, monkeypatch):
    monkeypatch.setattr(hermes_updates, '_write_watcher_receipt', lambda *a: pytest.fail('fixture must retain SafeFS'))
    result = record(LayoutPaths.under(private_tmp_root))
    assert Path(result['receipt']).is_file()


@pytest.mark.parametrize('effective_uid', [0, 1234])
def test_live_writer_dispatch_keeps_root_out_of_watcher_state(effective_uid, monkeypatch):
    paths = LayoutPaths.live()
    root = paths.varlib / ('hermes-updates' if effective_uid == 0 else 'system/hermes-updates')
    ancestry = {root, *root.parents}
    original_exists, original_lstat = Path.exists, Path.lstat
    monkeypatch.setattr(hermes_updates.os, 'geteuid', lambda: effective_uid)
    monkeypatch.setattr(hermes_updates.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_name='station-system'))
    monkeypatch.setattr(hermes_updates, 'source_observation', lambda root: {'state': 'NOT_INSTALLED'})
    monkeypatch.setattr(Path, 'exists', lambda path: True if path in ancestry else original_exists(path))
    monkeypatch.setattr(Path, 'lstat', lambda path: (
        os.stat_result((stat.S_IFDIR | 0o700, 1, 1, 1, 0, 0, 0, 0, 0, 0))
        if path in ancestry else original_lstat(path)
    ))
    calls = []

    class FakeSafeFS:
        def __init__(self, roots):
            assert effective_uid == 0, 'live non-root watcher cannot use ancestor-listing SafeFS'

        def mkdir(self, target, mode):
            assert target == paths.varlib / 'hermes-updates' and mode == 0o700

        def write_text(self, target, serialized, mode):
            assert target.parent == root and mode == 0o600
            calls.append('root-safe-fs')

    def watcher_writer(parent, serialized):
        assert effective_uid != 0, 'root must never write into watcher-owned state'
        assert parent == paths.varlib / 'system'
        calls.append('watcher-private-fd')
        return root / 'check-synthetic.json'

    monkeypatch.setattr(hermes_updates, 'SafeFS', FakeSafeFS)
    monkeypatch.setattr(hermes_updates, '_write_watcher_receipt', watcher_writer)
    result = record(paths)
    assert Path(result['receipt']).parent == root
    assert calls == ['root-safe-fs' if effective_uid == 0 else 'watcher-private-fd']
