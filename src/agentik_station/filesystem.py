from __future__ import annotations

import errno
import os
import stat
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .errors import SecurityError

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_under(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path), str(root)]) == str(root)
    except ValueError:
        return False


def _reject_bad_component(name: str) -> None:
    if name in {"", ".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise SecurityError(f"Unsafe path component: {name!r}")


@dataclass
class ChangeJournal:
    """Best-effort rollback journal for Station-owned filesystem mutations.

    Package manager changes and Unix-account creation are intentionally outside
    this journal. The reconciler remains convergent and records any partial
    failure as DEGRADED rather than claiming a full transaction.
    """

    created_files: list[Path] = field(default_factory=list)
    created_dirs: list[Path] = field(default_factory=list)
    replaced_files: dict[Path, tuple[bytes, int, int, int]] = field(default_factory=dict)
    previous_links: dict[Path, str | None] = field(default_factory=dict)


class SafeFS:
    """Filesystem helper constrained to explicit roots.

    Directory traversal uses directory descriptors and ``O_NOFOLLOW`` where the
    platform provides it. Managed writes are atomic. Existing symlinks and
    special files are rejected rather than followed.
    """

    def __init__(self, allowed_roots: Iterable[Path], journal: ChangeJournal | None = None):
        roots = tuple(sorted((_absolute(p) for p in allowed_roots), key=lambda p: len(str(p)), reverse=True))
        if not roots:
            raise ValueError("At least one allowed root is required")
        self.allowed_roots = roots
        self.journal = journal or ChangeJournal()
        self._rolling_back = False

    def anchor_for(self, path: Path | str) -> Path:
        target = _absolute(path)
        for root in self.allowed_roots:
            if target == root or _is_under(target, root):
                return root
        raise SecurityError(f"Path escapes Station-managed roots: {target}")

    @staticmethod
    def _assert_existing_absolute_chain(path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            _reject_bad_component(part)
            current /= part
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                return
            if stat.S_ISLNK(st.st_mode):
                raise SecurityError(f"Symlink forbidden in managed path: {current}")
            if not stat.S_ISDIR(st.st_mode):
                raise SecurityError(f"Expected directory in managed path: {current}")

    def _record_created_dir(self, path: Path) -> None:
        if not self._rolling_back and path not in self.journal.created_dirs:
            self.journal.created_dirs.append(path)

    def _ensure_anchor(self, anchor: Path, mode: int = 0o755) -> None:
        anchor = _absolute(anchor)
        self._assert_existing_absolute_chain(anchor.parent)
        current = Path(anchor.anchor)
        fd = os.open(current, os.O_RDONLY | _DIRECTORY)
        try:
            for part in anchor.parts[1:]:
                _reject_bad_component(part)
                current /= part
                try:
                    child_fd = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    os.mkdir(part, mode=mode, dir_fd=fd)
                    self._record_created_dir(current)
                    child_fd = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=fd)
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                        raise SecurityError(f"Unsafe managed directory component: {current}") from exc
                    raise
                os.close(fd)
                fd = child_fd
        finally:
            os.close(fd)

    def _open_dir(self, path: Path | str, *, create: bool = False, mode: int = 0o755) -> int:
        target = _absolute(path)
        anchor = self.anchor_for(target)
        self._ensure_anchor(anchor)
        if target == anchor:
            return os.open(anchor, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)

        relative = target.relative_to(anchor)
        fd = os.open(anchor, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        current = anchor
        try:
            for part in relative.parts:
                _reject_bad_component(part)
                current /= part
                try:
                    child_fd = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=mode, dir_fd=fd)
                    self._record_created_dir(current)
                    child_fd = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=fd)
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                        raise SecurityError(f"Unsafe managed directory component: {current}") from exc
                    raise
                os.close(fd)
                fd = child_fd
            return fd
        except Exception:
            os.close(fd)
            raise

    def mkdir(self, path: Path | str, mode: int = 0o755, owner: tuple[int, int] | None = None) -> Path:
        target = _absolute(path)
        fd = self._open_dir(target, create=True, mode=mode)
        try:
            os.fchmod(fd, mode)
            if owner:
                os.fchown(fd, owner[0], owner[1])
        finally:
            os.close(fd)
        return target

    def lstat(self, path: Path | str) -> os.stat_result:
        target = _absolute(path)
        self.anchor_for(target)
        return os.lstat(target)

    def assert_regular_file(self, path: Path | str) -> Path:
        target = _absolute(path)
        self.anchor_for(target)
        st = os.lstat(target)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise SecurityError(f"Expected a regular non-symlink file: {target}")
        return target

    def assert_directory(self, path: Path | str) -> Path:
        target = _absolute(path)
        self.anchor_for(target)
        st = os.lstat(target)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise SecurityError(f"Expected a directory, not a symlink or special file: {target}")
        return target

    @staticmethod
    def _read_existing(parent_fd: int, name: str, target: Path) -> tuple[bytes, int, int, int] | None:
        try:
            st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(st.st_mode):
            raise SecurityError(f"Refusing to overwrite non-regular managed file: {target}")
        fd = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=parent_fd)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(fd)
        return b"".join(chunks), stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid

    def _atomic_write(
        self,
        path: Path | str,
        payload: bytes,
        mode: int,
        owner: tuple[int, int] | None = None,
    ) -> Path:
        target = _absolute(path)
        self.anchor_for(target)
        parent_fd = self._open_dir(target.parent, create=True)
        name = target.name
        _reject_bad_component(name)
        temp_name = f".{name}.tmp-{uuid.uuid4().hex}"
        try:
            old = self._read_existing(parent_fd, name, target)
            if old is not None and not self._rolling_back and target not in self.journal.replaced_files:
                self.journal.replaced_files[target] = old

            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW
            temp_fd = os.open(temp_name, flags, mode, dir_fd=parent_fd)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(temp_fd, view)
                    view = view[written:]
                os.fsync(temp_fd)
                os.fchmod(temp_fd, mode)
                if owner:
                    os.fchown(temp_fd, owner[0], owner[1])
            finally:
                os.close(temp_fd)
            os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
            if old is None and not self._rolling_back:
                self.journal.created_files.append(target)
        finally:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)
        return target

    def write_text(
        self,
        path: Path | str,
        text: str,
        mode: int = 0o644,
        owner: tuple[int, int] | None = None,
    ) -> Path:
        return self._atomic_write(path, text.encode("utf-8"), mode, owner)

    def write_bytes(
        self,
        path: Path | str,
        payload: bytes,
        mode: int = 0o644,
        owner: tuple[int, int] | None = None,
    ) -> Path:
        return self._atomic_write(path, payload, mode, owner)

    def read_text(self, path: Path | str) -> str:
        target = self.assert_regular_file(path)
        fd = os.open(target, os.O_RDONLY | _NOFOLLOW)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")
        finally:
            os.close(fd)

    def chown(self, path: Path | str, uid: int, gid: int) -> None:
        target = _absolute(path)
        self.anchor_for(target)
        st = os.lstat(target)
        if stat.S_ISLNK(st.st_mode):
            raise SecurityError(f"Refusing to chown symlink: {target}")
        os.chown(target, uid, gid, follow_symlinks=False)

    def chmod(self, path: Path | str, mode: int) -> None:
        target = _absolute(path)
        self.anchor_for(target)
        st = os.lstat(target)
        if stat.S_ISLNK(st.st_mode):
            raise SecurityError(f"Refusing to chmod symlink: {target}")
        os.chmod(target, mode, follow_symlinks=False)

    def copy_file(self, source: Path, destination: Path, mode: int | None = None) -> None:
        source = Path(source)
        st = os.lstat(source)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise SecurityError(f"Source must be a regular non-symlink file: {source}")
        fd = os.open(source, os.O_RDONLY | _NOFOLLOW)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(fd)
        chosen_mode = mode if mode is not None else stat.S_IMODE(st.st_mode)
        self.write_bytes(destination, b"".join(chunks), chosen_mode)

    def copy_tree_strict(self, source: Path, destination: Path, excludes: set[str] | None = None) -> None:
        source = Path(source)
        excludes = excludes or set()
        source_stat = os.lstat(source)
        if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISDIR(source_stat.st_mode):
            raise SecurityError(f"Source tree must be a real directory: {source}")
        self.mkdir(destination, 0o755)
        for entry in sorted(os.scandir(source), key=lambda item: item.name):
            if (
                entry.name in excludes
                or entry.name.endswith(".pyc")
                or entry.name.endswith(".egg-info")
            ):
                continue
            src = source / entry.name
            dst = destination / entry.name
            if entry.is_symlink():
                raise SecurityError(f"Repository symlinks are not accepted in a release: {src}")
            if entry.is_dir(follow_symlinks=False):
                self.copy_tree_strict(src, dst, excludes)
            elif entry.is_file(follow_symlinks=False):
                self.copy_file(src, dst)
            else:
                raise SecurityError(f"Special files are not accepted in a release: {src}")

    def remove_tree_strict(self, path: Path | str) -> None:
        target = _absolute(path)
        self.anchor_for(target)
        try:
            st = os.lstat(target)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode):
            raise SecurityError(f"Refusing to recursively remove symlink: {target}")
        if not stat.S_ISDIR(st.st_mode):
            if stat.S_ISREG(st.st_mode):
                target.unlink()
                return
            raise SecurityError(f"Refusing to remove special file: {target}")
        for entry in os.scandir(target):
            child = target / entry.name
            if entry.is_symlink():
                raise SecurityError(f"Symlink found in managed removal tree: {child}")
            if entry.is_dir(follow_symlinks=False):
                self.remove_tree_strict(child)
            elif entry.is_file(follow_symlinks=False):
                child.unlink()
            else:
                raise SecurityError(f"Special file found in managed removal tree: {child}")
        target.rmdir()

    def trees_equal(self, left: Path, right: Path) -> bool:
        left = Path(left)
        right = Path(right)
        if not left.is_dir() or not right.is_dir() or left.is_symlink() or right.is_symlink():
            return False
        left_entries = {entry.name: entry for entry in os.scandir(left)}
        right_entries = {entry.name: entry for entry in os.scandir(right)}
        if left_entries.keys() != right_entries.keys():
            return False
        for name in left_entries:
            a = left_entries[name]
            b = right_entries[name]
            if a.is_symlink() or b.is_symlink():
                return False
            if a.is_dir(follow_symlinks=False) and b.is_dir(follow_symlinks=False):
                if not self.trees_equal(left / name, right / name):
                    return False
            elif a.is_file(follow_symlinks=False) and b.is_file(follow_symlinks=False):
                if os.path.getsize(a.path) != os.path.getsize(b.path):
                    return False
                with open(a.path, "rb") as fa, open(b.path, "rb") as fb:
                    while True:
                        ca = fa.read(1024 * 1024)
                        cb = fb.read(1024 * 1024)
                        if ca != cb:
                            return False
                        if not ca:
                            break
            else:
                return False
        return True

    def freeze_tree(self, path: Path) -> None:
        path = self.assert_directory(path)
        for root, dirs, files in os.walk(path, topdown=False, followlinks=False):
            for name in files:
                file_path = Path(root) / name
                st = os.lstat(file_path)
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                    raise SecurityError(f"Unexpected file type in release: {file_path}")
                executable = bool(st.st_mode & 0o111)
                os.chmod(file_path, 0o555 if executable else 0o444, follow_symlinks=False)
            for name in dirs:
                dir_path = Path(root) / name
                st = os.lstat(dir_path)
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                    raise SecurityError(f"Unexpected path in release: {dir_path}")
                os.chmod(dir_path, 0o555, follow_symlinks=False)
        os.chmod(path, 0o555, follow_symlinks=False)

    def replace_symlink(self, destination: Path, target: str, allowed_existing_prefix: str | None = None) -> None:
        destination = _absolute(destination)
        self.anchor_for(destination)
        parent_fd = self._open_dir(destination.parent, create=True)
        name = destination.name
        _reject_bad_component(name)
        temp_name = f".{name}.link-{uuid.uuid4().hex}"
        previous: str | None = None
        try:
            try:
                st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                st = None
            if st is not None:
                if not stat.S_ISLNK(st.st_mode):
                    raise SecurityError(f"Refusing to replace non-symlink command path: {destination}")
                previous = os.readlink(name, dir_fd=parent_fd)
                if allowed_existing_prefix and not previous.startswith(allowed_existing_prefix):
                    raise SecurityError(
                        f"Refusing to replace symlink outside Station ownership: {destination} -> {previous}"
                    )
            if not self._rolling_back:
                self.journal.previous_links.setdefault(destination, previous)
            os.symlink(target, temp_name, dir_fd=parent_fd)
            os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)

    def rollback(self) -> None:
        """Best-effort rollback of Station-owned filesystem changes."""

        self._rolling_back = True
        try:
            for path, previous in reversed(list(self.journal.previous_links.items())):
                try:
                    parent_fd = self._open_dir(path.parent, create=False)
                    try:
                        try:
                            os.unlink(path.name, dir_fd=parent_fd)
                        except FileNotFoundError:
                            pass
                        if previous is not None:
                            os.symlink(previous, path.name, dir_fd=parent_fd)
                    finally:
                        os.close(parent_fd)
                except Exception:
                    pass
            for path, (payload, mode, uid, gid) in reversed(list(self.journal.replaced_files.items())):
                try:
                    self._atomic_write(path, payload, mode, (uid, gid))
                except Exception:
                    pass
            for path in reversed(self.journal.created_files):
                try:
                    st = os.lstat(path)
                    if stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                        os.unlink(path)
                except OSError:
                    pass
            for path in sorted(set(self.journal.created_dirs), key=lambda p: len(p.parts), reverse=True):
                try:
                    st = os.lstat(path)
                except FileNotFoundError:
                    continue
                try:
                    if stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode):
                        self.remove_tree_strict(path)
                except OSError:
                    pass
                except SecurityError:
                    pass
        finally:
            self._rolling_back = False


def ensure_no_symlinks(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.exists():
        return found
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(current) / name
            if path.is_symlink():
                found.append(path)
    return found
