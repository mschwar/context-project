"""File watcher for ctx watch command.

Monitors a directory tree for changes and triggers incremental manifest
regeneration when source files are modified.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ctx.config import Config
from ctx.ignore import should_ignore


# How long to wait after the last file event before triggering regeneration.
_DEBOUNCE_SECONDS = 0.5


def _should_process_event(event: FileSystemEvent, root: Path, spec: object) -> bool:
    """Return True if this filesystem event should trigger a regeneration."""
    if event.is_directory:
        return False
    path = Path(event.src_path)
    # Never react to CONTEXT.md writes — that would cause an infinite loop.
    if path.name == "CONTEXT.md":
        return False
    # Respect ctxignore patterns.
    if should_ignore(path, spec, root):
        return False
    return True


class _DebounceHandler(FileSystemEventHandler):
    """Debounces rapid file events and calls on_change(changed_path) once settled."""

    def __init__(
        self,
        root: Path,
        spec: object,
        on_change: object,
    ) -> None:
        super().__init__()
        self._root = root
        self._spec = spec
        self._on_change = on_change
        self._pending: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: Path) -> None:
        with self._lock:
            existing = self._pending.pop(path, None)
            if existing:
                existing.cancel()
            timer = threading.Timer(_DEBOUNCE_SECONDS, self._fire, args=[path])
            self._pending[path] = timer
            timer.start()

    def _fire(self, path: Path) -> None:
        with self._lock:
            self._pending.pop(path, None)
        self._on_change(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if _should_process_event(event, self._root, self._spec):
            self._schedule(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if _should_process_event(event, self._root, self._spec):
            self._schedule(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if _should_process_event(event, self._root, self._spec):
            self._schedule(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        # Treat a move as a deletion of the source and creation of the dest.
        src = Path(event.src_path)
        dest = Path(getattr(event, "dest_path", event.src_path))
        for path in (src, dest):
            fake = _FakeEvent(path, is_directory=event.is_directory)
            if _should_process_event(fake, self._root, self._spec):
                self._schedule(path)


class _FakeEvent:
    """Minimal stand-in for FileSystemEvent used in on_moved."""

    def __init__(self, path: Path, *, is_directory: bool) -> None:
        self.src_path = str(path)
        self.is_directory = is_directory


def run_watch(
    root: Path,
    config: Config,
    client: object,
    spec: object,
    *,
    echo: object = None,
) -> None:
    """Start watching root and regenerate manifests on file changes.

    Blocks until the user presses Ctrl+C.

    Args:
        root: Directory tree to watch.
        config: Loaded ctx config.
        client: LLM client (CachingLLMClient or similar).
        spec: Compiled ignore spec from load_ignore_patterns.
        echo: Callable for printing status lines. Defaults to print.
    """
    import click
    from ctx.generator import update_tree

    if echo is None:
        echo = click.echo

    def on_change(changed_path: Path) -> None:
        echo(f"  change detected: {changed_path.relative_to(root)}")
        stats = update_tree(root, config, client, spec, changed_files=[changed_path])
        if stats.dirs_processed:
            echo(f"  refreshed {stats.dirs_processed} director{'y' if stats.dirs_processed == 1 else 'ies'}")
        if stats.errors:
            for err in stats.errors:
                echo(f"  error: {err}")

    handler = _DebounceHandler(root, spec, on_change)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    echo(f"ctx watch: watching {root}  (Ctrl+C to stop)")
    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        echo("ctx watch: stopped")
