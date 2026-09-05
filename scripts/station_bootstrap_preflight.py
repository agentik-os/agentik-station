#!/usr/bin/env python3
"""Read-only bootstrap eligibility checks; never reconcile or repair a Host."""

from __future__ import annotations

import grp
import filecmp
import platform
import pwd
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentik_station.errors import StationError, ValidationError
from agentik_station.installer import validate_supported_host
from agentik_station.paths import LayoutPaths
from agentik_station.constants import REPO_EXCLUDES


def check_directory_chain(path: Path) -> None:
    """Refuse links or non-directories before later shell installers touch them."""
    for parent in reversed((path, *path.parents)):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise ValidationError(f"Bootstrap target must be a real directory: {parent}")


def check_operator(home: Path) -> None:
    try:
        account = pwd.getpwnam("agk-station")
    except KeyError:
        try:
            grp.getgrnam("agk-station")
        except KeyError:
            return
        raise ValidationError("Existing agk-station group has no matching account; inspect before bootstrap")
    try:
        group = grp.getgrnam("agk-station")
    except KeyError as exc:
        raise ValidationError("Existing operator has no matching agk-station group") from exc
    if account.pw_uid == 0 or group.gr_gid == 0 or account.pw_gid != group.gr_gid or account.pw_dir != str(home):
        raise ValidationError("Existing agk-station identity/home/group conflicts with bootstrap; no automatic repair")
    if home.exists() and home.stat().st_uid != account.pw_uid:
        raise ValidationError("Existing operator home has unexpected ownership; inspect before bootstrap")


def check_existing_targets(repo: Path, home: Path, releases: Path) -> None:
    destination = home / "repos" / "agentik-station"
    check_directory_chain(destination)
    check_directory_chain(releases)
    check_directory_chain(home / ".local" / "bin")
    check_directory_chain(home / ".local" / "share")
    check_directory_chain(home / ".local" / "lib")
    check_directory_chain(home / ".config")
    check_directory_chain(releases.parent / "tools" / "hermes" / "current")
    check_directory_chain(releases.parent / "tools" / "hermes" / "python" / "bin")
    profile = home / ".profile"
    if profile.is_symlink() or (profile.exists() and not stat.S_ISREG(profile.lstat().st_mode)):
        raise ValidationError("Operator .profile must be a regular file, not a link or special file")
    check_operator(home)
    if destination.exists() and destination.resolve() != repo.resolve() and any(destination.iterdir()):
        raise ValidationError(
            "Operator checkout already exists; preserve its work and run bootstrap from that checkout. "
            "A different checkout will not be rsynced over it."
        )
    version = (repo / "VERSION").read_text().strip()
    # The repository's normal Doctor validates this too; do not trust path text.
    from agentik_station.identifiers import validate_version

    validate_version(version)
    published = releases / version
    check_directory_chain(published)
    if published.exists():
        provenance = published / "RELEASE_PROVENANCE.json"
        try:
            info = provenance.lstat()
        except FileNotFoundError as exc:
            raise ValidationError("Existing immutable release has no provenance; inspect before bootstrap") from exc
        if not stat.S_ISREG(info.st_mode) or provenance.read_bytes() != (repo / "RELEASE_PROVENANCE.json").read_bytes():
            raise ValidationError("Same-version immutable release differs; choose a reviewed new release/migration")
        if not release_matches(repo, published):
            raise ValidationError("Same-version immutable release content differs; inspect drift before bootstrap")


def release_matches(source: Path, published: Path) -> bool:
    """Compare the kernel's publishable tree without staging or following links."""
    expected = {p.name: p for p in source.iterdir() if p.name not in REPO_EXCLUDES and not p.name.endswith(".pyc")}
    actual = {p.name: p for p in published.iterdir()}
    if expected.keys() != actual.keys():
        return False
    for name, left in expected.items():
        right = actual[name]
        a, b = left.lstat(), right.lstat()
        if stat.S_ISDIR(a.st_mode) and stat.S_ISDIR(b.st_mode):
            if not release_matches(left, right):
                return False
        elif stat.S_ISREG(a.st_mode) and stat.S_ISREG(b.st_mode):
            if not filecmp.cmp(left, right, shallow=False):
                return False
        else:
            return False
    return True


def main() -> int:
    try:
        validate_supported_host(LayoutPaths.live())
        if platform.machine() not in {"x86_64", "aarch64"}:
            raise ValidationError("Bootstrap toolchain requires Linux x86_64 or aarch64")
        check_existing_targets(ROOT, Path("/home/agk-station"), Path("/opt/station/releases"))
    except (StationError, OSError) as exc:
        print(f"BOOTSTRAP_PREFLIGHT_FAILED: {exc}", file=sys.stderr)
        return 2
    print("BOOTSTRAP_PREFLIGHT_OK: supported Host and existing targets checked; no Host changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
