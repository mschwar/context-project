"""File watcher for ctx watch command.

Monitors a directory tree for changes and triggers incremental manifest
regeneration when source files are modified.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

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


def _print_coverage_summary(root: Path, spec: object) -> None:
    """Print a one-line coverage summary after a watch refresh."""
    import os
    import re as _re

    dirs_total = 0
    dirs_covered = 0
    dirs_stale = 0
    tokens_total = 0

    _tokens_re = _re.compile(r"^tokens_total:\s*(\d+)", _re.MULTILINE)

    for dirpath, dirnames, _ in os.walk(root):
        d = Path(dirpath)
        # Prune ignored subdirectories in-place
        dirnames[:] = [
            dn for dn in sorted(dirnames)
            if not should_ignore(d / dn, spec, root)
        ]

        dirs_total += 1
        manifest = d / "CONTEXT.md"

        if not manifest.exists():
            continue

        dirs_covered += 1
        try:
            text = manifest.read_text(encoding="utf-8")
            m = _tokens_re.search(text)
            if m:
                tokens_total += int(m.group(1))
        except (OSError, UnicodeDecodeError):
            pass

        # Check if stale using mtime comparison
        try:
            manifest_mtime = manifest.stat().st_mtime
            is_stale_dir = any(
                f.stat().st_mtime > manifest_mtime
                for f in d.iterdir()
                if f.is_file() and f.name != "CONTEXT.md"
            )
            if is_stale_dir:
                dirs_stale += 1
        except OSError:
            pass

    print(f"  coverage: {dirs_covered}/{dirs_total} dirs covered, {dirs_stale} stale, {tokens_total:,} tokens")


class _DebounceHandler(FileSystemEventHandler):
    """Debounces rapid file events and calls on_change(changed_path) once settled."""

    def __init__(
        self,
        root: Path,
        spec: "pathspec.PathSpec",
        on_change: Callable[[Path], None],
        debounce_seconds: float = _DEBOUNCE_SECONDS,
    ) -> None:
        super().__init__()
        self._root = root
        self._spec = spec
        self._on_change = on_change
        self._debounce_seconds = debounce_seconds
        self._pending: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: Path) -> None:
        with self._lock:
            existing = self._pending.pop(path, None)
            if existing:
                existing.cancel()
            timer = threading.Timer(self._debounce_seconds, self._fire, args=[path])
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
    client: "LLMClient",
    spec: "pathspec.PathSpec",
    *,
    echo: Callable[[str], None] = None,
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
        _print_coverage_summary(root, spec)

    handler = _DebounceHandler(root, spec, on_change, debounce_seconds=config.watch_debounce_seconds)
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
