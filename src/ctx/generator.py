"""Core generation engine: walks a directory tree and produces CONTEXT.md files.

The generator is the heart of ctx. It orchestrates:
1. Bottom-up directory walk (leaves first).
2. File reading + binary detection.
3. LLM calls for summaries.
4. Manifest writing.
5. Progress reporting.

Key design: bottom-up traversal ensures child CONTEXT.md files exist before
the parent is generated, so parent summaries can reference child summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pathspec

from ctx.config import Config
from ctx.llm import LLMClient, FileSummary, SubdirSummary


@dataclass
class GenerateStats:
    """Stats accumulated during a generation run."""

    dirs_processed: int = 0
    dirs_skipped: int = 0
    files_processed: int = 0
    files_binary: int = 0
    tokens_used: int = 0
    errors: list[str] = field(default_factory=list)


# Type alias for progress callback: (current_dir, dirs_done, dirs_total)
ProgressCallback = Callable[[Path, int, int], None]


def generate_tree(
    root: Path,
    config: Config,
    client: LLMClient,
    spec: pathspec.PathSpec,
    *,
    progress: Optional[ProgressCallback] = None,
) -> GenerateStats:
    """Generate CONTEXT.md files for an entire directory tree.

    Args:
        root: Root directory to process.
        config: Resolved configuration.
        client: LLM client for summaries.
        spec: Ignore spec for filtering.
        progress: Optional callback for progress reporting.

    Returns:
        GenerateStats with totals for the run.

    Implementation:
        1. Collect all directories under root (respecting spec + max_depth).
           Use os.walk or Path.rglob, filter with should_ignore().
        2. Sort directories bottom-up: deepest first, so children are processed
           before parents. (Sort by path depth descending, then alphabetically.)
        3. Count total dirs for progress reporting.
        4. For each directory (bottom-up):
           a. List files (non-ignored, non-directory children).
           b. Classify each file: binary or text.
              - Binary detection: try reading first 8KB as UTF-8. If it fails
                or contains null bytes, it's binary.
              - Binary files: create FileSummary(name, "[binary: ext, size]", is_binary=True).
              - Text files: read content, truncate to config.max_file_tokens chars.
           c. Call client.summarize_files() with all text files' (name, content) pairs.
           d. Build list[FileSummary] combining binary + LLM-summarized text files.
           e. Read existing child CONTEXT.md files (already generated because bottom-up)
              to build list[SubdirSummary] for each non-ignored subdirectory.
           f. Call client.summarize_directory() with file_summaries + subdir_summaries.
           g. Compute content hash via hash_directory().
           h. Call write_manifest() with all the data.
           i. Update stats, call progress callback.
        5. Return stats.
    """
    raise NotImplementedError


def update_tree(
    root: Path,
    config: Config,
    client: LLMClient,
    spec: pathspec.PathSpec,
    *,
    progress: Optional[ProgressCallback] = None,
) -> GenerateStats:
    """Incrementally update CONTEXT.md files where content has changed.

    Args:
        Same as generate_tree.

    Returns:
        GenerateStats (only counts regenerated directories).

    Implementation:
        1. Collect all directories (same as generate_tree step 1).
        2. Sort bottom-up.
        3. For each directory:
           a. Compute current content hash via hash_directory().
           b. Read existing CONTEXT.md via read_manifest().
           c. If manifest exists and manifest.frontmatter.content_hash == current hash:
              skip (directory is fresh).
           d. Otherwise: regenerate this directory (same as generate_tree step 4a-4h).
           e. Mark as changed — this means the parent will also need regeneration
              (its child hash changed), which happens naturally because we process
              bottom-up and the parent's hash_directory() will compute a new hash.
        4. Return stats.
    """
    raise NotImplementedError


def get_status(
    root: Path,
    spec: pathspec.PathSpec,
    target_root: Path,
) -> list[dict]:
    """Check manifest status for all directories in a tree.

    Args:
        root: Directory to check.
        spec: Ignore spec.
        target_root: Root for relative path computation.

    Returns:
        List of dicts: {"path": relative_str, "status": "fresh"|"stale"|"missing"}

    Implementation:
        1. Walk all directories under root (respecting spec).
        2. For each directory:
           a. If no CONTEXT.md exists: status = "missing".
           b. Else: read manifest, compute current hash, compare.
              If hashes match: "fresh". Else: "stale".
        3. Return sorted by path.
    """
    raise NotImplementedError


def is_binary_file(path: Path) -> bool:
    """Detect if a file is binary.

    Implementation:
        1. Read first 8192 bytes in binary mode.
        2. If contains null byte (b'\\x00'): binary.
        3. Try decoding as UTF-8. If UnicodeDecodeError: binary.
        4. Otherwise: text.
    """
    raise NotImplementedError


def format_binary_info(path: Path) -> str:
    """Format binary file info string like '[binary: xlsx, 234KB]'.

    Implementation:
        1. Get file extension (or "unknown" if none).
        2. Get file size, format as KB/MB.
        3. Return f"[binary: {ext}, {size}]".
    """
    raise NotImplementedError
