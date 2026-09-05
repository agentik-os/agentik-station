"""Narrow, non-overwriting Project creation using the canonical kernel templates."""
from __future__ import annotations

import json
import ctypes
import os
import pwd
import stat
import sys
from pathlib import Path
from typing import Any

from .errors import ReconcileError, SecurityError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_identifier
from .identity import Identity
from .installer import StationInstaller, install_lock, project_creation_layout
from .models import InstallSpec, new_operation_id
from .os_lifecycle import _context, _directory
from .paths import LayoutPaths
from .receipts import utc_now


def _signature(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _rename_noreplace(source_fd: int, source: str, target_fd: int, target: str) -> None:
    """Atomic no-replace publication, never an ordinary replacing rename fallback."""
    libc = ctypes.CDLL(None, use_errno=True)
    name, flag = ("renameatx_np", 0x00000004) if sys.platform == "darwin" else ("renameat2", 1)
    function = getattr(libc, name, None)
    if function is None:
        raise SecurityError("Atomic no-replace directory publication is unavailable on this Host")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(source_fd, os.fsencode(source), target_fd, os.fsencode(target), flag) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


class _NewProjectFS(SafeFS):
    """Only write inside exclusively reserved, descriptor-pinned private roots.

    The kernel continues to own all templates. Ownership is delayed so a Zone
    cannot modify generated children while root is constructing the new tree.
    Parent renames can hide a new root but cannot redirect a descriptor write.
    """

    def __init__(self, roots: list[Path], *, staging_roots: list[Path], operation_id: str, authority_uid: int):
        super().__init__(roots)
        self.roots = roots
        self.staging = dict(zip(roots, [root / ".project-staging" / operation_id for root in staging_roots]))
        self.authority_uid = authority_uid
        self.fds: dict[Path, int] = {}
        self.stage_parents: dict[Path, int] = {}
        self.published: set[Path] = set()
        self.desired: dict[Path, tuple[int, tuple[int, int]]] = {}
        self.files: list[Path] = []
        self.dirs: list[Path] = []
        self.handed_off = False
        self.uncertain_reservation = False

    def reserve(self) -> None:
        for root in self.roots:
            stage = self.staging[root]
            # These anchors are root-owned Station roots, never Zone-owned
            # parents. A Zone therefore cannot substitute an older private
            # tree in the mkdir/open interval.
            with _directory(stage.parent.parent) as anchor:
                info = os.fstat(anchor)
                if info.st_uid != self.authority_uid or info.st_mode & 0o022:
                    raise SecurityError("Project staging anchor is not private authority")
                try:
                    os.mkdir(stage.parent.name, mode=0o700, dir_fd=anchor)
                except FileExistsError:
                    pass
                parent = os.open(stage.parent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=anchor)
            info = os.fstat(parent)
            if info.st_uid != self.authority_uid or stat.S_IMODE(info.st_mode) != 0o700:
                os.close(parent)
                raise SecurityError("Unsafe Project staging directory")
            self.stage_parents[root] = parent
            os.mkdir(stage.name, mode=0o700, dir_fd=parent)
            self.uncertain_reservation = True
            fd = os.open(stage.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            self.fds[root] = fd
            self.uncertain_reservation = False

    def publish(self) -> None:
        # Flush generated directory entries before the two independent moves.
        # This is not a cross-filesystem transaction: a partial publication is
        # retained with a failure receipt and must be inspected before retrying.
        for path in reversed(self.dirs):
            parent = self._parent(path)
            try:
                fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                os.close(parent)
        for root in self.roots:
            os.fsync(self.fds[root])
            with _directory(root.parent) as target:
                _rename_noreplace(self.stage_parents[root], self.staging[root].name, target, root.name)
                self.published.add(root)
                os.fsync(target)
                os.fsync(self.stage_parents[root])

    def _parent(self, path: Path) -> int:
        root = self.anchor_for(path)
        fd = os.dup(self.fds[root])
        try:
            for name in path.parent.relative_to(root).parts:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def mkdir(self, path, mode=0o755, owner=None):
        path = Path(path)
        self.anchor_for(path)
        if owner is None or path in self.desired:
            raise SecurityError("Project generation requires explicit ownership and unique paths")
        if path not in self.fds:
            parent = self._parent(path)
            try:
                os.mkdir(path.name, mode=0o700, dir_fd=parent)
            finally:
                os.close(parent)
            self.dirs.append(path)
        self.desired[path] = mode, owner
        return path

    def write_text(self, path, text, mode=0o644, owner=None):
        path = Path(path)
        if owner is None or path in self.desired:
            raise SecurityError("Project generation requires explicit ownership and unique paths")
        parent = self._parent(path)
        try:
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            self.files.append(path)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        self.desired[path] = mode, owner
        return path

    def still_named(self) -> bool:
        try:
            for path, fd in self.fds.items():
                with _directory(path.parent) as parent:
                    current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(current.st_mode) or _signature(current) != _signature(os.fstat(fd)):
                    return False
            return True
        except OSError:
            return False

    def handoff(self) -> None:
        if not self.still_named():
            raise SecurityError("A Project root was renamed; retain partial state for inspection")
        # Files and children first, both top-level roots last.
        for path in [*self.files, *reversed(self.dirs), *self.roots]:
            mode, owner = self.desired[path]
            if path in self.fds:
                # From this point a Zone may be able to alter a handed-off root;
                # a later failure must leave partial state for inspection.
                self.handed_off = True
                fd = os.dup(self.fds[path])
            else:
                parent = self._parent(path)
                try:
                    fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                finally:
                    os.close(parent)
            try:
                os.fchown(fd, *owner)
                os.fchmod(fd, mode)
                os.fsync(fd)
            finally:
                os.close(fd)
        self.handed_off = True
        if not self.still_named():
            raise SecurityError("A Project root moved during handoff; inspect partial state")

    def rollback_new(self) -> bool:
        # Never delete through a moved root or after ownership has been handed
        # off: only the named new private tree is eligible for best-effort undo.
        if self.handed_off or self.published or self.uncertain_reservation:
            return False
        try:
            for path in reversed(self.files):
                parent = self._parent(path)
                try:
                    os.unlink(path.name, dir_fd=parent)
                finally:
                    os.close(parent)
            for path in reversed(self.dirs):
                parent = self._parent(path)
                try:
                    os.rmdir(path.name, dir_fd=parent)
                finally:
                    os.close(parent)
            for path in reversed(list(self.fds)):
                # Only the authority-owned staging parent is ever cleaned.
                # Never rmdir a top-level entry in a mutable Zone parent.
                os.rmdir(self.staging[path].name, dir_fd=self.stage_parents[path])
            return True
        except OSError:
            return False

    def close(self) -> None:
        for fd in self.fds.values():
            os.close(fd)
        for fd in self.stage_parents.values():
            os.close(fd)
        self.fds.clear()
        self.stage_parents.clear()


def _preflight(paths: LayoutPaths, zone: dict, project_id: str) -> tuple[dict, dict, Identity]:
    context = _context(paths, zone)
    authority_uid = os.getuid() if paths.test_mode else 0
    for anchor in (paths.runtime, paths.varlib):
        with _directory(anchor, uid=authority_uid, trusted_root=anchor if paths.test_mode else None):
            pass
    spec = context["spec"]
    entry = pwd.getpwnam(context["user"])
    layout = project_creation_layout(paths, Path(zone["human_root"]), spec.zone_id, project_id)
    for root in (layout["human_root"], layout["runtime_state_root"]):
        with _directory(root.parent) as parent:
            info = os.fstat(parent)
            if (info.st_uid, info.st_gid) != (entry.pw_uid, entry.pw_gid) or info.st_mode & 0o022:
                raise SecurityError("Project parent is not owned exclusively by its Zone identity")
            try:
                os.stat(root.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValidationError("Project already exists or has partial state; inspect it before retrying")
    return context, layout, Identity(context["user"], entry.pw_uid, entry.pw_gid, Path(entry.pw_dir))


def create_project(paths: LayoutPaths, repo_root: Path, *, zone: dict, project_id: str,
                   plan: bool = False) -> dict[str, Any]:
    """Create only a new Project and its runtime namespace; never reconcile Host/Zone."""
    project_id = validate_identifier(project_id, "project_id")
    context, layout, identity = _preflight(paths, zone, project_id)
    payload: dict[str, Any] = {
        "schema_version": 1, "kind": "StationProjectCreation", "zone_id": zone["id"], "project_id": project_id,
        "human_root": str(layout["human_root"]), "runtime_state_root": str(layout["runtime_state_root"]),
        "directories": [{"path": str(path), "mode": f"{mode:04o}"} for path, mode in layout["directories"]],
        "claim": "PREPARED_NOT_RUN", "operational": False, "atomic_no_replace_required": True,
        "rollback_policy": "UNPUBLISHED_STAGING_ONLY; retain any partially published Project for inspection",
        "next_actions": ["Install the selected OS into this Zone/Project, configure its Director, then verify external acceptance."],
    }
    if plan:
        return payload
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError("Project creation requires root for scoped ownership assignment")
    operation_id = new_operation_id()
    spec = InstallSpec(host_id=context["spec"].host_id, install_system_packages=False,
                       configure_fail2ban=False, enable_doctor_timer=False, operation_id=operation_id)
    installer = StationInstaller(repo_root, spec, paths)
    installer._zone_identities[zone["id"]] = identity
    installer._zone_paths[zone["id"]] = Path(zone["human_root"])
    roots = [layout["human_root"], layout["runtime_state_root"]]
    receipt_root = paths.varlib / "project-operations"
    receipt_path = receipt_root / f"{operation_id}.json"
    authority = (os.getuid(), os.getgid()) if paths.test_mode else (0, 0)
    fs = _NewProjectFS(roots, staging_roots=[paths.runtime, paths.varlib], operation_id=operation_id, authority_uid=authority[0])
    installer.fs = fs
    receipt_fs = SafeFS([paths.varlib])
    receipt = {"schema_version": 1, "operation_id": operation_id, "zone_id": zone["id"], "project_id": project_id,
               "status": "STARTED", "started_at": utc_now(), "human_root": str(roots[0]),
               "runtime_state_root": str(roots[1]), "staging_roots": [str(path) for path in fs.staging.values()], "operational": False}
    with install_lock(paths, operation_id):
        _preflight(paths, zone, project_id)
        # Receipt authority is never placed in the Zone-owned Project.
        with _directory(paths.varlib, uid=authority[0], trusted_root=paths.varlib if paths.test_mode else None):
            pass
        try:
            with _directory(receipt_root, uid=authority[0], trusted_root=paths.varlib if paths.test_mode else None):
                pass
        except FileNotFoundError:
            receipt_fs.mkdir(receipt_root, mode=0o700, owner=authority)
        receipt_fs.write_text(receipt_path, json.dumps(receipt, sort_keys=True) + "\n", 0o600, authority)
        try:
            fs.reserve()
            installer._create_project(context["spec"], project_id)
            fs.publish()
            fs.handoff()
            receipt.update(status="COMPLETED", finished_at=utc_now(), claim="PROJECT_LAYOUT_CREATED_NOT_OS_INSTALLED")
            receipt_fs.write_text(receipt_path, json.dumps(receipt, sort_keys=True) + "\n", 0o600, authority)
        except BaseException as exc:
            rollback = fs.rollback_new()
            receipt.update(status="FAILED", finished_at=utc_now(), error_type=type(exc).__name__,
                           error_code=getattr(exc, "errno", None),
                           new_tree_rollback_completed=rollback,
                           next_repair_action="Inspect the two named Project roots and this receipt; never overwrite or blindly remove a partial Project.")
            receipt_fs.write_text(receipt_path, json.dumps(receipt, sort_keys=True) + "\n", 0o600, authority)
            raise ReconcileError("Project creation failed; inspect its operation receipt before retrying") from exc
        finally:
            fs.close()
    payload.update(claim="PROJECT_LAYOUT_CREATED_NOT_OS_INSTALLED", operation_id=operation_id, receipt=str(receipt_path))
    return payload
