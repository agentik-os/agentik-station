from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from typing import Any
from ..errors import ValidationError, SecurityError

def plan_backup(zone_id: str, source_roots: list[Path], repository_file: Path, password_file: Path) -> dict[str, Any]:
    if not repository_file.is_absolute() or not password_file.is_absolute():
        raise ValidationError("Restic credential references must be absolute paths")
    for p in [repository_file,password_file]:
        if p.is_symlink() or not p.is_file():
            raise SecurityError(f"Backup credential reference must be a regular non-symlink file: {p}")
    return {
        "zone_id":zone_id,
        "provider":"restic",
        "source_roots":[str(Path(p)) for p in source_roots],
        "repository_file":str(repository_file),
        "password_file":str(password_file),
        "claim":"PLAN_NOT_RUN",
    }

def run_backup(plan: dict[str, Any]) -> dict[str, Any]:
    binary=shutil.which("restic")
    if not binary:
        raise RuntimeError("restic is required for encrypted off-Host backup")
    argv=[binary,"backup","--repository-file",plan["repository_file"],"--password-file",plan["password_file"],*plan["source_roots"],"--json"]
    completed=subprocess.run(argv,capture_output=True,text=True,check=False,timeout=3600)
    return {"state":"REPORTED_DONE" if completed.returncode==0 else "DEGRADED","returncode":completed.returncode,
            "stdout":completed.stdout[-12000:],"stderr":completed.stderr[-12000:],"verified":False,
            "next_repair_action":"Run restic check and a destructive restore rehearsal before declaring recovery verified."}

def check_repository(repository_file: Path,password_file: Path) -> dict[str,Any]:
    binary=shutil.which("restic")
    if not binary:
        return {"state":"NOT_INSTALLED","verified":False}
    completed=subprocess.run([binary,"check","--repository-file",str(repository_file),"--password-file",str(password_file)],
                             capture_output=True,text=True,check=False,timeout=1800)
    return {"state":"VERIFIED" if completed.returncode==0 else "DEGRADED","verified":completed.returncode==0,
            "stdout":completed.stdout[-8000:],"stderr":completed.stderr[-8000:]}


def restore_to_staging(plan: dict[str, Any], target: Path, snapshot: str = "latest") -> dict[str, Any]:
    """Restore a snapshot into a clean staging directory for recovery rehearsal.

    This never restores over a live Zone. Promotion back into a live Zone remains
    a separate, operator-controlled recovery step after Doctor/readback.
    """
    binary = shutil.which("restic")
    if not binary:
        raise RuntimeError("restic is required for restore rehearsal")
    target = Path(target)
    if not target.is_absolute():
        raise ValidationError("restore staging target must be absolute")
    if target.is_symlink():
        raise SecurityError(f"Restore target may not be a symlink: {target}")
    if target.exists() and any(target.iterdir()):
        raise SecurityError(f"Restore staging target must be empty: {target}")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    argv = [
        binary,
        "restore",
        snapshot,
        "--repository-file",
        plan["repository_file"],
        "--password-file",
        plan["password_file"],
        "--target",
        str(target),
    ]
    completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=3600)
    return {
        "state": "RESTORED_TO_STAGING" if completed.returncode == 0 else "DEGRADED",
        "returncode": completed.returncode,
        "target": str(target),
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "verified": False,
        "accepted": False,
        "next_repair_action": (
            "Run Station/OS Doctor and a fresh-session/readback acceptance against the restored staging state before any live promotion."
            if completed.returncode == 0
            else "Repair the restore failure and rerun the staging rehearsal."
        ),
    }
