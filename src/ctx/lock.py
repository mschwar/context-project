"""Cross-platform kernel-backed file lock for ctx write operations."""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


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

        if _same_guard_inode(fd, guard_path):
            try:
                os.utime(fd, None)
            except OSError:
                try:
                    os.utime(guard_path, None)
                except OSError:
                    pass
            return fd
        release_os_lock(fd)

    return None


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
                with self._state_lock:
                    if not self._held or self._os_fd is None:
                        return
                    if not _same_guard_inode(self._os_fd, self._guard_path) or not self._owns_lock(
                        self._read_lock()
                    ):
                        # Our lock was superseded after exceeding STALE_TIMEOUT_SECONDS while frozen.
                        self._held = False
                        return
                    try:
                        self._refresh_owned_lock()
                    except OSError:
                        return

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
        """Return True only when BOTH lock metadata and the active guard inode exceed STALE_TIMEOUT_SECONDS."""
        if info is None:
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
        reclaim_fd = try_acquire_os_lock(self._reclaim_guard_path)
        if reclaim_fd is None:
            raise LockHeldError(initial_existing)

        new_os_fd: int | None = None
        tmp_guard = self._lock_path.parent / f".lock.guard.{os.getpid()}.{uuid.uuid4().hex}"
        try:
            # Brief yield under reclaim_fd ensures any fresh winner that acquired flock nanoseconds
            # ago has completed os.utime(fd, None) and metadata publication before we re-check.
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
                    self._refresh_owned_lock()
                return direct_fd

            recheck = self._read_lock()
            if not self._is_frozen_guard_holder(recheck):
                raise LockHeldError(recheck or initial_existing)

            # Lock the replacement guard inode BEFORE atomically publishing it at self._guard_path
            # so there is zero unlocked window between contenders before and after os.replace().
            new_os_fd = try_acquire_os_lock(tmp_guard)
            if new_os_fd is None:
                raise LockHeldError(recheck or initial_existing)

            os.replace(tmp_guard, self._guard_path)
            with self._state_lock:
                self._os_fd = new_os_fd
                self._held = True
                self._refresh_owned_lock()
            return new_os_fd
        except LockHeldError:
            if new_os_fd is not None and not self._held:
                release_os_lock(new_os_fd)
            tmp_guard.unlink(missing_ok=True)
            raise
        except Exception:
            with self._state_lock:
                self._held = False
                self._os_fd = None
            if new_os_fd is not None:
                release_os_lock(new_os_fd)
            tmp_guard.unlink(missing_ok=True)
            raise
        finally:
            release_os_lock(reclaim_fd)

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
                self._start_heartbeat()
                return
            raise LockHeldError(
                existing or LockInfo(pid=0, timestamp=time.time(), command="active")
            )

        try:
            existing = self._read_lock()
            if existing is not None and not self._is_stale(existing):
                release_os_lock(os_fd)
                raise LockHeldError(existing)

            with self._state_lock:
                self._os_fd = os_fd
                self._held = True
                self._refresh_owned_lock()
        except LockHeldError:
            raise
        except Exception:
            with self._state_lock:
                self._held = False
                self._os_fd = None
            release_os_lock(os_fd)
            raise

        self._start_heartbeat()

    def release(self) -> None:
        self._stop_heartbeat()
        with self._state_lock:
            was_held = self._held
            os_fd = self._os_fd
            self._held = False
            self._os_fd = None
            try:
                if was_held and os_fd is not None and _same_guard_inode(os_fd, self._guard_path):
                    existing = self._read_lock()
                    if existing is None or self._owns_lock(existing):
                        self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            finally:
                if os_fd is not None:
                    release_os_lock(os_fd)

    def __enter__(self) -> "CtxLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
