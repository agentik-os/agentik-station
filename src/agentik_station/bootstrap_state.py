"""Bootstrap checkpoints, separate from kernel receipts and live acceptance."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import PRODUCT_VERSION
from .errors import ReconcileError, SecurityError, StationError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_operation_id, validate_version
from .models import InstallSpec, new_operation_id
from .receipts import utc_now

STATE_ROOT = Path("/var/lib/station/bootstrap")
LOCK_ROOT = Path("/run/station/bootstrap")
MAX_RECORD_BYTES = 1024 * 1024
FEATURES = (
    "hermes", "hermes_auto_update", "codex", "agk_tui", "toolchain", "ai_stack",
    "voice", "scrapegraphai", "crawl4ai",
)
BASE_STAGES = (
    "system-packages", "tailscale", "operator-account", "operator-sudo",
    "operator-checkout", "operator-profile",
)
REPAIR = {
    "system-packages": "Inspect apt/dpkg state and repair the interrupted package operation before a reviewed retry.",
    "tailscale": "Inspect the signed repository, package and tailscaled state; preserve existing Tailnet enrollment.",
    "operator-account": "Inspect the existing operator UID, group and home; preserve that identity and its files.",
    "operator-sudo": "Inspect the operator sudoers file with visudo; preserve existing access before changing it.",
    "operator-checkout": "Preserve the operator checkout and local changes; reconcile an interrupted copy deliberately.",
    "operator-profile": "Inspect the operator profile and preserve custom settings before repairing Station PATH entries.",
    "hermes": "Inspect the pinned Hermes code, launcher and user state; do not rerun its installer over unreviewed changes.",
    "toolchain": "Run the selected toolchain checks; repair the named incomplete tool without replacing user configuration.",
    "scrapegraphai": "Inspect this exact web runtime and its BUILT marker; preserve incomplete files for supervised repair.",
    "crawl4ai": "Inspect this exact web runtime and its BUILT marker; preserve incomplete files for supervised repair.",
    "voice": "Inspect the Hermes environment and voice dependency imports before retrying package installation.",
    "agk-tui": "Inspect the AGK/RMUX installation and preserve existing sessions, launchers and user configuration.",
    "kernel-apply": "Inspect the separate kernel receipt and full Doctor before reapplying the desired state.",
    "kernel-readback": "Read the kernel receipt, status and full Doctor; a successful apply does not prove bootstrap complete.",
    "ai-stack": "Inspect each required component and its state; do not blindly repeat the entire stack.",
    "parakeet": "Inspect the pinned image, service and loopback health; preserve existing service configuration.",
    "guided-setup": "Inspect the Zone broker, Tailnet enrollment and private Serve path before retrying setup.",
    "full-stack-verify": "Inspect station deps full-check results and repair each unverified component; installer success alone is not full-stack acceptance.",
    "hermes-update-timer": "Inspect the updater unit and timer state; ensure no updater is still modifying Hermes.",
    "tool-inventory": "Read back selected tool versions and repair the inventory file without changing account credentials.",
    "agk-metadata-sync": "Retry only Station metadata synchronization after inspecting the AGK user state.",
}


def selected_stages(options: dict[str, Any], release_version: str = PRODUCT_VERSION) -> list[str]:
    # The graph belongs to the recorded release, not the reader's installed
    # version. Older receipts retain their original independent web/voice gates.
    version_parts = validate_version(release_version).split(".")
    aggregate_dependencies = (options["ai_stack"] and all(part.isdecimal() for part in version_parts)
                              and tuple(map(int, version_parts)) >= (11, 28))
    deferred = {"scrapegraphai", "crawl4ai", "voice"} if aggregate_dependencies else set()
    stages = list(BASE_STAGES)
    stages += [name for name in ("hermes", "toolchain", "scrapegraphai", "crawl4ai", "voice", "agk_tui")
               if options[name] and name not in deferred]
    stages = ["agk-tui" if name == "agk_tui" else name for name in stages]
    stages += ["kernel-apply", "kernel-readback"]
    if options["ai_stack"]:
        stages.append("ai-stack")
    elif options["voice"]:
        stages.append("parakeet")
    if options["hermes"]:
        stages.append("guided-setup")
    if aggregate_dependencies:
        stages.append("full-stack-verify")
    if options["hermes_auto_update"]:
        stages.append("hermes-update-timer")
    return stages + ["tool-inventory", "agk-metadata-sync"]


def validate_options(options: dict[str, Any]) -> dict[str, Any]:
    if set(options) != {*FEATURES, "mode", "sudo_mode"}:
        raise ValidationError("Bootstrap options must contain exactly the declared feature switches and modes")
    if any(type(options[name]) is not bool for name in FEATURES):
        raise ValidationError("Bootstrap feature switches must be booleans")
    if options["mode"] not in {"full", "team"} or options["sudo_mode"] not in {"password", "passwordless"}:
        raise ValidationError("Unsupported bootstrap mode or sudo mode")
    return dict(options)


def _secure_chain(path: Path, owner_uid: int, *, allow_missing: bool = False) -> None:
    for parent in reversed((path, *path.parents)):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise
        if not stat.S_ISDIR(info.st_mode):
            raise SecurityError("Bootstrap state ancestors must be real directories")
        if info.st_uid not in {0, owner_uid}:
            raise SecurityError("Bootstrap directory ancestry has unexpected ownership")
        if info.st_mode & 0o022 and (parent == path or not info.st_mode & stat.S_ISVTX):
            raise SecurityError("Bootstrap directory ancestry must not be writable by other identities")
        if parent == path and info.st_uid != owner_uid:
            raise SecurityError("Bootstrap directory must have trusted ownership and permissions")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Duplicate bootstrap JSON key")
        result[key] = value
    return result


def _decode_record(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_RECORD_BYTES:
        raise ValidationError("Bootstrap record exceeds its size limit")
    def reject_constant(_value):
        raise ValidationError("Non-finite bootstrap JSON value")
    try:
        payload = json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("Invalid bootstrap JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Bootstrap record must be an object")
    pending = [(payload, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 32:
            raise ValidationError("Bootstrap JSON exceeds its nesting limit")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValidationError("Non-finite bootstrap JSON value")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return payload


def _read_json(path: Path, owner_uid: int) -> dict[str, Any]:
    _secure_chain(path.parent, owner_uid)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid or info.st_nlink != 1 or info.st_mode & 0o022:
            raise SecurityError("Bootstrap records must be trusted regular files without hardlinks")
        if info.st_size > MAX_RECORD_BYTES:
            raise ValidationError("Bootstrap record exceeds its size limit")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            payload = _decode_record(stream.read(MAX_RECORD_BYTES + 1))
    finally:
        os.close(fd)
    return payload


def _lock_is_held(lock_root: Path, owner_uid: int) -> bool:
    try:
        _secure_chain(lock_root, owner_uid)
        fd = os.open(lock_root / "bootstrap.lock", os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return False
    try:
        _validate_lock(fd, lock_root, owner_uid)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _validate_lock(fd: int, lock_root: Path, owner_uid: int) -> None:
    _secure_chain(lock_root, owner_uid)
    info = os.fstat(fd)
    path_info = (lock_root / "bootstrap.lock").lstat()
    if (not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(path_info.st_mode)
            or info.st_uid != owner_uid or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
            or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)):
        raise SecurityError("Bootstrap lock must be the trusted, private, single-link lock file")


def _process_exit(value: Any, *, allow_zero: bool = True) -> None:
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= 255:
        raise ValidationError("Bootstrap exit codes must be process-status integers")


def _timestamp(value: Any) -> None:
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError("Bootstrap timestamps must be bounded timestamps")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("Invalid bootstrap timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError("Bootstrap timestamps require a timezone")


def _validate_receipt(receipt: dict[str, Any], attempt_id: str) -> None:
    """Fail closed on corrupt records before reporting or updating a stage."""
    if (receipt.get("schema_version") != 1 or receipt.get("attempt_id") != attempt_id
            or receipt.get("status") not in {"running", "success", "failed", "interrupted"}):
        raise ValidationError("Invalid bootstrap receipt")
    if not isinstance(receipt.get("spec"), dict) or not isinstance(receipt.get("options"), dict):
        raise ValidationError("Invalid bootstrap spec or options record")
    spec = InstallSpec.from_dict(receipt["spec"])
    options = validate_options(receipt["options"])
    stages = receipt.get("stages")
    if (not isinstance(stages, list) or not all(isinstance(stage, dict) for stage in stages)
            or [stage.get("id") for stage in stages] != selected_stages(options, spec.release_version)):
        raise ValidationError("Invalid bootstrap stage sequence")
    if any(stage.get("status") not in {"pending", "running", "success", "failed", "interrupted"}
           or stage.get("required") is not (stage["id"] != "agk-metadata-sync") for stage in stages):
        raise ValidationError("Invalid bootstrap stage state")
    _timestamp(receipt.get("started_at"))
    unfinished_predecessor = False
    running = 0
    for stage in stages:
        status = stage["status"]
        if status == "pending":
            if any(stage.get(key) is not None for key in ("started_at", "finished_at", "exit_code")):
                raise ValidationError("A pending bootstrap stage cannot carry execution evidence")
        else:
            if unfinished_predecessor:
                raise ValidationError("Bootstrap stage evidence skips an incomplete predecessor")
            _timestamp(stage.get("started_at"))
            if status == "running":
                running += 1
                if stage.get("finished_at") is not None or stage.get("exit_code") is not None:
                    raise ValidationError("A running bootstrap stage cannot carry terminal evidence")
            else:
                _timestamp(stage.get("finished_at"))
                _process_exit(stage.get("exit_code"), allow_zero=status == "success")
                if status == "success" and stage["exit_code"] != 0:
                    raise ValidationError("Successful bootstrap stages require exit code zero")
        unfinished_predecessor |= status in {"pending", "running"} or (stage["required"] and status != "success")
    if running > 1:
        raise ValidationError("Bootstrap stage execution cannot overlap")
    if receipt["status"] == "running":
        if receipt.get("finished_at") is not None or receipt.get("exit_code") is not None:
            raise ValidationError("A running bootstrap attempt cannot carry terminal evidence")
    else:
        _timestamp(receipt.get("finished_at"))
        _process_exit(receipt.get("exit_code"), allow_zero=receipt["status"] == "success")
        if running:
            raise ValidationError("A terminal bootstrap attempt cannot contain a running stage")
        if receipt["status"] == "success" and (receipt["exit_code"] != 0 or any(
                stage["status"] != "success" if stage["required"] else stage["status"] not in {"success", "failed"}
                for stage in stages)):
            raise ValidationError("Bootstrap success requires complete coherent stage evidence")
    if (receipt.get("kernel_receipt") != f"{spec.operation_id}.json"
            or receipt.get("operational") is not False or receipt.get("rollback_performed") is not False):
        raise ValidationError("Bootstrap receipts cannot assert operational acceptance or rollback")
    previous = receipt.get("previous_incomplete")
    if previous is not None:
        if (not isinstance(previous, dict) or previous.get("status") not in {"failed", "interrupted"}
                or previous.get("acknowledged") is not True):
            raise ValidationError("Invalid incomplete bootstrap predecessor")
        validate_operation_id(previous["attempt_id"])


def load_bootstrap_report(state_root: Path = STATE_ROOT, lock_root: Path = LOCK_ROOT, *, _owner_uid: int = 0) -> dict[str, Any]:
    """Read reported bootstrap state without creating files or asserting acceptance."""
    result: dict[str, Any] = {"status": "not-started", "evidence_kind": "reported", "operational": False, "next_actions": []}
    try:
        try:
            state_root.lstat()
        except FileNotFoundError:
            return result
        pointer = _read_json(state_root / "latest.json", _owner_uid)
        attempt_id = validate_operation_id(pointer["attempt_id"])
        receipt = _read_json(state_root / "attempts" / f"{attempt_id}.json", _owner_uid)
        _validate_receipt(receipt, attempt_id)
        # A read model exposes only this contract, even if future or manually
        # edited receipts contain debugging fields such as argv or environment.
        fields = {"schema_version", "attempt_id", "status", "started_at", "finished_at", "exit_code",
                  "spec", "spec_sha256", "options", "options_sha256", "source_files", "source_fingerprint",
                  "stages", "previous_incomplete", "next_actions", "kernel_receipt", "operational", "rollback_performed"}
        receipt = {key: value for key, value in receipt.items() if key in fields}
        receipt["stages"] = [{key: value for key, value in stage.items()
                              if key in {"id", "status", "required", "repair", "started_at", "finished_at", "exit_code"}}
                             for stage in receipt["stages"]]
        if receipt.get("previous_incomplete") is not None:
            receipt["previous_incomplete"] = {key: receipt["previous_incomplete"][key]
                                              for key in ("attempt_id", "status", "acknowledged")}
        status = receipt["status"]
        if status == "running" and not _lock_is_held(lock_root, _owner_uid):
            status = "interrupted"
            for stage in receipt["stages"]:
                if stage["status"] == "running":
                    stage["status"] = "interrupted"
            receipt["next_actions"] = ["The bootstrap lock is no longer held; inspect the last running stage and any surviving installer processes before a reviewed retry."]
        receipt["status"] = status
        result.update(status=status, latest=receipt, next_actions=receipt.get("next_actions", []))
    except PermissionError:
        result.update(status="unreadable", next_actions=["Read the root-owned bootstrap receipt through an authorized operator."])
    except (OSError, StationError, KeyError, TypeError, ValueError):
        result.update(status="unavailable", next_actions=["Inspect the bootstrap receipt and lock paths; no readiness claim can be made."])
    return result


class BootstrapState:
    def __init__(self, state_root: Path = STATE_ROOT, lock_root: Path = LOCK_ROOT, *, owner_uid: int = 0):
        if os.geteuid() != owner_uid:
            raise SecurityError("Bootstrap state changes require the owning privileged identity")
        self.state_root, self.lock_root, self.owner_uid = Path(state_root), Path(lock_root), owner_uid

    def prepare_lock(self) -> Path:
        _secure_chain(self.lock_root, self.owner_uid, allow_missing=True)
        fs = SafeFS([self.lock_root])
        if self.lock_root.exists() or self.lock_root.is_symlink():
            _secure_chain(self.lock_root, self.owner_uid)
        fs.mkdir(self.lock_root, 0o700)
        path = self.lock_root / "bootstrap.lock"
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            _validate_lock(fd, self.lock_root, self.owner_uid)
        finally:
            os.close(fd)
        return path

    def acquire(self, fd: int) -> None:
        _validate_lock(fd, self.lock_root, self.owner_uid)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReconcileError("Another bootstrap is running; no Host stages were started") from exc

    def _persist(self, receipt: dict[str, Any]) -> None:
        _validate_receipt(receipt, receipt["attempt_id"])
        fs = SafeFS([self.state_root])
        path = self.state_root / "attempts" / f"{validate_operation_id(receipt['attempt_id'])}.json"
        if path.exists() or path.is_symlink():
            _read_json(path, self.owner_uid)
        fs.write_text(path, json.dumps(receipt, indent=2, sort_keys=True) + "\n", 0o600)

    def begin(self, spec_path: Path, source_root: Path, options: dict[str, Any], *, acknowledge: str | None = None) -> str:
        options = validate_options(options)
        _secure_chain(self.state_root, self.owner_uid, allow_missing=True)
        if acknowledge:
            validate_operation_id(acknowledge)
        spec_bytes = spec_path.read_bytes()
        spec = InstallSpec.from_dict(_decode_record(spec_bytes))
        previous = None
        if self.state_root.exists() or self.state_root.is_symlink():
            _secure_chain(self.state_root, self.owner_uid)
            pointer = self.state_root / "latest.json"
            if pointer.exists() or pointer.is_symlink():
                previous_id = validate_operation_id(_read_json(pointer, self.owner_uid)["attempt_id"])
                previous = _read_json(self.state_root / "attempts" / f"{previous_id}.json", self.owner_uid)
                _validate_receipt(previous, previous_id)
                if previous["status"] != "success" and acknowledge != previous_id:
                    raise ReconcileError(f"Incomplete bootstrap {previous_id}; inspect its stage repair actions before an acknowledged fresh run")
        if acknowledge and (not previous or previous["status"] == "success" or acknowledge != previous["attempt_id"]):
            raise ValidationError("Incomplete-bootstrap acknowledgement does not match the latest attempt")
        fingerprints = {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
                        for name in ("VERSION", "RELEASE_PROVENANCE.json", "config/versions.lock", "bootstrap.sh")}
        if (source_root / "VERSION").read_text().strip() != spec.release_version:
            raise ValidationError("Bootstrap spec and source release differ")
        now = utc_now()
        attempt_id = new_operation_id()
        receipt = {
            "schema_version": 1, "attempt_id": attempt_id, "status": "running",
            "started_at": now, "finished_at": None, "exit_code": None,
            "spec": spec.to_dict(), "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
            "options": options, "options_sha256": hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest(),
            "source_files": fingerprints,
            "source_fingerprint": hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest(),
            "stages": [{"id": stage, "status": "pending", "required": stage != "agk-metadata-sync", "repair": REPAIR[stage]}
                       for stage in selected_stages(options, spec.release_version)],
            "previous_incomplete": ({"attempt_id": previous["attempt_id"], "status": "interrupted" if previous["status"] == "running" else previous["status"],
                                     "acknowledged": True} if previous and previous["status"] != "success" else None),
            "next_actions": [], "kernel_receipt": f"{spec.operation_id}.json",
            "operational": False, "rollback_performed": False,
        }
        fs = SafeFS([self.state_root])
        if (self.state_root / "attempts").exists() or (self.state_root / "attempts").is_symlink():
            _secure_chain(self.state_root / "attempts", self.owner_uid)
        fs.mkdir(self.state_root, 0o700)
        fs.mkdir(self.state_root / "attempts", 0o700)
        self._persist(receipt)
        fs.write_text(self.state_root / "latest.json", json.dumps({"attempt_id": attempt_id}) + "\n", 0o600)
        return attempt_id

    def checkpoint(self, attempt_id: str, stage_id: str, status: str, *, exit_code: int | None = None) -> None:
        path = self.state_root / "attempts" / f"{validate_operation_id(attempt_id)}.json"
        receipt = _read_json(path, self.owner_uid)
        _validate_receipt(receipt, attempt_id)
        if receipt["status"] != "running":
            raise ValidationError("Cannot change a finished bootstrap attempt")
        stage = next((item for item in receipt["stages"] if item["id"] == stage_id), None)
        if stage is None or status not in {"running", "success", "failed"}:
            raise ValidationError("Unknown bootstrap stage or checkpoint")
        if status == "running":
            if stage["status"] != "pending" or any(item["status"] == "running" for item in receipt["stages"]):
                raise ValidationError("Bootstrap stages cannot be resumed or overlap")
            if next(item for item in receipt["stages"] if item["status"] == "pending") is not stage:
                raise ValidationError("Bootstrap stages must follow the declared sequence")
            if any(item["required"] and item["status"] != "success"
                   for item in receipt["stages"][:receipt["stages"].index(stage)]):
                raise ValidationError("A failed required bootstrap stage cannot be skipped")
            stage["started_at"] = utc_now()
        else:
            if stage["status"] != "running":
                raise ValidationError("Only a running bootstrap stage can finish")
            if status == "failed":
                _process_exit(exit_code, allow_zero=False)
            stage.update(finished_at=utc_now(), exit_code=exit_code if status == "failed" else 0)
        stage["status"] = status
        self._persist(receipt)

    def finish(self, attempt_id: str, exit_code: int, *, interrupted: bool = False) -> None:
        _process_exit(exit_code, allow_zero=not interrupted)
        path = self.state_root / "attempts" / f"{validate_operation_id(attempt_id)}.json"
        receipt = _read_json(path, self.owner_uid)
        _validate_receipt(receipt, attempt_id)
        if receipt["status"] != "running":
            raise ValidationError("Bootstrap attempt already finished")
        failed_status = "interrupted" if interrupted else "failed"
        incomplete = [stage for stage in receipt["stages"]
                      if stage["status"] in {"pending", "running", "interrupted"}
                      or (stage["required"] and stage["status"] != "success")]
        effective_exit = exit_code or (2 if incomplete else 0)
        for stage in receipt["stages"]:
            if stage["status"] == "running":
                stage.update(status=failed_status, finished_at=utc_now(), exit_code=effective_exit)
        status = "success" if effective_exit == 0 else failed_status
        receipt.update(status=status, exit_code=effective_exit, finished_at=utc_now())
        receipt["next_actions"] = [stage["repair"] for stage in receipt["stages"] if stage["status"] in {"failed", "interrupted"}]
        if status != "success" and not receipt["next_actions"]:
            receipt["next_actions"] = ["Inspect incomplete bootstrap stages; no automatic resume or rollback was performed."]
        if status == "success":
            receipt["next_actions"].append("Complete scoped account enrollment, external readback and human acceptance before OPERATIONAL.")
        self._persist(receipt)
        if exit_code == 0 and incomplete:
            raise ReconcileError("Bootstrap cannot succeed while required stages remain incomplete")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "acquire", "begin", "checkpoint", "finish", "report"))
    parser.add_argument("--fd", type=int, default=9)
    parser.add_argument("--attempt")
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--option", action="append", default=[])
    parser.add_argument("--acknowledge")
    parser.add_argument("--stage")
    parser.add_argument("--status")
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--interrupted", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "report":
            print(json.dumps(load_bootstrap_report(), indent=2, sort_keys=True))
            return 0
        state = BootstrapState()
        if args.action == "prepare":
            print(state.prepare_lock())
            return 0
        state.acquire(args.fd)
        if args.action == "begin":
            options = dict(value.split("=", 1) for value in args.option)
            options = {key: value == "1" if key in FEATURES and value in {"0", "1"} else value for key, value in options.items()}
            print(state.begin(args.spec, args.source, options, acknowledge=args.acknowledge))
        elif args.action == "checkpoint":
            state.checkpoint(args.attempt, args.stage, args.status, exit_code=args.exit_code)
        elif args.action == "finish":
            state.finish(args.attempt, args.exit_code, interrupted=args.interrupted)
    except (OSError, StationError, KeyError, TypeError, ValueError) as exc:
        # Never include command text, environment values or upstream output.
        message = str(exc) if isinstance(exc, StationError) else "Bootstrap checkpoint unavailable; inspect the root-owned state and lock paths"
        print(f"BOOTSTRAP_STATE_ERROR: {message}", file=sys.stderr)
        return 2
    return 0
