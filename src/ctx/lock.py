"""Cross-platform kernel-backed file lock for ctx write operations."""

from __future__ import annotations

import os
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


STALE_TIMEOUT_SECONDS = 900
HEARTBEAT_INTERVAL_SECONDS = 15.0


def _same_guard_inode(fd: int, guard_path: Path) -> bool:
    """Return True if *fd* still refers to the current directory entry at *guard_path*."""
    if os.name == "nt":
        return guard_path.exists()
    try:
        fd_stat = os.fstat(fd)
        path_stat = os.stat(guard_path)
    except OSError:
        return False
    return fd_stat.st_dev == path_stat.st_dev and fd_stat.st_ino == path_stat.st_ino


def try_acquire_os_lock(guard_path: Path) -> int | None:
    """Acquire a non-blocking OS kernel exclusive lock on the current *guard_path* inode.

    The guard file is never unlinked during normal operation so all contenders lock
    the exact same inode without check-then-unlink or publication races. After acquiring
    the kernel lock, verifies the open descriptor still matches *guard_path*'s current
    inode (guarding against concurrent frozen-owner guard rotation).
    Returns the open locked file descriptor on success, or None if already held.
    """
    for _ in range(3):
        try:
            guard_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(guard_path), os.O_CREAT | os.O_RDWR, 0o644)
        except OSError:
            return None

        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            return None

        try:
            if _same_guard_inode(fd, guard_path):
                try:
                    if os.utime in os.supports_fd:
                        os.utime(fd, None)
                    else:
                        os.utime(guard_path, None)
                except (OSError, TypeError, NotImplementedError):
                    try:
                        os.utime(guard_path, None)
                    except OSError:
                        pass
                return fd
        except BaseException:
            release_os_lock(fd)
            raise
        release_os_lock(fd)

    return None


def acquire_os_lock_blocking(guard_path: Path) -> int:
    """Acquire a blocking OS kernel exclusive lock on the persistent *guard_path* inode."""
    while True:
        guard_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(guard_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            if os.name == "nt":
                import msvcrt

                while True:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.005)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        if _same_guard_inode(fd, guard_path):
            return fd
        release_os_lock(fd)


def release_os_lock(fd: int) -> None:
    """Unlock and close a file descriptor previously returned by try_acquire_os_lock()."""
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


@dataclass
class LockInfo:
    """Contents of a lock metadata file."""

    pid: int
    timestamp: float
    command: str
    token: str | None = None


class LockHeldError(Exception):
    """Raised when another process already holds the ctx lock."""

    def __init__(self, info: LockInfo) -> None:
        self.info = info
        super().__init__(
            f"Lock held by PID {info.pid} (command: {info.command}, since {info.timestamp:.0f})"
        )


class LockSupersededError(RuntimeError):
    """Raised when a CtxLock owner lost ownership after exceeding STALE_TIMEOUT_SECONDS."""


_ACTIVE_LOCKS: dict[Path, list["CtxLock"]] = {}
_ACTIVE_LOCKS_LOCK = threading.Lock()
_POST_FENCE_VALIDATION_HOOK: Callable[[Path], None] | None = None


def _register_active_lock(lock: "CtxLock") -> None:
    with _ACTIVE_LOCKS_LOCK:
        bucket = _ACTIVE_LOCKS.setdefault(lock._resolved_root, [])
        if lock not in bucket:
            bucket.append(lock)


def _unregister_active_lock(lock: "CtxLock") -> None:
    with _ACTIVE_LOCKS_LOCK:
        bucket = _ACTIVE_LOCKS.get(lock._resolved_root)
        if not bucket:
            return
        try:
            bucket.remove(lock)
        except ValueError:
            pass
        if not bucket:
            _ACTIVE_LOCKS.pop(lock._resolved_root, None)


def _applicable_active_locks(target_path: Path) -> list["CtxLock"]:
    with _ACTIVE_LOCKS_LOCK:
        if not _ACTIVE_LOCKS:
            return []
        snapshot = [(lock_root, list(locks)) for lock_root, locks in _ACTIVE_LOCKS.items()]

    resolved_target = target_path.resolve()
    applicable: list[CtxLock] = []
    for lock_root, locks in snapshot:
        if resolved_target == lock_root or resolved_target.is_relative_to(lock_root):
            applicable.extend(locks)
    if not applicable:
        caller_tid = threading.get_ident()
        for _, locks in snapshot:
            applicable.extend(lk for lk in locks if lk._owner_thread_id == caller_tid)
    return sorted(
        {id(lk): lk for lk in applicable}.values(),
        key=lambda lk: (str(lk._resolved_root), id(lk)),
    )


def assert_lock_ownership_for_path(target_path: Path) -> None:
    """Verify live ownership for any active CtxLock in this process covering *target_path*."""
    for active_lock in _applicable_active_locks(target_path):
        active_lock.verify_ownership()


@contextmanager
def lock_publication_fence_for_path(target_path: Path) -> Iterator[None]:
    """Hold non-rotatable reclaim kernel guards across ownership verification and atomic commit.

    Serializes publication syscalls (os.replace / unlink / mkdir / rmdir / rmtree) against
    _reclaim_frozen_owner() so a writer can never pass validation, freeze, be superseded,
    and then complete its write over a replacement owner's state.
    """
    applicable = _applicable_active_locks(target_path)
    hook = _POST_FENCE_VALIDATION_HOOK
    if not applicable:
        if hook is not None:
            hook(target_path)
        yield
        return

    with ExitStack() as stack:
        for active_lock in applicable:
            stack.enter_context(active_lock.publication_fence())
        if hook is not None:
            hook(target_path)
        yield


def fenced_replace(
    src_path: str | Path,
    dst_path: Path,
    *,
    fence_path: Path | None = None,
) -> None:
    """Atomically replace *dst_path* with *src_path* while holding the kernel publication fence."""
    with lock_publication_fence_for_path(fence_path or dst_path):
        os.replace(str(src_path), str(dst_path))


def fenced_unlink(
    target_path: Path,
    *,
    missing_ok: bool = True,
    fence_path: Path | None = None,
) -> None:
    """Unlink *target_path* while holding the kernel publication fence."""
    with lock_publication_fence_for_path(fence_path or target_path):
        target_path.unlink(missing_ok=missing_ok)


def fenced_mkdir(
    dir_path: Path,
    *,
    parents: bool = True,
    exist_ok: bool = True,
    fence_path: Path | None = None,
) -> None:
    """Ensure *dir_path* exists while holding the kernel publication fence."""
    check_path = fence_path or dir_path
    if dir_path.is_dir():
        assert_lock_ownership_for_path(check_path)
        return
    with lock_publication_fence_for_path(check_path):
        dir_path.mkdir(parents=parents, exist_ok=exist_ok)


class CtxLock:
    """Cross-platform exclusive file lock backed by OS kernel locking plus atomic metadata heartbeat."""

    def __init__(
        self,
        root: Path,
        *,
        command: str,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._root = root
        self._resolved_root = root.resolve()
        self._command = command
        self._lock_path = root / ".ctx-cache" / "lock"
        self._guard_path = root / ".ctx-cache" / ".lock.guard"
        self._reclaim_guard_path = root / ".ctx-cache" / ".lock.reclaim.guard"
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._os_fd: int | None = None
        self._held = False
        self._owner_thread_id: int | None = None
        self._token = f"{os.getpid()}:{uuid.uuid4().hex}"

    def _format_payload(self) -> str:
        now = time.time()
        return (
            f"pid={os.getpid()}\n"
            f"timestamp={now}\n"
            f"command={self._command}\n"
            f"token={self._token}\n"
        )

    def _owns_lock(self, info: LockInfo | None) -> bool:
        if info is None:
            return False
        if info.token is not None:
            return info.token == self._token
        return info.pid == os.getpid()

    def _read_lock(self) -> LockInfo | None:
        try:
            raw = self._lock_path.read_text(encoding="utf-8")
        except OSError:
            return None

        values: dict[str, str] = {}
        for line in raw.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        try:
            return LockInfo(
                pid=int(values["pid"]),
                timestamp=float(values["timestamp"]),
                command=values["command"],
                token=values.get("token") or None,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _refresh_owned_lock(self) -> None:
        """Atomically publish or refresh metadata while holding the OS kernel guard lock."""
        content = self._format_payload()
        tmp_path = self._lock_path.parent / f".lock.tmp.{os.getpid()}.{threading.get_ident()}"
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, self._lock_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _start_heartbeat(self) -> None:
        stop_event = threading.Event()
        self._heartbeat_stop = stop_event

        def _beat() -> None:
            while not stop_event.wait(self._heartbeat_interval):
                try:
                    with self.publication_fence():
                        self._refresh_owned_lock()
                except LockSupersededError:
                    return
                except OSError:
                    continue

        thread = threading.Thread(target=_beat, name="ctx-lock-heartbeat", daemon=True)
        self._heartbeat_thread = thread
        thread.start()

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def _pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False

        if os.name == "nt":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False

        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _is_stale(self, info: LockInfo) -> bool:
        if not self._pid_alive(info.pid):
            return True
        return time.time() - info.timestamp > STALE_TIMEOUT_SECONDS

    def _is_frozen_guard_holder(self, info: LockInfo | None) -> bool:
        """Return True on POSIX when BOTH lock metadata and the active guard inode exceed STALE_TIMEOUT_SECONDS.

        Live-process guard-inode rotation requires POSIX st_dev/st_ino identity and atomic os.replace()
        over open descriptors; on Windows, live lock holders report LockHeldError until the process exits
        (when the OS kernel automatically releases the msvcrt byte-range lock).
        """
        if os.name == "nt" or info is None:
            return False
        now = time.time()
        if (now - info.timestamp) <= STALE_TIMEOUT_SECONDS:
            return False
        try:
            guard_mtime = self._guard_path.stat().st_mtime
        except OSError:
            return False
        return (now - guard_mtime) > STALE_TIMEOUT_SECONDS

    def _reclaim_frozen_owner(self, initial_existing: LockInfo) -> int:
        """Atomically rotate the kernel guard inode when a live owner's heartbeat exceeds STALE_TIMEOUT_SECONDS."""
        if os.name == "nt":
            raise LockHeldError(initial_existing)
        reclaim_fd = try_acquire_os_lock(self._reclaim_guard_path)
        if reclaim_fd is None:
            raise LockHeldError(initial_existing)

        new_os_fd: int | None = None
        tmp_guard = self._lock_path.parent / f".lock.guard.{os.getpid()}.{uuid.uuid4().hex}"
        try:
            # Brief yield under reclaim_fd ensures any fresh winner that acquired flock nanoseconds
            # ago has completed os.utime and metadata publication before we re-check.
            time.sleep(0.002)

            # Re-try normal acquisition first in case the frozen holder exited while we acquired reclaim_fd.
            direct_fd = try_acquire_os_lock(self._guard_path)
            if direct_fd is not None:
                recheck = self._read_lock()
                if recheck is not None and not self._is_stale(recheck):
                    release_os_lock(direct_fd)
                    raise LockHeldError(recheck)
                with self._state_lock:
                    self._os_fd = direct_fd
                    self._held = True
                    self._owner_thread_id = threading.get_ident()
                    self._refresh_owned_lock()
                _register_active_lock(self)
                return direct_fd

            recheck = self._read_lock()
            if not self._is_frozen_guard_holder(recheck):
                raise LockHeldError(recheck or initial_existing)

            # Lock the replacement guard inode BEFORE atomically publishing it at self._guard_path
            # so there is zero unlocked window between contenders before and after os.replace().
            new_os_fd = try_acquire_os_lock(tmp_guard)
            if new_os_fd is None:
                raise LockHeldError(recheck or initial_existing)

            try:
                os.replace(tmp_guard, self._guard_path)
            except PermissionError as exc:
                raise LockHeldError(recheck or initial_existing) from exc
            with self._state_lock:
                self._os_fd = new_os_fd
                self._held = True
                self._owner_thread_id = threading.get_ident()
                self._refresh_owned_lock()
            _register_active_lock(self)
            return new_os_fd
        except LockHeldError:
            if new_os_fd is not None and not self._held:
                release_os_lock(new_os_fd)
            tmp_guard.unlink(missing_ok=True)
            raise
        except Exception:
            _unregister_active_lock(self)
            with self._state_lock:
                self._held = False
                self._os_fd = None
                self._owner_thread_id = None
            if new_os_fd is not None:
                release_os_lock(new_os_fd)
            tmp_guard.unlink(missing_ok=True)
            raise
        finally:
            release_os_lock(reclaim_fd)

    @contextmanager
    def publication_fence(self) -> Iterator[None]:
        """Hold the non-rotatable reclaim kernel guard across ownership verification and commit."""
        with self._state_lock:
            reclaim_fd = acquire_os_lock_blocking(self._reclaim_guard_path)
            try:
                still_owned = (
                    self._held
                    and self._os_fd is not None
                    and _same_guard_inode(self._os_fd, self._guard_path)
                    and self._owns_lock(self._read_lock())
                )
                if not still_owned:
                    self._held = False
                    raise LockSupersededError(
                        f"CtxLock on {self._root} (command: {self._command}, token: {self._token}) "
                        "was superseded after stale timeout; aborting write."
                    )
                yield
            finally:
                release_os_lock(reclaim_fd)

    def verify_ownership(self) -> None:
        """Verify this lock instance still owns the active kernel guard and metadata token."""
        with self.publication_fence():
            return

    def acquire(self) -> None:
        with self._state_lock:
            if self._held:
                existing = self._read_lock()
                raise LockHeldError(
                    existing or LockInfo(pid=os.getpid(), timestamp=time.time(), command=self._command)
                )

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        os_fd = try_acquire_os_lock(self._guard_path)
        if os_fd is None:
            existing = self._read_lock()
            if self._is_frozen_guard_holder(existing):
                assert existing is not None
                self._reclaim_frozen_owner(existing)
                try:
                    self._start_heartbeat()
                except BaseException:
                    self.release()
                    raise
                return
            raise LockHeldError(
                existing or LockInfo(pid=0, timestamp=time.time(), command="active")
            )

        reclaim_fd: int | None = None
        try:
            reclaim_fd = acquire_os_lock_blocking(self._reclaim_guard_path)
            if not _same_guard_inode(os_fd, self._guard_path):
                release_os_lock(os_fd)
                existing = self._read_lock()
                raise LockHeldError(
                    existing or LockInfo(pid=0, timestamp=time.time(), command="active")
                )
            existing = self._read_lock()
            if existing is not None and not self._is_stale(existing):
                release_os_lock(os_fd)
                raise LockHeldError(existing)

            with self._state_lock:
                self._os_fd = os_fd
                self._held = True
                self._owner_thread_id = threading.get_ident()
                self._refresh_owned_lock()
            _register_active_lock(self)
        except LockHeldError:
            raise
        except Exception:
            _unregister_active_lock(self)
            with self._state_lock:
                self._held = False
                self._os_fd = None
                self._owner_thread_id = None
            release_os_lock(os_fd)
            raise
        finally:
            if reclaim_fd is not None:
                release_os_lock(reclaim_fd)

        try:
            self._start_heartbeat()
        except BaseException:
            self.release()
            raise

    def release(self) -> None:
        self._stop_heartbeat()
        try:
            with self._state_lock:
                was_held = self._held
                os_fd = self._os_fd
                self._held = False
                self._os_fd = None
                self._owner_thread_id = None
                reclaim_fd: int | None = None
                try:
                    if was_held and os_fd is not None:
                        reclaim_fd = acquire_os_lock_blocking(self._reclaim_guard_path)
                        if _same_guard_inode(os_fd, self._guard_path):
                            existing = self._read_lock()
                            if existing is None or self._owns_lock(existing):
                                self._lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
                finally:
                    if reclaim_fd is not None:
                        release_os_lock(reclaim_fd)
                    if os_fd is not None:
                        release_os_lock(os_fd)
        finally:
            _unregister_active_lock(self)

    def __enter__(self) -> "CtxLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
