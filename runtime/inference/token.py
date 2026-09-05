#!/usr/bin/python3
"""Zone-local inference capability; never reads the source provider credential."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import secrets
import stat
import sys


ZONE_HOME = re.compile(r"/var/lib/station/zones/([a-z0-9][a-z0-9-]{0,62})/home\Z")
TOKEN = re.compile(rb"[0-9a-f]{64}\n?\Z")


class TokenError(Exception):
    """A deliberately non-secret capability error."""


def _open_directory(path: str, uid: int) -> int:
    """Walk from /, retaining nofollow descriptors across every component."""
    traverse = getattr(os, 'O_PATH', os.O_RDONLY)
    fd = os.open("/", traverse | os.O_DIRECTORY)
    try:
        parts = path.strip("/").split("/")
        for index, part in enumerate(parts):
            # Canonical Station parents are execute-only (0711) to Zone users.
            # Only our own final directory needs a readable/fsync-capable FD.
            access = os.O_RDONLY if index == len(parts) - 1 else traverse
            child = os.open(part, access | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            if st.st_uid not in (0, uid) or stat.S_IMODE(st.st_mode) & 0o022:
                raise TokenError("Unsafe Zone directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def capability(mode: str = "read") -> str | dict:
    uid = os.geteuid()
    if uid == 0 or os.getuid() != uid:
        raise TokenError("Run as the owning Zone identity")
    account = pwd.getpwuid(uid)
    match = ZONE_HOME.fullmatch(account.pw_dir)
    if not match:
        raise TokenError("The account is not a canonical Zone identity")
    zone_id = match.group(1)
    state_fd = _open_directory(account.pw_dir.removesuffix("/home"), uid)
    access_fd = None
    try:
        state = os.fstat(state_fd)
        if state.st_uid != uid or stat.S_IMODE(state.st_mode) != 0o700:
            raise TokenError("Unsafe Zone state root")
        if mode == "create":
            # An existing directory/token is never silently adopted or replaced.
            os.mkdir("model-access", 0o700, dir_fd=state_fd)
        access_fd = os.open("model-access", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=state_fd)
        access = os.fstat(access_fd)
        if access.st_uid != uid or stat.S_IMODE(access.st_mode) != 0o700:
            raise TokenError("Unsafe capability directory")
        if mode == "create":
            token = secrets.token_hex(32).encode("ascii")
            fd = os.open("token", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=access_fd)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(token + b"\n")
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(access_fd)
            os.fsync(state_fd)
        fd = os.open("token", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=access_fd)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != uid
                    or stat.S_IMODE(st.st_mode) != 0o600 or st.st_size not in (64, 65)):
                raise TokenError("Unsafe capability token")
            token = os.read(fd, 66)
            if not TOKEN.fullmatch(token):
                raise TokenError("Malformed capability token")
            token = token.rstrip(b"\n")
        finally:
            os.close(fd)
        if mode == "read":
            return token.decode("ascii")
        return {"schema_version": 1, "zone_id": zone_id, "uid": uid,
                "token_sha256": hashlib.sha256(token).hexdigest()}
    finally:
        if access_fd is not None:
            os.close(access_fd)
        os.close(state_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--create", action="store_true")
    modes.add_argument("--digest", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = capability("create" if args.create else "digest" if args.digest else "read")
    except (OSError, KeyError, TokenError):
        print("Station inference capability unavailable for this Zone", file=sys.stderr)
        return 1
    print(result if isinstance(result, str) else json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
