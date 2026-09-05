from dataclasses import replace
from pathlib import Path
import os
import stat
import tempfile

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
