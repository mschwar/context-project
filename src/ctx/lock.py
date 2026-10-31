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


def try_acquire_os_lock(guard_path: Path) -> int | None:
    """Acquire a non-blocking OS kernel exclusive lock on a persistent guard inode.

    The guard file is never unlinked during normal operation so all contenders lock
    the exact same inode without check-then-unlink or publication races.
    Returns the open locked file descriptor on success, or None if already held.
    """
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
        return fd
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass
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
                if was_held:
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
