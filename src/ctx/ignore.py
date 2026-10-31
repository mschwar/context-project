"""Ignore-pattern matching using .gitignore and .ctxignore files (gitignore-style).

Uses the `pathspec` library for glob matching (same engine git uses).

Pattern resolution:
1. Load .ctxignore.default shipped with this package (always applied).
2. Load .gitignore files from the project anchor through nested subdirectories.
3. Load .ctxignore files from the project anchor and target directory (applied last so !negations win).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
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


class _SubtreePathSpec(pathspec.PathSpec):
    """PathSpec compiled at the canonical project anchor and evaluated from a subtree root."""

    def __init__(self, patterns: Iterable[pathspec.Pattern], *, sub_prefix: str) -> None:
        super().__init__(patterns)
        self._sub_prefix = sub_prefix.strip("/")

    def match_file(
        self,
        file: str | os.PathLike[str],
        separators: Iterable[str] | None = None,
    ) -> bool:
        raw_str = os.fspath(file).replace("\\", "/")
        trailing = "/" if raw_str.endswith("/") else ""
        clean = raw_str.strip("/")
        anchored_file = f"{self._sub_prefix}/{clean}{trailing}" if clean else f"{self._sub_prefix}/"
        return super().match_file(anchored_file, separators=separators)


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


def _rebase_nested_patterns(patterns: list[str], nested_rel: str) -> list[str]:
    rebased: list[str] = []
    for pat in patterns:
        neg, core, is_dir = _split_pattern(pat)
        if not core:
            continue
        suffix = "/" if is_dir else ""
        if core.startswith("**/"):
            rest = core[3:]
            if rest:
                rebased.append(f"{neg}/{nested_rel}/{rest}{suffix}")
                rebased.append(f"{neg}/{nested_rel}/**/{rest}{suffix}")
        elif "/" not in core:
            rebased.append(f"{neg}/{nested_rel}/{core}{suffix}")
            rebased.append(f"{neg}/{nested_rel}/**/{core}{suffix}")
        else:
            anchored = core.lstrip("/")
            if anchored:
                rebased.append(f"{neg}/{nested_rel}/{anchored}{suffix}")
    return rebased


def _collect_nested_gitignore_patterns(
    walk_root: Path,
    *,
    relative_base: Path,
) -> list[str]:
    lines: list[str] = []
    if not walk_root.is_dir():
        return lines
    for dirpath, dirnames, filenames in os.walk(walk_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _NESTED_WALK_PRUNE_DIRS)
        current = Path(dirpath)
        if current == walk_root:
            continue
        if ".gitignore" in filenames:
            gi_path = current / ".gitignore"
            try:
                raw_lines = _pattern_lines(gi_path.read_text(encoding="utf-8", errors="replace"))
                rel_posix = current.relative_to(relative_base).as_posix()
                lines.extend(_rebase_nested_patterns(raw_lines, rel_posix))
            except OSError:
                pass
    return lines


def load_ignore_patterns(
    target_root: Path,
    default_patterns_path: Optional[Path] = None,
) -> pathspec.PathSpec:
    """Load and merge ignore patterns from default, .gitignore (anchor/nested), and .ctxignore."""
    pattern_lines = _load_default_patterns(default_patterns_path)
    resolved_target = target_root.resolve() if target_root.exists() else target_root
    anchor = resolve_project_anchor(resolved_target) if resolved_target.exists() else resolved_target

    if anchor != resolved_target and resolved_target.is_relative_to(anchor):
        sub_prefix = resolved_target.relative_to(anchor).as_posix()
        chain_dirs: list[Path] = []
        cur = resolved_target
        while True:
            chain_dirs.append(cur)
            if cur == anchor:
                break
            cur = cur.parent
        chain_dirs.reverse()

        for directory in chain_dirs:
            gi_path = directory / ".gitignore"
            if gi_path.is_file():
                try:
                    raw_lines = _pattern_lines(gi_path.read_text(encoding="utf-8", errors="replace"))
                    if directory == anchor:
                        pattern_lines.extend(raw_lines)
                    else:
                        rel_dir = directory.relative_to(anchor).as_posix()
                        pattern_lines.extend(_rebase_nested_patterns(raw_lines, rel_dir))
                except OSError:
                    pass

        pattern_lines.extend(
            _collect_nested_gitignore_patterns(resolved_target, relative_base=anchor)
        )

        for directory in chain_dirs:
            ci_path = directory / ".ctxignore"
            if ci_path.is_file():
                try:
                    raw_lines = _pattern_lines(ci_path.read_text(encoding="utf-8"))
                    if directory == anchor:
                        pattern_lines.extend(raw_lines)
                    else:
                        rel_dir = directory.relative_to(anchor).as_posix()
                        pattern_lines.extend(_rebase_nested_patterns(raw_lines, rel_dir))
                except OSError:
                    pass

        anchor_spec = pathspec.PathSpec.from_lines("gitignore", pattern_lines)
        return _SubtreePathSpec(anchor_spec.patterns, sub_prefix=sub_prefix)

    gitignore_path = target_root / ".gitignore"
    if gitignore_path.is_file():
        try:
            pattern_lines.extend(
                _pattern_lines(gitignore_path.read_text(encoding="utf-8", errors="replace"))
            )
        except OSError:
            pass

    pattern_lines.extend(_collect_nested_gitignore_patterns(target_root, relative_base=target_root))

    user_patterns_path = target_root / ".ctxignore"
    if user_patterns_path.exists():
        pattern_lines.extend(_pattern_lines(user_patterns_path.read_text(encoding="utf-8")))

    return pathspec.PathSpec.from_lines("gitignore", pattern_lines)


def should_ignore(path: Path, spec: pathspec.PathSpec, target_root: Path) -> bool:
    """Check whether a path should be ignored."""
    relative_str = path.relative_to(target_root).as_posix()
    try:
        is_directory = path.is_dir()
    except OSError:
        is_directory = False

    if is_directory and relative_str and not relative_str.endswith("/"):
        relative_str = f"{relative_str}/"
    return spec.match_file(relative_str)
