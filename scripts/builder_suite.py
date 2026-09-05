#!/usr/bin/env python3
"""Deterministic, non-privileged Builder suite snapshots; no runtime installation."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile

REPOSITORY = "https://github.com/agentik-os/agentik-station.git"
PACKAGES = ("builder", "librarian", "stepper")
GENERATOR = "scripts/builder_suite.py"
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


class SuiteError(ValueError):
    pass


def encoded(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_json(data: bytes) -> dict:
    value = json.loads(data)
    if not isinstance(value, dict):
        raise SuiteError("Suite metadata must be a JSON object")
    return value


def relative(name: str) -> str:
    if (not isinstance(name, str) or not name or "\\" in name or "\0" in name
            or name != str(PurePosixPath(name)) or name.startswith("/")
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise SuiteError("Invalid suite-relative path")
    return name


def public_source(name: str) -> None:
    relative(name)
    forbidden = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
                 "auth.json", "sessions.json", "state.db", ".DS_Store"}
    if any(part in forbidden or part == ".env" or part.startswith(".env.")
           or part.endswith((".pyc", ".pyo")) for part in name.split("/")):
        raise SuiteError("Private or generated runtime material is not a suite source")


def git(station: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(station), *args], capture_output=True,
                            check=False, timeout=60)
    if result.returncode:
        raise SuiteError("Cannot read the requested committed Station source")
    if len(result.stdout) > MAX_TOTAL:
        raise SuiteError("Committed source exceeds the suite size limit")
    return result.stdout


def committed_source(station: Path, ref: str) -> dict[str, tuple[bytes, int]]:
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise SuiteError("Source ref must be a complete lowercase immutable Git commit")
    actual = git(station, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
    if actual != ref:
        raise SuiteError("Source ref is not the exact commit")
    prefixes = tuple(f"os/{package}/" for package in PACKAGES)
    requested = [*(f"os/{package}" for package in PACKAGES), "os/CATALOG.json", "VERSION", GENERATOR]
    # Git archive attributes can omit files. Compare its exact regular inventory
    # to ls-tree, which also rejects symlinks/submodules before any materialization.
    expected = {}
    for row in git(station, "ls-tree", "-rz", ref, "--", *requested).split(b"\0"):
        if not row:
            continue
        meta, raw_name = row.split(b"\t", 1)
        mode, kind, object_id = meta.decode("ascii").split()
        name = raw_name.decode("utf8")
        public_source(name)
        if (mode not in {"100644", "100755"} or kind != "blob"
                or not (name.startswith(prefixes) or name in requested)):
            raise SuiteError("Committed suite source contains an unsupported entry")
        expected[name] = (int(mode[-3:], 8), object_id)
    result = {}
    archive = git(station, "archive", "--format=tar", ref, "--", *requested)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar:
            name = member.name.rstrip("/") if member.isdir() else member.name
            relative(name)
            if member.isdir():
                continue
            if (not member.isfile() or name not in expected or name in result
                    or not 0 <= member.size <= MAX_FILE):
                raise SuiteError("Unsafe or unexpected archive entry")
            stream = tar.extractfile(member)
            if stream is None:
                raise SuiteError("Unreadable archive entry")
            data = stream.read(MAX_FILE + 1)
            if len(data) != member.size:
                raise SuiteError("Incomplete archive entry")
            blob_hash = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob_hash != expected[name][1]:
                raise SuiteError("Archive attributes changed committed source bytes")
            result[name] = (data, expected[name][0])
    if set(result) != set(expected) or sum(len(v[0]) for v in result.values()) > MAX_TOTAL:
        raise SuiteError("Incomplete or oversized source inventory")
    return result


def package_records(files: dict[str, tuple[bytes, int]]) -> list[dict]:
    catalog = object_json(files["os/CATALOG.json"][0])
    entries = catalog.get("packages")
    if not isinstance(entries, list) or any(not isinstance(row, dict) for row in entries):
        raise SuiteError("Catalog packages must be objects in a list")
    records = []
    for package in PACKAGES:
        path, os_id = f"os/{package}", f"{package}-os"
        matches = [row for row in entries if row.get("id") == os_id]
        contract = object_json(files[f"{path}/CONTRACT.json"][0])
        manifest = object_json(files[f"{path}/MANIFEST.json"][0])
        version = contract.get("version")
        if (len(matches) != 1 or matches[0].get("path") != path
                or not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", version)
                or contract.get("os_id") != os_id or manifest.get("id") != os_id
                or manifest.get("version") != version or matches[0].get("version") != version):
            raise SuiteError("Package catalog, contract and manifest disagree")
        if not isinstance(contract.get("nanoteam"), list):
            raise SuiteError("Package team must be a list")
        roles = [contract.get("nano_director"), *contract["nanoteam"]]
        if (any(not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", role) for role in roles)
                or len(set(roles)) != len(roles)):
            raise SuiteError("Invalid package team")
        records.append({"id": os_id, "path": path, "version": version,
                        "director": roles[0], "roles": roles, "profile_count": len(roles)})
    return records


def render(station: Path, ref: str) -> dict[str, tuple[bytes, int]]:
    source = committed_source(station, ref)
    if source[GENERATOR][0] != Path(__file__).read_bytes():
        raise SuiteError("Use the generator from the selected committed Station release")
    records = package_records(source)
    version = source["VERSION"][0].decode("ascii").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", version):
        raise SuiteError("Invalid Station version")
    payload = {name: value for name, value in source.items()
               if name.startswith(tuple(f"os/{package}/" for package in PACKAGES))}
    payload["verify.py"] = (source[GENERATOR][0], 0o644)
    payload["SUITE.json"] = (encoded({
        "schema_version": 1, "kind": "StationBuilderSuite", "source_repository": REPOSITORY,
        "source_commit": ref, "station_version": version, "packages": records,
        "canonical_source": "Station os/ only; this directory is generated",
        "claim": "SOURCE_SNAPSHOT_NOT_RUNTIME", "operational": False,
        "installation": "Use the pinned Station release; it supplies compiler and support dependencies",
    }), 0o644)
    table = "\n".join(f"| {row['id']} | {row['version']} | {row['profile_count']} |" for row in records)
    payload["README.md"] = ((
        "# Generated Station Builder Suite\n\n"
        f"Source: [{ref}]({REPOSITORY.removesuffix('.git')}/tree/{ref}), Station {version}.\n\n"
        "| Package | Version | Profiles |\n|---|---|---:|\n" + table + "\n\n"
        "Builder builds and verifies; Librarian researches; Stepper structures the work.\n"
        "All three complete canonical source trees are included. Their instances and\n"
        "accounts stay separate. This is not a native Hermes profile distribution,\n"
        "a second editable source, a running team, or an authenticated integration.\n\n"
        "From the parent repository:\n\n```sh\n"
        "python3 station-suite/verify.py verify --suite station-suite\n```\n\n"
        "For source-provenance comparison add `--station /path/to/agentik-station`;\n"
        "the checkout must contain the exact recorded commit. `--check-current` also\n"
        "compares the three packages with that checkout's HEAD. No network fetch is\n"
        "performed. Hashes detect drift, not a maliciously replaced verifier/manifest.\n\n"
        "Install through the pinned Station release, which includes the compiler,\n"
        "shared skills, policy, web plugins and resources absent from this source-only\n"
        "snapshot. Existing installations must compare their active source and trusted\n"
        "instance versions; do not replace profiles or copy credentials to clear drift.\n"
        "Submit changes to Station's os/ sources, then regenerate the whole suite.\n"
        "Preserve each package's provenance and licensing limitations.\n"
    ).encode(), 0o644)
    payload["MANIFEST.json"] = (encoded({"schema_version": 1, "files": {
        name: {"sha256": digest(data), "size": len(data), "mode": mode}
        for name, (data, mode) in sorted(payload.items())
    }}), 0o644)
    return payload


def inventory(root: Path) -> dict[str, tuple[bytes, int]]:
    """Read through anchored directory FDs; never follow a payload symlink."""
    result: dict[str, tuple[bytes, int]] = {}
    total = 0

    def walk(fd: int, prefix: str) -> None:
        nonlocal total
        entries = sorted(os.listdir(fd))
        if prefix and not entries:
            raise SuiteError("Unexpected empty suite directory")
        for name in entries:
            path = relative(prefix + name)
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(before.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    walk(child, path + "/")
                finally:
                    os.close(child)
            else:
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE:
                    raise SuiteError("Suite payload must contain bounded regular single-link files")
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    info = os.fstat(child)
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)):
                        raise SuiteError("Suite file changed during inspection")
                    data = b""
                    while len(data) <= MAX_FILE:
                        chunk = os.read(child, min(65536, MAX_FILE + 1 - len(data)))
                        if not chunk:
                            break
                        data += chunk
                    after = os.fstat(child)
                    if (len(data) != info.st_size or len(data) > MAX_FILE
                            or after.st_mtime_ns != info.st_mtime_ns or after.st_size != info.st_size):
                        raise SuiteError("Suite file changed or exceeds limits")
                    total += len(data)
                    if total > MAX_TOTAL:
                        raise SuiteError("Suite exceeds size limit")
                    result[path] = data, stat.S_IMODE(info.st_mode)
                finally:
                    os.close(child)

    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        walk(fd, "")
    finally:
        os.close(fd)
    return result


def verify(suite: Path, station: Path | None = None, check_current: bool = False) -> dict:
    files = inventory(suite)
    manifest = object_json(files["MANIFEST.json"][0])
    if set(manifest) != {"schema_version", "files"} or manifest["schema_version"] != 1:
        raise SuiteError("Unsupported suite inventory")
    rows = manifest["files"]
    if not isinstance(rows, dict) or set(rows) != set(files) - {"MANIFEST.json"}:
        raise SuiteError("Suite inventory has missing or unexpected files")
    for name, row in rows.items():
        relative(name)
        data, mode = files[name]
        if row != {"sha256": digest(data), "size": len(data), "mode": mode} or mode not in {0o644, 0o755}:
            raise SuiteError("Suite file hash, size or mode differs from manifest")
    if files["MANIFEST.json"][1] != 0o644:
        raise SuiteError("Unexpected manifest mode")
    meta = object_json(files["SUITE.json"][0])
    if (meta.get("schema_version") != 1 or meta.get("kind") != "StationBuilderSuite"
            or meta.get("source_repository") != REPOSITORY
            or not re.fullmatch(r"[0-9a-f]{40}", str(meta.get("source_commit", "")))
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", str(meta.get("station_version", "")))
            or meta.get("claim") != "SOURCE_SNAPSHOT_NOT_RUNTIME" or meta.get("operational") is not False):
        raise SuiteError("Invalid suite source or readiness metadata")
    catalog = {"packages": [{"id": f"{package}-os", "path": f"os/{package}",
                             "version": object_json(files[f"os/{package}/CONTRACT.json"][0])["version"]}
                            for package in PACKAGES]}
    records = package_records({**files, "os/CATALOG.json": (encoded(catalog), 0o644)})
    if meta.get("packages") != records:
        raise SuiteError("Suite packages disagree with source contracts")
    allowed = {"SUITE.json", "MANIFEST.json", "README.md", "verify.py"}
    for name in files:
        if name not in allowed and not name.startswith(tuple(f"os/{package}/" for package in PACKAGES)):
            raise SuiteError("Unexpected suite payload scope")
        public_source(name)
    if check_current and station is None:
        raise SuiteError("Current-source comparison requires an explicit Station checkout")
    if station is not None:
        expected = render(station, meta["source_commit"])
        if files != expected:
            raise SuiteError("Suite differs from its pinned Station commit")
        if check_current:
            head = git(station, "rev-parse", "HEAD").decode().strip()
            current = committed_source(station, head)
            selected = {name: value for name, value in current.items()
                        if name.startswith(tuple(f"os/{package}/" for package in PACKAGES))}
            observed = {name: value for name, value in files.items()
                        if name.startswith(tuple(f"os/{package}/" for package in PACKAGES))}
            if selected != observed or package_records(current) != records:
                raise SuiteError("Canonical OS packages changed; regenerate and review the complete suite")
    return {"ok": True, "claim": meta["claim"], "source_commit": meta["source_commit"],
            "station_version": meta["station_version"], "packages": records, "files": len(files),
            "source_compared": station is not None, "current_packages_compared": check_current,
            "operational": False}


def export(station: Path, ref: str, output: Path) -> dict:
    if os.geteuid() == 0:
        raise SuiteError("Generate publications as a non-root repository owner")
    payload = render(station, ref)
    if output.exists() or output.is_symlink():
        if inventory(output) != payload:
            raise SuiteError("Destination differs; generate a new directory and review the update, never overwrite")
        return verify(output, station)
    # Reserve privately even under a permissive umask. Every descendant write is
    # relative to retained no-follow directory FDs, not a reconstructed path.
    # Failure retains the exact partial destination for review; never delete it.
    parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directories: dict[str, int] = {}
    try:
        relative(output.name)
        os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        root_fd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        directories[""] = root_fd
        for name, (data, mode) in sorted(payload.items()):
            parts, prefix, directory_fd = relative(name).split("/"), "", root_fd
            for part in parts[:-1]:
                current = prefix + part
                if current not in directories:
                    os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                    directories[current] = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                                   dir_fd=directory_fd)
                directory_fd, prefix = directories[current], current + "/"
            fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         mode, dir_fd=directory_fd)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
        for directory_fd in reversed(list(directories.values())):
            os.fchmod(directory_fd, 0o755)
            os.fsync(directory_fd)
    finally:
        for directory_fd in directories.values():
            os.close(directory_fd)
        os.close(parent_fd)
    return verify(output, station)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("export")
    create.add_argument("--station", type=Path, required=True)
    create.add_argument("--source-ref", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--suite", type=Path, required=True)
    check.add_argument("--station", type=Path)
    check.add_argument("--check-current", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = (export(args.station, args.source_ref, args.output) if args.command == "export"
                  else verify(args.suite, args.station, args.check_current))
    except (SuiteError, OSError, KeyError, TypeError, UnicodeError, ValueError,
            tarfile.TarError, subprocess.SubprocessError) as exc:
        # No native tool output, credentials or file contents in error messages.
        print(json.dumps({"ok": False, "error": str(exc) if isinstance(exc, SuiteError)
                          else "Invalid or inaccessible suite/source"}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
