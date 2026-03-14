"""Tests for ctx.watcher — focuses on the event-filtering and debounce logic."""
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ctx.watcher import _DebounceHandler, _should_process_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeEvent:
    """Minimal stand-in for FileSystemEvent used in tests."""
    def __init__(self, path: Path, *, is_directory: bool = False) -> None:
        self.src_path = str(path)
        self.is_directory = is_directory


def _make_event(path: str | Path, *, is_directory: bool = False) -> _FakeEvent:
    return _FakeEvent(Path(path), is_directory=is_directory)


def _load_spec(root: Path):
    from ctx.ignore import load_ignore_patterns
    return load_ignore_patterns(root)


# ---------------------------------------------------------------------------
# _should_process_event
# ---------------------------------------------------------------------------

def test_ignores_context_md(tmp_path):
    spec = _load_spec(tmp_path)
    event = _make_event(tmp_path / "src" / "CONTEXT.md")
    assert _should_process_event(event, tmp_path, spec) is False


def test_ignores_directory_events(tmp_path):
    spec = _load_spec(tmp_path)
    event = _make_event(tmp_path / "src", is_directory=True)
    assert _should_process_event(event, tmp_path, spec) is False


def test_accepts_regular_source_file(tmp_path):
    spec = _load_spec(tmp_path)
    event = _make_event(tmp_path / "src" / "main.py")
    assert _should_process_event(event, tmp_path, spec) is True


def test_ignores_ctxignored_path(tmp_path):
    # Write a .ctxignore that ignores *.log
    (tmp_path / ".ctxignore").write_text("*.log\n", encoding="utf-8")
    spec = _load_spec(tmp_path)
    event = _make_event(tmp_path / "app.log")
    assert _should_process_event(event, tmp_path, spec) is False


# ---------------------------------------------------------------------------
# _DebounceHandler
# ---------------------------------------------------------------------------

def test_debounce_calls_on_change_once_for_rapid_events(tmp_path):
    """Multiple events for the same file within the debounce window → one callback."""
    spec = _load_spec(tmp_path)
    calls: list[Path] = []
    handler = _DebounceHandler(tmp_path, spec, on_change=calls.append)

    target = tmp_path / "module.py"
    for _ in range(5):
        handler.on_modified(_make_event(target))

    # Wait for debounce to fire (0.5 s + margin)
    time.sleep(0.8)
    assert calls == [target]


def test_debounce_fires_separately_for_different_files(tmp_path):
    """Events for two distinct files each fire their own callback."""
    spec = _load_spec(tmp_path)
    calls: list[Path] = []
    handler = _DebounceHandler(tmp_path, spec, on_change=calls.append)

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    handler.on_modified(_make_event(a))
    handler.on_modified(_make_event(b))

    time.sleep(0.8)
    assert set(calls) == {a, b}


def test_on_change_not_called_for_context_md(tmp_path):
    """CONTEXT.md events must never reach on_change."""
    spec = _load_spec(tmp_path)
    calls: list[Path] = []
    handler = _DebounceHandler(tmp_path, spec, on_change=calls.append)

    handler.on_modified(_make_event(tmp_path / "CONTEXT.md"))
    time.sleep(0.8)
    assert calls == []


def test_on_moved_schedules_both_paths(tmp_path):
    """A move event schedules debounce for both src and dest."""
    spec = _load_spec(tmp_path)
    calls: list[Path] = []
    handler = _DebounceHandler(tmp_path, spec, on_change=calls.append)

    src = tmp_path / "old.py"
    dest = tmp_path / "new.py"

    move_event = MagicMock()
    move_event.src_path = str(src)
    move_event.dest_path = str(dest)
    move_event.is_directory = False

    handler.on_moved(move_event)
    time.sleep(0.8)
    assert set(calls) == {src, dest}
