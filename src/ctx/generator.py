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

import math
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pathspec

from ctx.config import Config
from ctx.hasher import hash_directory, is_stale
from ctx.ignore import should_ignore
from ctx.llm import CachingLLMClient, LLMClient, FileSummary, SubdirSummary
from ctx.manifest import Manifest, read_manifest, write_manifest
from ctx.language_detector import detect_language
from ctx.lang_parsers.python_parser import parse_python_file
from ctx.lang_parsers.js_ts_parser import parse_js_ts_file
from ctx.lang_parsers.rust_parser import parse_rust_file


# Cap on threads per depth level. LLM calls are I/O-bound so threads are effective,
# but we stay conservative to avoid hammering provider rate limits.
MAX_PARALLEL_DIRS = 4


@dataclass
class GenerateStats:
    """Stats accumulated during a generation run."""

    dirs_processed: int = 0
    dirs_skipped: int = 0
    files_processed: int = 0
    files_binary: int = 0
    tokens_used: int = 0
    budget_exhausted: bool = False
    errors: list[str] = field(default_factory=list)


# Type alias for progress callback: (current_dir, dirs_done, dirs_total)
ProgressCallback = Callable[[Path, int, int], None]


def _relative_path_str(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return path.as_posix()
    if not relative.parts:
        return "."
    return relative.as_posix()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _extract_manifest_summary(manifest: Manifest, directory_name: str) -> str:
    lines = [line.strip() for line in manifest.body.splitlines()]
    seen_heading = False
    for line in lines:
        if not line:
            continue
        if not seen_heading and line.startswith("#"):
            seen_heading = True
            continue
        if seen_heading:
            return line
    return f"{directory_name} directory"


def _collect_directories(
    root: Path,
    spec: pathspec.PathSpec,
    target_root: Path,
    *,
    max_depth: Optional[int] = None,
) -> list[Path]:
    directories: list[Path] = []

    def visit(path: Path, depth: int) -> None:
        directories.append(path)
        if max_depth is not None and depth >= max_depth:
            return

        try:
            children = sorted(path.iterdir(), key=lambda child: child.name)
        except OSError:
            return

        for child in children:
            if not child.is_dir() or should_ignore(child, spec, target_root):
                continue
            visit(child, depth + 1)

    visit(root, 0)
    return directories


def _ordered_directories(
    root: Path,
    spec: pathspec.PathSpec,
    *,
    max_depth: Optional[int] = None,
) -> list[Path]:
    directories = _collect_directories(root, spec, root, max_depth=max_depth)
    return sorted(
        directories,
        key=lambda path: (-len(path.relative_to(root).parts), path.relative_to(root).as_posix()),
    )


def _list_directory_entries(
    path: Path,
    spec: pathspec.PathSpec,
    target_root: Path,
) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    directories: list[Path] = []

    for child in sorted(path.iterdir(), key=lambda item: item.name):
        if should_ignore(child, spec, target_root):
            continue
        if child.is_dir():
            directories.append(child)
        elif child.is_file():
            files.append(child)

    return files, directories


def _binary_file_summary(path: Path) -> FileSummary:
    return FileSummary(
        name=path.name,
        summary=format_binary_info(path),
        is_binary=True,
    )


def _prepare_file_entry(
    path: Path,
    config: Config,
) -> tuple[FileSummary | dict, int]:
    content: Optional[str] = None
    if not is_binary_file(path):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = None

    if content is None:
        return _binary_file_summary(path), 0

    language = detect_language(path)
    metadata: dict = {}
    if language == "Python":
        metadata = parse_python_file(path)
    elif language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
        metadata = parse_js_ts_file(path)
    elif language == "Rust":
        metadata = parse_rust_file(path)

    truncated = content[: config.max_file_tokens]
    entry = {
        "name": path.name,
        "content": truncated,
        "language": language,
        "metadata": metadata,
    }
    return entry, _estimate_tokens(truncated)


def _should_regenerate_directory(
    path: Path,
    root: Path,
    spec: pathspec.PathSpec,
    *,
    incremental: bool,
) -> bool:
    if not incremental:
        return True

    current_hash = hash_directory(path, spec, root)
    manifest = read_manifest(path)
    return manifest is None or is_stale(manifest.frontmatter.content_hash, current_hash)


def _manifest_model(config: Config, client: LLMClient) -> str:
    model = getattr(client, "model", "")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return config.resolved_model()


def _generate_directory_manifest(
    path: Path,
    root: Path,
    config: Config,
    client: LLMClient,
    spec: pathspec.PathSpec,
) -> tuple[int, int, int]:
    files, directories = _list_directory_entries(path, spec, root)

    ordered_entries: list[FileSummary | dict] = []
    text_inputs: list[dict] = []
    binary_count = 0
    tokens_total = 0

    for file_path in files:
        entry, estimated_tokens = _prepare_file_entry(file_path, config)
        if isinstance(entry, FileSummary):
            binary_count += 1
            ordered_entries.append(entry)
            continue

        text_inputs.append(entry)
        tokens_total += estimated_tokens
        ordered_entries.append(entry)

    text_results = client.summarize_files(path, text_inputs)
    if len(text_results) != len(text_inputs):
        raise ValueError(f"Expected {len(text_inputs)} file summaries for {path}, got {len(text_results)}.")

    file_summaries: list[FileSummary] = []
    text_index = 0
    for entry in ordered_entries:
        if isinstance(entry, FileSummary):
            file_summaries.append(entry)
            continue

        result = text_results[text_index]
        file_summaries.append(FileSummary(name=entry["name"], summary=result.text))
        text_index += 1

    subdir_summaries: list[SubdirSummary] = []
    for directory in directories:
        manifest = read_manifest(directory)
        if manifest is None:
            continue
        subdir_summaries.append(
            SubdirSummary(
                name=directory.name,
                summary=_extract_manifest_summary(manifest, directory.name),
            )
        )

    directory_result = client.summarize_directory(path, file_summaries, subdir_summaries)
    content_hash = hash_directory(path, spec, root)
    write_manifest(
        path,
        model=_manifest_model(config, client),
        content_hash=content_hash,
        files=len(files),
        dirs=len(directories),
        tokens_total=tokens_total,
        body=directory_result.text,
    )

    total_tokens_used = sum(result.input_tokens + result.output_tokens for result in text_results)
    total_tokens_used += directory_result.input_tokens + directory_result.output_tokens
    return len(files), binary_count, total_tokens_used


def _process_one_directory(
    directory: Path,
    root: Path,
    config: Config,
    client: LLMClient,
    spec: pathspec.PathSpec,
    incremental: bool,
) -> tuple[int, int, int, str | None]:
    """Worker function for parallel execution within a depth level.

    Returns (file_count, binary_count, tokens_used, error):
      - error is None on success
      - error is "skip" when the directory is fresh and was skipped
      - error is an error string when an exception occurred
    """
    try:
        if not _should_regenerate_directory(directory, root, spec, incremental=incremental):
            return 0, 0, 0, "skip"
        file_count, binary_count, tokens_used = _generate_directory_manifest(
            directory, root, config, client, spec
        )
        return file_count, binary_count, tokens_used, None
    except Exception as exc:
        return 0, 0, 0, str(exc)


def _run_generation(
    root: Path,
    config: Config,
    client: LLMClient,
    spec: pathspec.PathSpec,
    *,
    incremental: bool,
    progress: Optional[ProgressCallback] = None,
    changed_files: Optional[list[Path]] = None,
) -> GenerateStats:
    stats = GenerateStats()
    ordered_directories = _ordered_directories(root, spec, max_depth=config.max_depth)

    if changed_files is not None:
        target_directories: set[Path] = set()
        for changed_file in changed_files:
            # Add the directory containing the changed file
            dir_to_check = changed_file.parent
            if dir_to_check.is_relative_to(root):
                target_directories.add(dir_to_check)
                # Add all ancestors up to the root
                for ancestor in dir_to_check.parents:
                    if ancestor == root or ancestor.is_relative_to(root):
                        target_directories.add(ancestor)
                    if ancestor == root: # Stop at the root
                        break
        
        # Filter ordered_directories to only include those in target_directories
        # Or, more precisely, those that are affected by the change (contain a changed file or are ancestors of one)
        # Given bottom-up processing, if a directory is in target_directories,
        # it means it either contains a changed file, or an ancestor of one.
        # This implies its children would have been processed already if they contained changed files.
        filtered_ordered_directories = []
        for d in ordered_directories:
            if d in target_directories:
                filtered_ordered_directories.append(d)
        ordered_directories = filtered_ordered_directories

    total_dirs = len(ordered_directories)

    # Group directories by depth. Siblings (same depth) are independent and can run in parallel.
    # The bottom-up invariant is preserved by processing each depth level fully before the next.
    levels: dict[int, list[Path]] = defaultdict(list)
    for path in ordered_directories:
        depth = len(path.relative_to(root).parts)
        levels[depth].append(path)

    stats_lock = threading.Lock()
    dirs_done = 0

    for depth in sorted(levels.keys(), reverse=True):  # deepest first
        level_dirs = levels[depth]

        # Token budget check at level granularity — before submitting the level.
        if config.token_budget is not None and stats.tokens_used >= config.token_budget:
            remaining = sum(len(levels[d]) for d in levels if d <= depth)
            stats.dirs_skipped += remaining
            stats.budget_exhausted = True
            break

        workers = min(MAX_PARALLEL_DIRS, len(level_dirs))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_one_directory,
                    directory, root, config, client, spec, incremental,
                ): directory
                for directory in level_dirs
            }
            for future in as_completed(futures):
                directory = futures[future]
                file_count, binary_count, tokens_used, error = future.result()
                with stats_lock:
                    dirs_done += 1
                    local_done = dirs_done
                    if error == "skip":
                        stats.dirs_skipped += 1
                    elif error is not None:
                        stats.errors.append(f"{directory}: {error}")
                    else:
                        stats.dirs_processed += 1
                        stats.files_processed += file_count
                        stats.files_binary += binary_count
                        stats.tokens_used += tokens_used
                    if progress is not None:
                        progress(directory, local_done, total_dirs)

    return stats


def _resolve_cache_path(config: Config, root: Path) -> Optional[Path]:
    """Return the disk cache path for CachingLLMClient, or None to disable."""
    if config.cache_path == "":
        return None  # explicitly disabled
    if config.cache_path:
        return Path(config.cache_path)
    return root / ".ctx-cache" / "llm_cache.json"


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
    return _run_generation(
        root,
        config,
        CachingLLMClient(client, cache_path=_resolve_cache_path(config, root)),
        spec,
        incremental=False,
        progress=progress,
    )


def update_tree(
    root: Path,
    config: Config,
    client: LLMClient,
    spec: pathspec.PathSpec,
    *,
    progress: Optional[ProgressCallback] = None,
    changed_files: Optional[list[Path]] = None,
) -> GenerateStats:
    """Incrementally update CONTEXT.md files where content has changed.

    Args:
        Same as generate_tree.
        changed_files: Optional list of file paths that have changed.
                       If provided, only directories affected by these changes
                       will be processed.

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
    return _run_generation(
        root,
        config,
        CachingLLMClient(client, cache_path=_resolve_cache_path(config, root)),
        spec,
        incremental=True,
        progress=progress,
        changed_files=changed_files,
    )


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
    directories = _collect_directories(root, spec, target_root)
    results: list[dict] = []

    for directory in directories:
        relative_path = _relative_path_str(directory, target_root)
        try:
            manifest = read_manifest(directory)
        except ValueError:
            results.append({"path": relative_path, "status": "stale"})
            continue
        if manifest is None:
            results.append({"path": relative_path, "status": "missing"})
            continue

        current_hash = hash_directory(directory, spec, target_root)
        status = "stale" if is_stale(manifest.frontmatter.content_hash, current_hash) else "fresh"
        results.append({"path": relative_path, "status": status})

    return sorted(results, key=lambda item: item["path"])


def check_stale_dirs(
    root: Path,
    config: Config,
    spec: pathspec.PathSpec,
    *,
    changed_files: Optional[list[Path]] = None,
) -> list[Path]:
    """Return directories that would be regenerated by update_tree, without LLM calls.

    Used by --dry-run to preview what a run would touch.
    """
    ordered_directories = _ordered_directories(root, spec, max_depth=config.max_depth)

    if changed_files is not None:
        target_directories: set[Path] = set()
        for changed_file in changed_files:
            dir_to_check = changed_file.parent
            if dir_to_check.is_relative_to(root):
                target_directories.add(dir_to_check)
                for ancestor in dir_to_check.parents:
                    if ancestor == root or ancestor.is_relative_to(root):
                        target_directories.add(ancestor)
                    if ancestor == root:
                        break
        ordered_directories = [d for d in ordered_directories if d in target_directories]

    return [
        directory for directory in ordered_directories
        if _should_regenerate_directory(directory, root, spec, incremental=True)
    ]


def is_binary_file(path: Path) -> bool:
    """Detect if a file is binary.

    Implementation:
        1. Read first 8192 bytes in binary mode.
        2. If contains null byte (b'\\x00'): binary.
        3. Try decoding as UTF-8. If UnicodeDecodeError: binary.
        4. Otherwise: text.
    """
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
    except OSError:
        return True

    if b"\x00" in sample:
        return True

    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True

    return False


def format_binary_info(path: Path) -> str:
    """Format binary file info string like '[binary: xlsx, 234KB]'.

    Implementation:
        1. Get file extension (or "unknown" if none).
        2. Get file size, format as KB/MB.
        3. Return f"[binary: {ext}, {size}]".
    """
    extension = path.suffix.lstrip(".").lower() or "unknown"
    size_bytes = path.stat().st_size
    if size_bytes < 1024 * 1024:
        size = f"{max(1, math.ceil(size_bytes / 1024))}KB"
    else:
        size_mb = size_bytes / (1024 * 1024)
        size = f"{size_mb:.1f}".rstrip("0").rstrip(".") + "MB"
    return f"[binary: {extension}, {size}]"
