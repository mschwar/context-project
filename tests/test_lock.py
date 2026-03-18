"""Tests for ctx.lock CtxLock."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from ctx.lock import CtxLock, LockHeldError


def _lock_path(root: Path) -> Path:
    return root / ".ctx-cache" / "lock"


def _write_lock_file(root: Path, *, pid: int, timestamp: float, command: str) -> None:
    path = _lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"pid={pid}\n"
        f"timestamp={timestamp}\n"
        f"command={command}\n",
        encoding="utf-8",
    )


def test_lock_basic_acquire_release(tmp_path) -> None:
    lock = CtxLock(tmp_path, command="refresh")
    lock.acquire()
    assert _lock_path(tmp_path).exists()
    lock.release()
    assert not _lock_path(tmp_path).exists()


def test_lock_double_acquire_same_process_raises(tmp_path) -> None:
    first = CtxLock(tmp_path, command="refresh")
    second = CtxLock(tmp_path, command="refresh")

    first.acquire()
    with pytest.raises(LockHeldError):
        second.acquire()
    first.release()


def test_lock_file_content(tmp_path) -> None:
    with CtxLock(tmp_path, command="refresh"):
        content = _lock_path(tmp_path).read_text(encoding="utf-8")

    assert f"pid={os.getpid()}" in content
    assert "timestamp=" in content
    assert "command=refresh" in content


def test_lock_stale_dead_pid_is_stolen(tmp_path, monkeypatch) -> None:
    _write_lock_file(tmp_path, pid=99999, timestamp=time.time(), command="refresh")
    lock = CtxLock(tmp_path, command="refresh")
    monkeypatch.setattr(lock, "_pid_alive", lambda _pid: False)

    lock.acquire()
    assert _lock_path(tmp_path).exists()
    lock.release()


def test_lock_stale_old_timestamp_is_stolen(tmp_path) -> None:
    _write_lock_file(
        tmp_path,
        pid=os.getpid(),
        timestamp=time.time() - 120.0,
        command="refresh",
    )
    with CtxLock(tmp_path, command="refresh"):
        assert _lock_path(tmp_path).exists()


def test_lock_fresh_alive_pid_raises(tmp_path, monkeypatch) -> None:
    _write_lock_file(
        tmp_path,
        pid=os.getpid(),
        timestamp=time.time(),
        command="refresh",
    )
    lock = CtxLock(tmp_path, command="refresh")
    monkeypatch.setattr(lock, "_pid_alive", lambda _pid: True)

    with pytest.raises(LockHeldError):
        lock.acquire()


def test_lock_context_manager_releases_on_exception(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        with CtxLock(tmp_path, command="refresh"):
            raise RuntimeError("boom")

    assert not _lock_path(tmp_path).exists()


def test_lock_creates_lock_directory(tmp_path) -> None:
    assert not (tmp_path / ".ctx-cache").exists()
    with CtxLock(tmp_path, command="refresh"):
        assert (tmp_path / ".ctx-cache").exists()


def test_lock_concurrent_simulation_reports_holder_info(tmp_path, monkeypatch) -> None:
    _write_lock_file(
        tmp_path,
        pid=424242,
        timestamp=time.time(),
        command="refresh",
    )
    lock = CtxLock(tmp_path, command="refresh")
    monkeypatch.setattr(lock, "_pid_alive", lambda _pid: True)

    with pytest.raises(LockHeldError) as excinfo:
        lock.acquire()

    assert excinfo.value.info.pid == 424242
    assert excinfo.value.info.command == "refresh"


def test_lock_watch_per_cycle_locking(tmp_path) -> None:
    with CtxLock(tmp_path, command="watch"):
        assert _lock_path(tmp_path).exists()
    assert not _lock_path(tmp_path).exists()

    with CtxLock(tmp_path, command="watch"):
        assert _lock_path(tmp_path).exists()
    assert not _lock_path(tmp_path).exists()
