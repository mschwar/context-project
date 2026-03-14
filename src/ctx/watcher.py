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
        # A move event affects the parent directories of both the source and destination.
        # The event passed to on_moved is a FileSystemMovedEvent, which guarantees dest_path.
        paths_to_process = {Path(event.src_path), Path(event.dest_path)}

        for path in paths_to_process:
            # We can't use _should_process_event as it filters out directories,
            # but we need to trigger updates for parents of moved directories.
            if path.name == "CONTEXT.md" or should_ignore(path, self._spec, self._root):
                continue
            
            # Scheduling the moved path will cause update_tree to process its parent.
            self._schedule(path)


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
