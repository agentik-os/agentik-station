from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .constants import REPO_EXCLUDES
from .errors import ReconcileError, SecurityError
from .identifiers import RemoteTarget, validate_remote_target
from .models import InstallSpec


def _ssh_options(target: RemoteTarget, *, accept_new_host_key: bool) -> list[str]:
    policy = "accept-new" if accept_new_host_key else "yes"
    return [
        "-p",
        str(target.port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"StrictHostKeyChecking={policy}",
        "-o",
        "ConnectTimeout=15",
    ]


def _require_commands(names: Iterable[str]) -> None:
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise ReconcileError(f"Remote bootstrap requires local command(s): {', '.join(missing)}")


def _iter_release_paths(repo: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(repo, topdown=True, followlinks=False):
        current_path = Path(current)
        filtered_dirs: list[str] = []
        for name in sorted(dirs):
            if name in REPO_EXCLUDES or name.endswith(".egg-info"):
                continue
            path = current_path / name
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise SecurityError(f"Unsupported path in remote release: {path}")
            filtered_dirs.append(name)
        dirs[:] = filtered_dirs
        yield current_path
        for name in sorted(files):
            if name in REPO_EXCLUDES or name.endswith(".pyc"):
                continue
            path = current_path / name
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise SecurityError(f"Unsupported file in remote release: {path}")
            yield path


def create_release_tar(repo: Path, destination: Path) -> Path:
    repo = Path(repo).absolute()
    st = os.lstat(repo)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise SecurityError(f"Repository root must be a real directory: {repo}")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise SecurityError(f"Remote release archive destination already exists: {destination}")

    with tarfile.open(destination, mode="w") as archive:
        for path in _iter_release_paths(repo):
            relative = path.relative_to(repo)
            arcname = Path("agentik-station") / relative
            info = archive.gettarinfo(str(path), arcname=str(arcname))
            # Release archives never preserve local owners or writable group bits.
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = 0
            if info.isdir():
                info.mode = 0o755
                archive.addfile(info)
            elif info.isfile():
                info.mode = 0o755 if (info.mode & 0o111) else 0o644
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    with os.fdopen(fd, "rb", closefd=True) as source:
                        archive.addfile(info, source)
                except Exception:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    raise
            else:
                raise SecurityError(f"Special files are forbidden in a remote release: {path}")
    return destination


def build_remote_plan(
    target_value: str,
    port: int,
    spec: InstallSpec,
    *,
    accept_new_host_key: bool = False,
) -> dict[str, Any]:
    target = validate_remote_target(target_value, port)
    base = f"/tmp/agentik-station-{spec.operation_id}"
    remote_archive = f"{base}/release.tar"
    remote_spec = f"{base}/install-spec.json"
    remote_repo = f"{base}/agentik-station"
    options = _ssh_options(target, accept_new_host_key=accept_new_host_key)
    ssh = ["ssh", *options, target.destination]
    scp = ["scp", "-P", str(target.port), "-o", "BatchMode=yes", "-o", f"StrictHostKeyChecking={'accept-new' if accept_new_host_key else 'yes'}"]
    commands = [
        [*ssh, "/usr/bin/install", "-d", "-m", "0700", "--", base],
        [*scp, "<release.tar>", f"{target.destination}:{remote_archive}"],
        [*scp, "<install-spec.json>", f"{target.destination}:{remote_spec}"],
        [*ssh, "/usr/bin/tar", "--no-same-owner", "--no-same-permissions", "-xf", remote_archive, "-C", base],
        [
            *ssh,
            "/usr/bin/sudo",
            "/usr/bin/python3",
            f"{remote_repo}/installer/install_station.py",
            "--spec",
            remote_spec,
            "--non-interactive",
        ],
        [*ssh, "/usr/bin/sudo", "/usr/local/bin/station", "status", "--json"],
    ]
    return {
        "schema_version": 1,
        "state": "PLAN_READY",
        "claim": "BOOTSTRAP_TRANSPORT_ONLY",
        "target": target.destination,
        "port": target.port,
        "strict_host_key_checking": "accept-new" if accept_new_host_key else "yes",
        "remote_staging": base,
        "spec": spec.to_dict(),
        "commands": commands,
        "next_repair_action": (
            "After bootstrap, inspect the remote receipt and Doctor output. Fleet reconciliation, drift detection, "
            "remote rollback, and Tailscale identity attestation remain separate gates."
        ),
    }


def remote_bootstrap(
    repo: Path,
    target_value: str,
    port: int,
    spec: InstallSpec,
    *,
    accept_new_host_key: bool = False,
    plan_only: bool = False,
) -> dict[str, Any]:
    plan = build_remote_plan(
        target_value,
        port,
        spec,
        accept_new_host_key=accept_new_host_key,
    )
    if plan_only:
        return plan

    _require_commands(["ssh", "scp"])
    target = validate_remote_target(target_value, port)
    options = _ssh_options(target, accept_new_host_key=accept_new_host_key)
    ssh = ["ssh", *options, target.destination]
    scp = ["scp", "-P", str(target.port), "-o", "BatchMode=yes", "-o", f"StrictHostKeyChecking={'accept-new' if accept_new_host_key else 'yes'}"]
    base = str(plan["remote_staging"])
    remote_archive = f"{base}/release.tar"
    remote_spec = f"{base}/install-spec.json"
    remote_repo = f"{base}/agentik-station"

    outputs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="agentik-station-remote-") as temp_dir:
        temp = Path(temp_dir)
        archive_path = create_release_tar(repo, temp / "release.tar")
        spec_path = temp / "install-spec.json"
        spec.write(spec_path)
        commands = [
            [*ssh, "/usr/bin/install", "-d", "-m", "0700", "--", base],
            [*scp, str(archive_path), f"{target.destination}:{remote_archive}"],
            [*scp, str(spec_path), f"{target.destination}:{remote_spec}"],
            [*ssh, "/usr/bin/tar", "--no-same-owner", "--no-same-permissions", "-xf", remote_archive, "-C", base],
            [
                *ssh,
                "/usr/bin/sudo",
                "/usr/bin/python3",
                f"{remote_repo}/installer/install_station.py",
                "--spec",
                remote_spec,
                "--non-interactive",
            ],
            [*ssh, "/usr/bin/sudo", "/usr/local/bin/station", "status", "--json"],
        ]
        for argv in commands:
            completed = subprocess.run(argv, check=True, capture_output=True, text=True)
            outputs.append(
                {
                    "argv": argv[1:],
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout[-8000:],
                    "stderr": completed.stderr[-8000:],
                }
            )

    result = dict(plan)
    result.update(
        {
            "state": "REMOTE_APPLY_REPORTED",
            "outputs": outputs,
            "verified": False,
            "accepted": False,
        }
    )
    return result
