"""Cross-platform PID lock for ctx write operations."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


STALE_TIMEOUT_SECONDS = 30


@dataclass
class LockInfo:
    """Contents of a lock file."""

    pid: int
    timestamp: float
    command: str


class LockHeldError(Exception):
    """Raised when another process already holds the ctx lock."""

    def __init__(self, info: LockInfo) -> None:
        self.info = info
        super().__init__(
            f"Lock held by PID {info.pid} (command: {info.command}, since {info.timestamp:.0f})"
        )


class CtxLock:
    """Cross-platform file lock based on a PID file."""

    def __init__(self, root: Path, *, command: str) -> None:
        self._root = root
        self._command = command
        self._lock_path = root / ".ctx-cache" / "lock"

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
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _write_lock(self) -> None:
        info = LockInfo(pid=os.getpid(), timestamp=time.time(), command=self._command)
        content = (
            f"pid={info.pid}\n"
            f"timestamp={info.timestamp}\n"
            f"command={info.command}\n"
        )
        self._lock_path.write_text(content, encoding="utf-8")

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
        if time.time() - info.timestamp > STALE_TIMEOUT_SECONDS:
            return True
        return not self._pid_alive(info.pid)

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

        if self._lock_path.exists():
            existing = self._read_lock()
            if existing is None:
                try:
                    self._lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
            elif self._is_stale(existing):
                self._lock_path.unlink(missing_ok=True)
            else:
                raise LockHeldError(existing)

        self._write_lock()

        actual = self._read_lock()
        if actual is None or actual.pid != os.getpid():
            raise LockHeldError(actual or LockInfo(pid=0, timestamp=0.0, command="unknown"))

    def release(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> "CtxLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
