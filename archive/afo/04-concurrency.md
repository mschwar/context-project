# AFO Spec 04 — Concurrency

> **Status:** Canonical
> **Scope:** Cross-cutting (Stages 1-3, 5)
> **Prerequisites:** Read 00-conventions.md first

---

## 1. Overview

Two concurrency problems need solving:

1. **Write conflicts**: Two `ctx refresh` runs on the same tree can corrupt CONTEXT.md files.
2. **Partial writes**: A crash during `write_manifest` can leave a truncated CONTEXT.md.

This spec introduces a PID-based lockfile and atomic writes via `os.replace`.

---

## 2. New File: `src/ctx/lock.py`

### 2.1 CtxLock Class

```python
@dataclass
class LockInfo:
    """Contents of a lock file."""
    pid: int
    timestamp: float  # time.time() when lock was acquired
    command: str       # e.g., "refresh", "reset"


class CtxLock:
    """Cross-platform file lock using PID files.

    Usage:
        with CtxLock(root, command="refresh") as lock:
            # ... perform writes ...
        # lock released on exit

    Raises:
        LockHeldError: Another process holds the lock and it is not stale.
    """
```

### 2.2 Lock File Location

```
<root>/.ctx-cache/lock
```

The `.ctx-cache/` directory already exists (used for `llm_cache.json`). The lock file lives alongside the cache.

### 2.3 Lock File Format

Plain text, one field per line:

```
pid=12345
timestamp=1742234567.89
command=refresh
```

This is intentionally not JSON — it must be parseable even if partially written.

### 2.4 Acquisition Algorithm

```python
def acquire(self) -> None:
    lock_path = self._root / ".ctx-cache" / "lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Check for existing lock
    if lock_path.exists():
        existing = self._read_lock(lock_path)
        if existing is not None:
            # 2. Check staleness
            if self._is_stale(existing):
                # Stale lock — steal it
                lock_path.unlink(missing_ok=True)
            else:
                raise LockHeldError(existing)

    # 3. Write our lock
    self._write_lock(lock_path)

    # 4. Re-read and verify it's ours (race guard)
    actual = self._read_lock(lock_path)
    if actual is None or actual.pid != os.getpid():
        raise LockHeldError(actual or LockInfo(pid=0, timestamp=0, command="unknown"))
```

### 2.5 Staleness Detection

A lock is stale if **either**:

1. The PID in the lock file is no longer running (checked via `os.kill(pid, 0)` on POSIX, `ctypes.windll.kernel32.OpenProcess` on Windows), OR
2. The timestamp is more than **30 seconds** old.

```python
STALE_TIMEOUT_SECONDS = 30

def _is_stale(self, info: LockInfo) -> bool:
    # Time-based check
    if time.time() - info.timestamp > STALE_TIMEOUT_SECONDS:
        return True
    # PID-based check
    return not self._pid_alive(info.pid)

def _pid_alive(self, pid: int) -> bool:
    """Check if a process is still running. Cross-platform."""
    if os.name == "nt":
        # Windows: use ctypes
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    else:
        # POSIX: signal 0 checks existence
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # Process exists but we can't signal it
```

### 2.6 Release

```python
def release(self) -> None:
    lock_path = self._root / ".ctx-cache" / "lock"
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass  # Best-effort cleanup
```

### 2.7 Context Manager Protocol

```python
def __enter__(self) -> "CtxLock":
    self.acquire()
    return self

def __exit__(self, *exc_info) -> None:
    self.release()
```

### 2.8 LockHeldError

```python
class LockHeldError(Exception):
    """Raised when another process holds the ctx lock."""
    def __init__(self, info: LockInfo) -> None:
        self.info = info
        super().__init__(
            f"Lock held by PID {info.pid} (command: {info.command}, "
            f"since {info.timestamp:.0f})"
        )
```

When caught by the OutputBroker, this maps to error code `lock_held`.

---

## 3. Lock Scope by Command

| Command | Acquires Lock? | Reason |
|---------|---------------|--------|
| `refresh` | **Yes** | Writes CONTEXT.md files. |
| `reset` | **Yes** | Deletes CONTEXT.md files. |
| `check` | No | Read-only. |
| `export` | No | Read-only. |
| `serve` | No | Read-only per request. |
| `watch` (refresh cycle) | **Yes, per cycle** | Lock acquired at start of each `update_tree` call, released after. Not held for the entire watch session. |

### Watch Lock Behavior

The `watch` command runs indefinitely. It must NOT hold the lock for the entire session. Instead:

```python
def on_change(changed_path):
    try:
        with CtxLock(root, command="watch"):
            stats = update_tree(root, config, client, spec, changed_files=[changed_path])
    except LockHeldError:
        echo("  skipped: another ctx process is running")
```

This allows a user to run `ctx refresh` while `ctx watch` is running — the watch cycle will skip that one update gracefully.

---

## 4. Atomic Writes in `manifest.py`

### Current Code (line 152)

```python
(path / "CONTEXT.md").write_text(content, encoding="utf-8")
```

### New Code

```python
import os
import tempfile

target = path / "CONTEXT.md"
# Write to a temporary file in the same directory, then atomically replace.
# os.replace() is atomic on both Windows and POSIX when source and destination
# are on the same filesystem (which they always are here — same directory).
fd, tmp_path = tempfile.mkstemp(
    prefix=".CONTEXT.md.",
    suffix=".tmp",
    dir=str(path),
)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, str(target))
except BaseException:
    # Clean up the temp file on any failure
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise
```

### Why `os.replace` and not `os.rename`

- `os.rename` on Windows raises `FileExistsError` if the target exists.
- `os.replace` atomically replaces the target on both Windows and POSIX.
- Both are atomic when source and destination are on the same filesystem.
- Using the same directory for the temp file guarantees same-filesystem.

---

## 5. Integration Points

### 5.1 `api.py` (Stage 2)

Each API function that writes manifests wraps its work in a `CtxLock`:

```python
def refresh(root: Path, ...) -> RefreshResult:
    with CtxLock(root, command="refresh"):
        stats = generate_tree(root, config, client, spec, ...)
        # ... build result ...
```

### 5.2 `output.py` (Stage 1)

The OutputBroker's exception classifier maps `LockHeldError` to error code `lock_held`:

```python
if isinstance(exc, LockHeldError):
    return ("lock_held", str(exc), "Wait and retry, or check for stuck processes.")
```

### 5.3 `watcher.py` (existing)

Modify `run_watch` → `on_change` to acquire/release the lock per cycle (see Section 3).

---

## 6. Files

### New

| File | Description |
|------|-------------|
| `src/ctx/lock.py` | `CtxLock`, `LockHeldError`, `LockInfo` |
| `tests/test_lock.py` | Lock acquisition, staleness, release, and contention tests |

### Modified

| File | Changes |
|------|---------|
| `src/ctx/manifest.py` | `write_manifest` uses atomic temp-file + `os.replace` (line 152) |
| `src/ctx/watcher.py` | `on_change` wraps `update_tree` in `CtxLock` |

---

## 7. Test Cases for `test_lock.py`

1. **Basic acquire/release**: Lock acquired, lock file exists, release removes it.
2. **Double acquire same process**: Second acquire in same process raises `LockHeldError`.
3. **Lock file content**: Written file contains correct PID, timestamp, and command.
4. **Stale lock — dead PID**: Lock file with non-existent PID → acquisition succeeds (steals lock).
5. **Stale lock — old timestamp**: Lock file with timestamp > 30s ago → acquisition succeeds.
6. **Fresh lock — alive PID**: Lock file with current PID and recent timestamp → `LockHeldError`.
7. **Context manager cleanup**: Lock is released even when an exception occurs inside the `with` block.
8. **Lock directory creation**: `.ctx-cache/` is created if it doesn't exist.
9. **Concurrent simulation**: Use `monkeypatch` to simulate a foreign PID holding the lock; verify `LockHeldError` is raised with correct `info`.
10. **Watch per-cycle locking**: Simulate two sequential watch cycles — each acquires and releases independently.

### Platform-Specific Tests

- Test `_pid_alive` on the current platform (Windows or POSIX).
- Mock the other platform's check to ensure the fallback works.

---

## 8. Edge Cases

### Race Condition on Acquisition

Two processes check for the lock file simultaneously, both see it absent, both write. The re-read step (Section 2.4, step 4) mitigates this: the process whose PID is in the file after writing wins. The loser raises `LockHeldError`.

This is not a perfect mutex — there's a small window — but for ctx's use case (developer-initiated CLI runs), it's sufficient. A true filesystem mutex requires platform-specific APIs (`fcntl.flock` on POSIX, `LockFileEx` on Windows), which this spec deliberately avoids for simplicity.

### Lock File Corruption

If the lock file exists but is unparseable (e.g., partially written), treat it as stale and overwrite it.

### `.ctx-cache/` Permissions

If the directory is read-only, the lock acquisition fails with a clear error. The OutputBroker wraps this as `unknown_error` with a hint about directory permissions.
