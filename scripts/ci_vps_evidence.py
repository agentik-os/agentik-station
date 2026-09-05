#!/usr/bin/env python3
"""Bounded observed-host evidence with atomic, no-overwrite publication.

This helper does not run acceptance checks. The shell entry point calls publish
only after every existing gate succeeds. Output is restricted to named acceptance
artifacts directly under /tmp; arbitrary root-owned paths are never destinations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

OUTPUT_ROOT = Path("/tmp")
OUTPUT_NAME = re.compile(r"station-vps-acceptance(?:\.[a-z0-9][a-z0-9-]{0,63})?\.json\Z")


@contextmanager
def _output_directory(output: Path) -> Iterator[int]:
    if output.parent != OUTPUT_ROOT or not OUTPUT_NAME.fullmatch(output.name):
        raise ValueError("Evidence must be /tmp/station-vps-acceptance[.<safe-id>].json")
    # /tmp may itself be a platform-owned symlink (macOS). Open its resolved
    # standard location; callers cannot supply another directory or traversal.
    root = OUTPUT_ROOT.resolve(strict=True) if sys.platform == "darwin" else OUTPUT_ROOT
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise ValueError("Evidence directory must be trusted or sticky and owned by the publishing identity")
        try:
            os.stat(output.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Evidence already exists; preserve it and select a new acceptance filename")
        yield fd
    finally:
        os.close(fd)


def validate_output(output: Path) -> None:
    with _output_directory(output):
        pass


def observed_host() -> dict[str, str]:
    release = platform.freedesktop_os_release()
    result = {
        "system": platform.system(),
        "distribution_id": release.get("ID", ""),
        "distribution_version_id": release.get("VERSION_ID", ""),
        "architecture": platform.machine(),
    }
    if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)
           for value in result.values()):
        raise ValueError("Cannot identify the observed OS/version/architecture safely")
    return result


def _doctor_bytes(path: Path) -> bytes:
    # The entry point puts this output in a root-created private mktemp directory.
    parent = path.parent
    if parent.parent != OUTPUT_ROOT or not re.fullmatch(r"station-vps-readback\.[A-Za-z0-9]{8,}", parent.name):
        raise ValueError("Doctor output must be in the private acceptance workspace")
    with_root = OUTPUT_ROOT.resolve(strict=True) if sys.platform == "darwin" else OUTPUT_ROOT
    root_fd = os.open(with_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory = os.open(parent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    finally:
        os.close(root_fd)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Acceptance workspace must be private and owned by the publishing identity")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_size > 4 * 1024 * 1024:
                raise ValueError("Unsafe or oversized Doctor output")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError("Oversized Doctor output")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def publish(output: Path, profile: str, doctor: Path) -> dict:
    if profile not in {"core", "full"}:
        raise ValueError("Invalid acceptance profile")
    host = observed_host()
    doctor_data = _doctor_bytes(doctor)
    payload = {
        "schema_version": 1,
        "environment": f"{host['distribution_id']}-{host['distribution_version_id']}",
        "observed_host": host,
        "profile": profile,
        "claim": "VERIFIED_INSTALL_READY_FOR_EXTERNAL_SETUP",
        "external_accounts_accepted": False,
        "checks": [
            "station-doctor-full",
            "real-zone-identity-traversal-and-cross-zone-denial",
            "devops-os-doctor",
            "agk-entrypoint",
            "pinned-toolchain-including-discord-js",
            "shared-zone-cli-pins-private-home-network-isolated",
            "hermes-update-timer",
            "scrapegraphai-crawl4ai-imports-and-chromium-launch",
            *(["parakeet-loopback-health"] if profile == "full" else []),
        ],
        "devops_doctor_sha256": hashlib.sha256(doctor_data).hexdigest(),
        "observed_unix_time": int(time.time()),
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    with _output_directory(output) as root_fd:
        # Stage under a private directory on the destination filesystem. link()
        # publishes the complete file atomically and refuses every existing leaf,
        # including a symlink swapped in after the earlier eligibility check.
        with tempfile.TemporaryDirectory(prefix="station-vps-publish.", dir=OUTPUT_ROOT) as workspace:
            temporary = Path(workspace) / "evidence.json"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fchmod(fd, 0o644)  # Non-secret CI artifact must be uploadable by the runner.
                    os.fsync(fd)
                os.link(temporary, output.name, dst_dir_fd=root_fd, follow_symlinks=False)
                os.fsync(root_fd)
            finally:
                os.close(fd)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-output", action="store_true")
    parser.add_argument("--profile", choices=["core", "full"])
    parser.add_argument("--doctor", type=Path)
    args = parser.parse_args()
    try:
        if args.check_output:
            validate_output(args.output)
        else:
            if args.profile is None or args.doctor is None:
                parser.error("publication requires --profile and --doctor")
            print(json.dumps(publish(args.output, args.profile, args.doctor), indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        # Do not relay file contents or captured native output.
        print(f"Acceptance evidence failed: {type(exc).__name__}; inspect destination/host metadata and preserve existing evidence.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
