"""Ignore-pattern matching using .ctxignore files (gitignore-style).

Uses the `pathspec` library for glob matching (same engine git uses).

Pattern resolution:
1. Load .ctxignore.default shipped with this package (always applied).
2. Load .ctxignore from the target root directory (if present).
3. Merge patterns (user patterns add to defaults, they don't replace).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pathspec


def load_ignore_patterns(
    target_root: Path,
    default_patterns_path: Optional[Path] = None,
) -> pathspec.PathSpec:
    """Load and merge ignore patterns from default + user .ctxignore files.

    Args:
        target_root: Root directory being processed. Look for .ctxignore here.
        default_patterns_path: Path to .ctxignore.default. If None, use the one
            shipped alongside this package (../../../.ctxignore.default relative
            to this file, or locate via importlib.resources).

    Returns:
        A compiled PathSpec object. Use `spec.match_file(relative_path)` to test.

    Implementation:
        1. Read .ctxignore.default (ship sensible defaults — see file).
        2. Read target_root / ".ctxignore" if it exists.
        3. Combine all pattern lines, filter blanks and comments.
        4. Return pathspec.PathSpec.from_lines("gitwildmatch", combined_lines).
    """
    default_path = default_patterns_path or (Path(__file__).resolve().parents[2] / ".ctxignore.default")
    pattern_lines: list[str] = []

    for path in (default_path, target_root / ".ctxignore"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            pattern_lines.append(line.rstrip("\r\n"))

    return pathspec.PathSpec.from_lines("gitwildmatch", pattern_lines)


def should_ignore(path: Path, spec: pathspec.PathSpec, target_root: Path) -> bool:
    """Check whether a path should be ignored.

    Args:
        path: Absolute path to test.
        spec: Compiled ignore spec from load_ignore_patterns().
        target_root: Root directory (paths are matched relative to this).

    Returns:
        True if the path matches an ignore pattern.

    Implementation:
        1. Compute relative path from target_root.
        2. For directories, append trailing slash for correct glob matching.
        3. Return spec.match_file(relative_str).
    """
    relative_str = path.relative_to(target_root).as_posix()
    if path.is_dir() and relative_str and not relative_str.endswith("/"):
        relative_str = f"{relative_str}/"
    return spec.match_file(relative_str)
