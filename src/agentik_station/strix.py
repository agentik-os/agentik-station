"""Bounded local-source Strix adapter. Hermes owns the mission, not Strix.

No network targets, cloud mode, arbitrary flags, ambient MCP servers or automatic
authorization. Docker execution is restricted to an explicitly accepted disposable
LAB Host. Grants are time-limited, not a hard cumulative provider-spending limit.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import pwd
import re
import signal
import stat
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .errors import SecurityError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_identifier
from .os_runtime import require_root_owned_directory_chain

VERSION = "1.6.1"
RUNTIME = Path("/opt/station/tools/security/strix-1.6.1-py3.13.15")
IMAGES = {
    "x86_64": "ghcr.io/usestrix/strix-sandbox@sha256:e5e5d9927f15ca95ad49804ef7d22439771cd27378f400da6edd47556799baff",
    "aarch64": "ghcr.io/usestrix/strix-sandbox@sha256:38f9eea087079763312877eaf59047c3bd61ece67ab3479c1da63dc48fe50587",
}
MAX_FILE = 2 * 1024 * 1024
MAX_TREE = 64 * 1024 * 1024
DENIED = {"node_modules", "venv", "dist", "build", "__pycache__", "credentials", "secrets", "strix_runs"}
MODEL = re.compile(r"^[a-z][a-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_./:-]{0,119}$")


@contextmanager
def _directory(path: Path):
    """Open every ancestor by descriptor; safe even when a Zone renames parents."""
    if not path.is_absolute() or ".." in path.parts:
        raise SecurityError("Expected an absolute path without parent traversal")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _read_at(fd: int, name: str, *, uid: int, limit: int, immutable: bool = False) -> bytes:
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid:
            raise SecurityError("Expected a single-link regular file owned by the required identity")
        if immutable and info.st_mode & 0o022:
            raise SecurityError("Approval must not be group/world writable")
        if info.st_size > limit:
            raise ValidationError("File exceeds size limit")
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValidationError("File exceeds size limit")
        return data
    finally:
        os.close(file_fd)


def read_json(path: Path, *, uid: int, immutable: bool = False) -> dict:
    with _directory(path.parent) as fd:
        value = json.loads(_read_at(fd, path.name, uid=uid, limit=65536, immutable=immutable))
    if not isinstance(value, dict):
        raise ValidationError("Expected a JSON object")
    return value


def _excluded(name: str) -> bool:
    lower = name.lower()
    return (lower in DENIED or (lower.startswith(".") and lower != ".github")
            or lower.endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"))
            or lower in {"id_rsa", "id_ed25519", "credentials.json", "auth.json"})


def source_files(root: Path, uid: int, *, filter_source: bool) -> list[tuple[str, bytes]]:
    """Bounded snapshot; filtering is NOT a secret scanner or a DLP guarantee."""
    result, total = [], 0
    with _directory(root) as root_fd:
        for current, dirs, files, fd in os.fwalk(".", dir_fd=root_fd, follow_symlinks=False):
            if filter_source:
                dirs[:] = [name for name in dirs if not _excluded(name)]
                files = [name for name in files if not _excluded(name)]
            for name in dirs:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid:
                    raise SecurityError("Snapshot may not traverse symlinks or another identity's directories")
            for name in sorted(files):
                data = _read_at(fd, name, uid=uid, limit=MAX_FILE)
                relative = (Path(current) / name).as_posix()
                total += len(data)
                if total > MAX_TREE or len(result) >= 5000:
                    raise ValidationError("Snapshot exceeds 64 MiB or 5000 files; narrow the source")
                result.append((relative, data))
    if not result:
        raise ValidationError("Snapshot contains no eligible files")
    return sorted(result)


def snapshot_digest(files: list[tuple[str, bytes]]) -> str:
    entries = [(name, hashlib.sha256(data).hexdigest()) for name, data in files]
    return hashlib.sha256(json.dumps(entries, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def job_root(project: Path, job: str) -> Path:
    return project / "workspaces" / "strix" / validate_identifier(job, "Strix job")


def status(project: Path, *, job: str, zone: str, project_id: str, uid: int, policy_root: Path) -> dict:
    if os.geteuid() != uid or uid == 0:
        raise SecurityError("Read job status as the owning non-root Zone identity")
    root = job_root(project, job)
    summary = project / "evidence" / "strix" / job / "summary.json"
    if summary.exists() or summary.is_symlink():
        return read_json(summary, uid=uid)
    if (root / "execution").exists():
        return {"job": job, "state": "AWAITING_EXECUTION_EVIDENCE", "accepted": False,
                "next_gate": "Observe the native Hermes task/session; no final report exists yet. This does not prove the process is running."}
    policy = policy_root / f"{job}.json"
    if policy.exists() or policy.is_symlink():
        grant = read_json(policy, uid=0, immutable=True)
        validate_plan(grant, job=job, zone=zone, project_id=project_id, uid=uid)
        state = "AUTHORIZED_NOT_EXECUTED" if grant.get("expires_at", 0) > time.time() else "AUTHORIZATION_EXPIRED"
        return {"job": job, "state": state, "expires_at": grant.get("expires_at"), "accepted": False}
    return read_json(root / "plan.json", uid=uid)


def validate_limits(model: str, budget: float, timeout: int) -> None:
    if not isinstance(model, str) or not MODEL.fullmatch(model):
        raise ValidationError("Use an explicit provider/model identifier, not a URL or custom endpoint")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or not 0 < budget <= 25:
        raise ValidationError("Strix per-run budget must be finite and between 0 and 25 USD")
    if type(timeout) is not int or not 60 <= timeout <= 1800:
        raise ValidationError("Strix timeout must be between 60 and 1800 seconds")


def prepare(project: Path, repo: str, *, zone: str, project_id: str, uid: int,
            model: str, budget: float, timeout: int) -> dict:
    if os.geteuid() != uid or uid == 0:
        raise SecurityError("Prepare as the owning non-root Zone identity")
    validate_limits(model, budget, timeout)
    relative = Path(repo)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValidationError("Source must be relative to this Project's repos directory")
    source = project / "repos" / relative
    files = source_files(source, uid, filter_source=True)
    job = "strix-" + uuid.uuid4().hex[:16]
    root = job_root(project, job)
    fs = SafeFS([project])
    fs.mkdir(root, mode=0o700)
    fs.mkdir(root / "snapshot", mode=0o700)
    for name, data in files:
        destination = root / "snapshot" / name
        fs.mkdir(destination.parent, mode=0o700)
        fs.write_bytes(destination, data, mode=0o600)
    plan = {"schema_version": 1, "job": job, "zone": zone, "project": project_id, "uid": uid,
            "source": str(source), "snapshot_sha256": snapshot_digest(files), "file_count": len(files),
            "model": model, "max_budget_usd": budget, "timeout_seconds": timeout,
            "scan_mode": "quick", "max_turns": 80, "strix_version": VERSION,
            "state": "PREPARED_NOT_AUTHORIZED", "source_upload_approved": False}
    fs.write_text(root / "plan.json", json.dumps(plan, indent=2) + "\n", mode=0o600)
    return plan


def validate_plan(plan: dict, *, job: str, zone: str, project_id: str, uid: int) -> None:
    expected = {"schema_version": 1, "job": job, "zone": zone, "project": project_id,
                "uid": uid, "strix_version": VERSION, "scan_mode": "quick", "max_turns": 80}
    if any(plan.get(key) != value for key, value in expected.items()):
        raise SecurityError("Plan identity/version/mode does not match this invocation")
    validate_limits(plan.get("model"), plan.get("max_budget_usd"), plan.get("timeout_seconds"))
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("snapshot_sha256", ""))):
        raise ValidationError("Missing snapshot digest")


def approve(project: Path, *, job: str, zone: str, project_id: str, uid: int,
            policy_root: Path, host_record: Path, network: str, acceptance_sha256: str,
            source_upload_approved: bool, dedicated_lab: bool) -> dict:
    if os.geteuid() != 0 or uid == 0:
        raise SecurityError("Only the human/root operator may grant a non-root LAB identity access")
    if not source_upload_approved or not dedicated_lab:
        raise SecurityError("Explicit sanitized-source upload and disposable dedicated LAB approval are required")
    if read_json(host_record, uid=0, immutable=True).get("role") != "lab":
        raise SecurityError("Active Strix runs are forbidden on non-LAB Station Hosts")
    if not re.fullmatch(r"station-strix-lab-[a-z0-9-]{1,32}", network):
        raise ValidationError("Use a dedicated station-strix-lab-* Docker network")
    if not re.fullmatch(r"[0-9a-f]{64}", acceptance_sha256):
        raise ValidationError("Supply the SHA256 of the operator-reviewed worker/network acceptance evidence")
    root = job_root(project, job)
    plan = read_json(root / "plan.json", uid=uid)
    validate_plan(plan, job=job, zone=zone, project_id=project_id, uid=uid)
    if snapshot_digest(source_files(root / "snapshot", uid, filter_source=False)) != plan["snapshot_sha256"]:
        raise SecurityError("Snapshot changed; prepare and review a new job")
    grant = {**plan, "state": "AUTHORIZED_NOT_EXECUTED", "source_upload_approved": True,
             "dedicated_lab": True, "host_role": "lab", "expires_at": int(time.time()) + 3600, "network": network,
             "worker_acceptance_sha256": acceptance_sha256}
    fs = SafeFS([policy_root.parent])
    fs.mkdir(policy_root.parent, mode=0o711, owner=(0, 0))
    group = pwd.getpwuid(uid).pw_gid
    fs.mkdir(policy_root, mode=0o750, owner=(0, group))
    require_root_owned_directory_chain(policy_root)
    fs.write_text(policy_root / f"{job}.json", json.dumps(grant, indent=2) + "\n", mode=0o640, owner=(0, group))
    return {"job": job, "state": grant["state"], "expires_at": grant["expires_at"],
            "note": "Per-run soft cost limit; not a one-use or cumulative financial authorization."}


def build_execution(root: Path, grant: dict, *, image: str, key: str) -> tuple[list[str], dict[str, str]]:
    argv = [str(RUNTIME / "venv/bin/strix"), "--non-interactive", "--target", str(root / "target"),
            "--scan-mode", "quick", "--scope-mode", "full", "--max-budget", str(grant["max_budget_usd"]),
            "--max-turns", "80", "--config", str(root / "config.json"), "--mcp-config", str(root / "mcp.json"),
            "--instruction-file", str(root / "scope.txt")]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(root / "home"),
           "TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "home/cache"),
           "STRIX_LLM": grant["model"], "LLM_API_KEY": key, "STRIX_TELEMETRY": "false",
           "STRIX_RUNTIME_BACKEND": "docker", "DOCKER_HOST": "unix:///var/run/docker.sock",
           "STRIX_IMAGE": image, "STRIX_DOCKER_SANDBOX_NETWORK": grant["network"],
           "STRIX_SANDBOX_MEM_LIMIT": "4g", "STRIX_SANDBOX_SHM_SIZE": "256m",
           "STRIX_SANDBOX_CPUS": "2", "STRIX_SANDBOX_PIDS_LIMIT": "256",
           "STRIX_SANDBOX_LOG_MAX_SIZE": "10m", "STRIX_SANDBOX_LOG_MAX_FILE": "2",
           "STRIX_RUN_ID": grant["job"], "STRIX_RUN_TYPE": "station-lab", "PYTHONDONTWRITEBYTECODE": "1"}
    return argv, env


def interpret_result(run: dict, findings: Any, returncode: int, budget: float) -> dict:
    cost = run.get("llm_usage", {}).get("cost") if isinstance(run.get("llm_usage"), dict) else None
    completed = (run.get("status") == "completed" and isinstance(run.get("scan_results"), dict)
                 and run["scan_results"].get("scan_completed") is True)
    valid_cost = type(cost) in (int, float) and math.isfinite(cost) and 0 <= cost < budget
    consistent = (isinstance(findings, list) and all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in findings)
                  and ((returncode == 2 and bool(findings)) or (returncode == 0 and not findings)))
    state = ("FINDINGS_REPORTED" if findings else "NO_FINDINGS_REPORTED") if completed and valid_cost and consistent else "INCOMPLETE"
    return {"state": state, "returncode": returncode, "findings_count": len(findings) if isinstance(findings, list) else None,
            "observed_cost_usd": cost if valid_cost else None, "accepted": False, "untrusted_report": True,
            "next_gate": "Sentinel independent triage/reproduction; absence of findings is not proof of security."}


def _docker(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/docker", *args], env={"PATH": "/usr/bin:/bin", "DOCKER_HOST": "unix:///var/run/docker.sock"},
                          capture_output=True, text=True, timeout=timeout, check=True)


def cleanup_containers(job: str) -> None:
    """Only this job's labelled containers. Never prune unrelated worker resources."""
    ids = _docker(["ps", "-aq", "--filter", f"label=strix-run-id={job}"]).stdout.split()
    if any(not re.fullmatch(r"[a-f0-9]{12,64}", value) for value in ids):
        raise SecurityError("Unexpected Docker container identifier")
    if ids:
        _docker(["rm", "-f", *ids])


def run(project: Path, *, job: str, zone: str, project_id: str, uid: int,
        policy_root: Path, credential_file: Path) -> dict:
    if platform.system() != "Linux" or os.geteuid() != uid or uid == 0:
        raise SecurityError("Execute as the owning non-root identity on a dedicated Linux LAB Host")
    require_root_owned_directory_chain(policy_root)
    grant = read_json(policy_root / f"{validate_identifier(job)}.json", uid=0, immutable=True)
    validate_plan(grant, job=job, zone=zone, project_id=project_id, uid=uid)
    if (grant.get("source_upload_approved") is not True or grant.get("dedicated_lab") is not True
            or type(grant.get("expires_at")) is not int or grant["expires_at"] <= time.time()):
        raise SecurityError("Grant missing, expired or not approved for source disclosure")
    if grant.get("host_role") != "lab":
        raise SecurityError("Worker is not a LAB Host")
    image = IMAGES.get(platform.machine())
    if not image:
        raise ValidationError("Unsupported worker architecture")
    require_root_owned_directory_chain(RUNTIME)
    with _directory(RUNTIME) as fd:
        _read_at(fd, "BUILT", uid=0, limit=4096, immutable=True)
    network = json.loads(_docker(["network", "inspect", grant["network"]]).stdout)
    if len(network) != 1 or network[0].get("Internal") is not True or network[0].get("Driver") != "bridge":
        raise SecurityError("Accepted isolated internal Docker network is not present")
    _docker(["image", "inspect", image])  # Never pull/start a floating or absent image here.
    root = job_root(project, job)
    files = source_files(root / "snapshot", uid, filter_source=False)
    if snapshot_digest(files) != grant["snapshot_sha256"]:
        raise SecurityError("Approved source changed; prepare and re-authorize a new job")
    with _directory(credential_file.parent) as fd:
        info = os.stat(credential_file.name, dir_fd=fd, follow_symlinks=False)
        if info.st_mode & 0o077:
            raise SecurityError("Strix provider credential must have mode 0600")
        key = _read_at(fd, credential_file.name, uid=uid, limit=8192).decode().strip()
    if not key or any(char.isspace() for char in key):
        raise ValidationError("Invalid dedicated Strix provider credential")
    # Freeze the approved bytes in memory, then create a NEW disposable target.
    # Original repo and reviewed snapshot are never mounted writable by Strix.
    execution = root / "execution"
    fs = SafeFS([project])
    if execution.exists() or execution.is_symlink():
        raise ValidationError("Job already attempted; retain evidence and prepare a new job")
    with _directory(root) as fd:
        os.mkdir("execution", 0o700, dir_fd=fd)
    for directory in ("target", "home", "tmp"):
        fs.mkdir(execution / directory, mode=0o700)
    for name, data in files:
        fs.mkdir((execution / "target" / name).parent, mode=0o700)
        fs.write_bytes(execution / "target" / name, data, mode=0o600)
    fs.write_text(execution / "config.json", "{}\n", mode=0o600)
    fs.write_text(execution / "mcp.json", "[]\n", mode=0o600)
    fs.write_text(execution / "scope.txt", "Assess only the supplied disposable local source and services you start inside this sandbox. "
                  "No external targets, host access, credentials, persistence or network expansion. Report findings; do not publish or deploy.\n", mode=0o600)
    argv, env = build_execution(execution, grant, image=image, key=key)
    process = None
    cleanup_ok = True
    rc = -1
    def interrupted(signum, frame):
        raise InterruptedError("Assessment interrupted")
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    try:
        with _directory(execution) as fd:
            log_fd = os.open("runtime.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(log_fd, "wb") as log:
            remaining = min(grant["timeout_seconds"], grant["expires_at"] - time.time())
            if remaining <= 0:
                raise SecurityError("Authorization expired before execution")
            process = subprocess.Popen(argv, cwd=execution, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True, preexec_fn=limits)
            rc = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        rc = -124
    except (KeyboardInterrupt, InterruptedError):
        rc = -130
    except (OSError, subprocess.SubprocessError):
        rc = -1
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        try:
            cleanup_containers(job)
        except (OSError, ValueError, subprocess.SubprocessError, SecurityError):
            cleanup_ok = False
        signal.signal(signal.SIGTERM, previous_term)
    summary = {"state": "INCOMPLETE", "returncode": rc, "accepted": False, "untrusted_report": True}
    try:
        results = list((execution / "strix_runs").iterdir())
        if len(results) == 1:
            run_data = read_json(results[0] / "run.json", uid=uid)
            with _directory(results[0]) as fd:
                try:
                    findings = json.loads(_read_at(fd, "vulnerabilities.json", uid=uid, limit=MAX_FILE))
                except FileNotFoundError:
                    # Upstream 1.6.1 omits vulnerabilities.json for zero findings,
                    # but always emits SARIF. Require that positive empty artifact.
                    sarif = json.loads(_read_at(fd, "findings.sarif", uid=uid, limit=MAX_FILE))
                    runs = sarif.get("runs", [])
                    if sarif.get("version") != "2.1.0" or len(runs) != 1 or runs[0].get("results") != []:
                        raise ValidationError("Missing findings index and no explicit empty SARIF")
                    findings = []
            summary = interpret_result(run_data, findings, rc, grant["max_budget_usd"])
    except (OSError, ValueError, ValidationError, SecurityError):
        pass
    summary.update(job=job, snapshot_sha256=grant["snapshot_sha256"], cleanup_ok=cleanup_ok)
    if not cleanup_ok:
        summary.update(state="INCOMPLETE", next_gate="Inspect and remove only this job's labelled LAB containers before retrying.")
    evidence = project / "evidence" / "strix" / job
    fs.mkdir(evidence, mode=0o700)
    fs.write_text(evidence / "summary.json", json.dumps(summary, indent=2) + "\n", mode=0o600)
    return summary
