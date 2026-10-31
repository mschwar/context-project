"""Cross-platform PID lock for ctx write operations."""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


STALE_TIMEOUT_SECONDS = 900
HEARTBEAT_INTERVAL_SECONDS = 15.0
_INIT_GRACE_SECONDS = 2.0
_RECLAIM_STALE_SECONDS = 5.0


@dataclass
class LockInfo:
    """Contents of a lock file."""

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
    """Cross-platform exclusive file lock based on O_CREAT|O_EXCL PID file with active heartbeat."""

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
        self._reclaim_path = root / ".ctx-cache" / ".lock.reclaim"
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
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

    def _try_create_exclusive(self) -> bool:
        """Create the lock file exclusively with O_CREAT | O_EXCL. Returns True on success."""
        try:
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        try:
            os.write(fd, self._format_payload().encode("utf-8"))
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            self._lock_path.unlink(missing_ok=True)
            raise
        else:
            os.close(fd)
        return True

    def _refresh_owned_lock(self) -> None:
        """Atomically refresh timestamp on a lock already exclusively owned by this instance."""
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
                    if not self._held:
                        return
                    existing = self._read_lock()
                    if not self._owns_lock(existing):
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

    def _acquire_reclaim_guard(self) -> int | None:
        """Acquire exclusive stale-lock reclamation guard, clearing abandoned guards."""
        for _ in range(2):
            try:
                return os.open(
                    str(self._reclaim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
                )
            except FileExistsError:
                try:
                    age = time.time() - self._reclaim_path.stat().st_mtime
                except OSError:
                    continue
                if age > _RECLAIM_STALE_SECONDS:
                    try:
                        self._reclaim_path.unlink(missing_ok=True)
                    except OSError:
                        return None
                    continue
                return None
            except OSError:
                return None
        return None

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

        for _attempt in range(6):
            if self._try_create_exclusive():
                with self._state_lock:
                    self._held = True
                self._start_heartbeat()
                return

            # Lock file exists: inspect holder. Allow brief grace period if another
            # process just created the O_EXCL file and is still writing its payload.
            existing = self._read_lock()
            if existing is None:
                try:
                    mtime = self._lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise LockHeldError(
                        LockInfo(pid=0, timestamp=time.time(), command="unknown")
                    ) from exc

                if time.time() - mtime < _INIT_GRACE_SECONDS:
                    time.sleep(0.02)
                    existing = self._read_lock()
                    if existing is None and self._lock_path.exists():
                        raise LockHeldError(
                            LockInfo(pid=0, timestamp=mtime, command="initializing")
                        )

            if existing is not None and not self._is_stale(existing):
                raise LockHeldError(existing)

            # Existing lock is stale or corrupt (> grace window): serialize reclamation
            # via an exclusive guard file so concurrent reclaimers never unlink a fresh lock.
            guard_fd = self._acquire_reclaim_guard()
            if guard_fd is None:
                time.sleep(0.02)
                continue
            try:
                os.close(guard_fd)
                recheck = self._read_lock()
                if recheck is not None and not self._is_stale(recheck):
                    raise LockHeldError(recheck)
                if recheck is None:
                    try:
                        if time.time() - self._lock_path.stat().st_mtime < _INIT_GRACE_SECONDS:
                            raise LockHeldError(
                                LockInfo(pid=0, timestamp=time.time(), command="initializing")
                            )
                    except FileNotFoundError:
                        pass
                self._lock_path.unlink(missing_ok=True)
                if self._try_create_exclusive():
                    with self._state_lock:
                        self._held = True
                    self._start_heartbeat()
                    return
            finally:
                self._reclaim_path.unlink(missing_ok=True)

        existing = self._read_lock()
        raise LockHeldError(
            existing or LockInfo(pid=0, timestamp=time.time(), command="contended")
        )

    def release(self) -> None:
        self._stop_heartbeat()
        with self._state_lock:
            was_held = self._held
            self._held = False
            try:
                existing = self._read_lock()
                if self._owns_lock(existing) or (was_held and existing is None):
                    self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self) -> "CtxLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
