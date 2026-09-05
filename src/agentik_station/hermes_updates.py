"""Account-free Hermes update planning, including non-Git immutable installs."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import pwd
from pathlib import Path
import re
import stat
from typing import Any
from uuid import uuid4

from .filesystem import SafeFS
from .errors import ValidationError
from .paths import LayoutPaths
from .updates import fetch_metadata, GATES


def _read(path: Path, limit: int = 512 * 1024) -> str:
    # Read metadata as data only; never import Hermes or execute local hooks.
    current = path.parent
    while current != current.parent:
        if current.is_symlink(): raise ValueError('Linked metadata parent')
        current = current.parent
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit: raise ValueError('Invalid metadata')
        return os.read(fd, limit + 1).decode('utf-8')
    finally:
        os.close(fd)


def source_observation(root: Path) -> dict[str, Any]:
    if not root.exists(): return {'state': 'NOT_INSTALLED', 'distribution': None, 'commit': None}
    try:
        anchor = root.parent.absolute()
        for parent in [anchor, *anchor.parents]:
            if parent.is_symlink(): raise ValueError('Linked source parent')
        root = root.resolve(strict=True)
        if not root.is_relative_to(anchor): raise ValueError('Source escapes Hermes software root')
        if not root.is_dir() or not (root / 'pyproject.toml').is_file(): raise ValueError('Unknown runtime')
        if not (root / '.git').is_dir():
            # No Git metadata is a supported installation shape, not an updater error.
            # Never invent provenance from the Station target pin or a version string.
            return {'state': 'SOURCE_PRESENT_PROVENANCE_NOT_VERIFIED', 'distribution': 'immutable-or-tarball', 'commit': None}
        head = _read(root / '.git/HEAD', 512).strip()
        if head.startswith('ref: '):
            ref = head[5:]
            if not re.fullmatch(r'refs/[A-Za-z0-9_./-]+', ref) or any(p in {'.', '..'} for p in Path(ref).parts): raise ValueError('Invalid Git ref')
            head = _read(root / '.git' / ref, 512).strip()
        if not re.fullmatch(r'[a-f0-9]{40}', head): raise ValueError('Invalid Git identity')
        return {'state': 'SOURCE_ID_OBSERVED_NOT_CONTENT_VERIFIED', 'distribution': 'git', 'commit': head}
    except (OSError, ValueError, UnicodeError):
        return {'state': 'SOURCE_PROVENANCE_NOT_VERIFIED', 'distribution': 'unknown', 'commit': None}


def run_check(paths: LayoutPaths, *, record: bool = False, fetch=fetch_metadata) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[2]
    pins = dict(line.split('=', 1) for line in (repo / 'config/versions.lock').read_text().splitlines()
                if re.fullmatch(r'[A-Z0-9_]+=[^\s]+', line))
    observed = source_observation(paths.software / 'tools/hermes/current')
    upstream = fetch('github', 'NousResearch/hermes-agent')
    payload = {'schema_version': 2, 'checked_at': datetime.now(timezone.utc).isoformat(),
               'status': 'PLAN_READY' if upstream['status'] == 'OBSERVED_NOT_ACCEPTED' else 'DISCOVERY_INCOMPLETE',
               'source': observed, 'reviewed': {'release': pins['HERMES_RELEASE'], 'commit': pins['HERMES_COMMIT']},
               'upstream': upstream, 'claim': 'OBSERVED_UPDATE_PLAN_NOT_APPLIED', 'commands': [],
               'applied': False, 'promoted': False, 'account_accessed': False, 'gates': GATES,
               'next_repair_action': 'Review the full Station dependency inventory and native compatibility gates; deploy a new immutable release, never independently pull Hermes into a live profile.'}
    if record:
        if not paths.test_mode and os.geteuid() != 0 and pwd.getpwuid(os.geteuid()).pw_name != 'station-system':
            raise ValidationError('--record requires root or the Station watcher identity')
        root = (paths.varlib / 'hermes-updates' if paths.test_mode or os.geteuid() == 0
                else paths.varlib / 'system/hermes-updates')
        fixture_anchor = None
        if paths.test_mode:
            if len(paths.varlib.parents) < 3:
                raise ValidationError('Invalid update evidence test layout')
            fixture_anchor = paths.varlib.parents[2]
            if fixture_anchor == Path(fixture_anchor.anchor) or LayoutPaths.under(fixture_anchor) != paths:
                raise ValidationError('Invalid update evidence test layout')
        fs = SafeFS(paths.allowed_roots)
        # Do not write through station-system-owned /var/lib/station/system as root.
        for parent in [root, *root.parents]:
            if parent.exists():
                info = parent.lstat()
                expected = os.getuid()
                # A validated synthetic fixture may live below root-owned /tmp.
                # Its own anchor and every managed descendant remain strict;
                # live paths never receive this sticky-directory exception.
                external_sticky = (
                    fixture_anchor is not None and parent in fixture_anchor.parents
                    and stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                    and bool(info.st_mode & stat.S_ISVTX)
                )
                if (stat.S_ISLNK(info.st_mode) or info.st_uid not in {0, expected}
                        or (info.st_mode & 0o022 and not external_sticky)):
                    raise ValidationError('Unsafe update evidence ancestry')
        fs.mkdir(root, 0o700)
        target = root / f'check-{uuid4().hex}.json'
        fs.write_text(target, json.dumps(payload, indent=2) + '\n', 0o600)
        payload['receipt'] = str(target)
    return payload
