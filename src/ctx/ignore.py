"""Ignore-pattern matching using .ctxignore files (gitignore-style).

Uses the `pathspec` library for glob matching (same engine git uses).

Pattern resolution:
1. Load .ctxignore.default shipped with this package (always applied).
2. Load .ctxignore from the target root directory (if present).
3. Merge patterns (user patterns add to defaults, they don't replace).
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path
from typing import Optional

import pathspec

from ctx.config import resolve_project_anchor

_NESTED_WALK_PRUNE_DIRS = frozenset({
    ".git",
    ".ctx",
    ".ctx-cache",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tmp",
})


def _pattern_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line.rstrip("\r\n"))
    return lines


def _load_default_patterns(default_patterns_path: Optional[Path]) -> list[str]:
    if default_patterns_path is not None:
        return _pattern_lines(default_patterns_path.read_text(encoding="utf-8"))

    try:
        packaged_default = files("ctx").joinpath(".ctxignore.default")
        if packaged_default.is_file():
            return _pattern_lines(packaged_default.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    for directory in Path(__file__).resolve().parents:
        candidate = directory / ".ctxignore.default"
        if candidate.is_file():
            return _pattern_lines(candidate.read_text(encoding="utf-8"))

    return []


def _split_pattern(raw_pattern: str) -> tuple[str, str, bool]:
    neg = ""
    body = raw_pattern
    if body.startswith("\\!"):
        body = body[1:]
    elif body.startswith("!"):
        neg = "!"
        body = body[1:]
    is_dir = body.endswith("/")
    core = body.rstrip("/")
    return neg, core, is_dir


def _rebase_ancestor_patterns(patterns: list[str], sub_prefix: str) -> list[str]:
    rebased: list[str] = []
    for pat in patterns:
        neg, core, is_dir = _split_pattern(pat)
        if not core:
            continue
        suffix = "/" if is_dir else ""
        if core.startswith("**/") or "/" not in core:
            rebased.append(pat)
            continue
        anchored = core.lstrip("/")
        if anchored.startswith(f"{sub_prefix}/"):
            remainder = anchored[len(sub_prefix) + 1 :]
            if remainder:
                rebased.append(f"{neg}/{remainder}{suffix}")
    return rebased


def _rebase_nested_patterns(patterns: list[str], nested_rel: str) -> list[str]:
    rebased: list[str] = []
    for pat in patterns:
        neg, core, is_dir = _split_pattern(pat)
        if not core:
            continue
        suffix = "/" if is_dir else ""
        if "/" not in core:
            rebased.append(f"{neg}/{nested_rel}/{core}{suffix}")
            rebased.append(f"{neg}/{nested_rel}/**/{core}{suffix}")
        else:
            anchored = core.lstrip("/")
            if anchored:
                rebased.append(f"{neg}/{nested_rel}/{anchored}{suffix}")
    return rebased


def _collect_nested_gitignore_patterns(target_root: Path) -> list[str]:
    lines: list[str] = []
    if not target_root.is_dir():
        return lines
    for dirpath, dirnames, filenames in os.walk(target_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _NESTED_WALK_PRUNE_DIRS)
        current = Path(dirpath)
        if current == target_root:
            continue
        if ".gitignore" in filenames:
            gi_path = current / ".gitignore"
            try:
                raw_lines = _pattern_lines(gi_path.read_text(encoding="utf-8", errors="replace"))
                rel_posix = current.relative_to(target_root).as_posix()
                lines.extend(_rebase_nested_patterns(raw_lines, rel_posix))
            except OSError:
                pass
    return lines


def load_ignore_patterns(
    target_root: Path,
    default_patterns_path: Optional[Path] = None,
) -> pathspec.PathSpec:
    """Load and merge ignore patterns from default, .gitignore (ancestor/root/nested), and .ctxignore."""
    pattern_lines = _load_default_patterns(default_patterns_path)
    resolved_target = target_root.resolve() if target_root.exists() else target_root
    anchor = resolve_project_anchor(resolved_target) if resolved_target.exists() else resolved_target

    ancestor_dirs: list[Path] = []
    if anchor != resolved_target and resolved_target.is_relative_to(anchor):
        cur = resolved_target.parent
        while True:
            ancestor_dirs.append(cur)
            if cur == anchor:
                break
            cur = cur.parent
        ancestor_dirs.reverse()

    # 1. Ancestor .gitignore rules rebased onto target_root (for subtree commands)
    for anc in ancestor_dirs:
        anc_gi = anc / ".gitignore"
        if anc_gi.is_file():
            try:
                sub_prefix = resolved_target.relative_to(anc).as_posix()
                pattern_lines.extend(
                    _rebase_ancestor_patterns(
                        _pattern_lines(anc_gi.read_text(encoding="utf-8", errors="replace")),
                        sub_prefix,
                    )
                )
            except OSError:
                pass

    # 2. Target root .gitignore
    gitignore_path = target_root / ".gitignore"
    if gitignore_path.is_file():
        try:
            pattern_lines.extend(
                _pattern_lines(gitignore_path.read_text(encoding="utf-8", errors="replace"))
            )
        except OSError:
            pass

    # 3. Nested .gitignore files beneath target_root
    pattern_lines.extend(_collect_nested_gitignore_patterns(target_root))

    # 4. Ancestor and target .ctxignore overrides (applied last so !negations win)
    for anc in ancestor_dirs:
        anc_ci = anc / ".ctxignore"
        if anc_ci.is_file():
            try:
                sub_prefix = resolved_target.relative_to(anc).as_posix()
                pattern_lines.extend(
                    _rebase_ancestor_patterns(
                        _pattern_lines(anc_ci.read_text(encoding="utf-8")),
                        sub_prefix,
                    )
                )
            except OSError:
                pass

    user_patterns_path = target_root / ".ctxignore"
    if user_patterns_path.exists():
        pattern_lines.extend(_pattern_lines(user_patterns_path.read_text(encoding="utf-8")))

    return pathspec.PathSpec.from_lines("gitignore", pattern_lines)


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
    try:
        is_directory = path.is_dir()
    except OSError:
        is_directory = False

    if is_directory and relative_str and not relative_str.endswith("/"):
        relative_str = f"{relative_str}/"
    return spec.match_file(relative_str)
