from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentik_station.errors import SecurityError
from agentik_station.filesystem import SafeFS


def test_managed_write_cannot_escape_allowed_root(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    fs = SafeFS([root])
    with pytest.raises(SecurityError):
        fs.write_text(tmp_path / "outside.txt", "blocked")


def test_managed_write_refuses_symlink_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    fs = SafeFS([root])
    with pytest.raises(SecurityError):
        fs.write_text(root / "link" / "victim.txt", "pwned")
    assert not (outside / "victim.txt").exists()


def test_managed_write_refuses_symlink_destination(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("safe")
    (root / "target.txt").symlink_to(outside)
    fs = SafeFS([root])
    with pytest.raises(SecurityError):
        fs.write_text(root / "target.txt", "pwned")
    assert outside.read_text() == "safe"


def test_atomic_write_sets_expected_mode(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    fs = SafeFS([root])
    target = fs.write_text(root / "credentials" / "secret.ref", "reference-only", 0o600)
    assert target.read_text() == "reference-only"
    assert (os.lstat(target).st_mode & 0o777) == 0o600
    assert not list(target.parent.glob(f".{target.name}.tmp-*"))


def test_rollback_restores_replaced_files_and_removes_created_files(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    existing = root / "existing.txt"
    existing.write_text("before")
    fs = SafeFS([root])
    fs.write_text(existing, "after", 0o640)
    created = fs.write_text(root / "new.txt", "new")
    fs.rollback()
    assert existing.read_text() == "before"
    assert not created.exists()
