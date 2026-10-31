"""Ignore-pattern matching using .gitignore and .ctxignore files (gitignore-style).

Uses the `pathspec` library for glob matching (same engine git uses).

Pattern resolution at the canonical project anchor:
1. Load .ctxignore.default shipped with this package (always applied).
2. Load .gitignore files top-down from the project anchor, enforcing git's
   excluded-parent-directory rule (descendant .gitignore rules cannot resurrect
   files beneath an excluded ancestor directory).
3. Load .ctxignore files top-down from the project anchor (applied as explicit
   ctx overrides so !negations can selectively include gitignored paths).
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


def _is_base_ignored(anchored_file: str, base_spec: pathspec.PathSpec) -> bool:
    """Evaluate .ctxignore.default + .gitignore with git's excluded-parent-directory rule."""
    clean = anchored_file.strip("/")
    if not clean:
        return False
    parts = clean.split("/")
    # Check every ancestor directory prefix first: once git excludes a parent directory
    # (e.g. /src/private/), no descendant .gitignore negation can re-include paths beneath it.
    ancestor_count = len(parts) if anchored_file.endswith("/") else len(parts) - 1
    prefix = ""
    for idx in range(ancestor_count):
        prefix = f"{prefix}/{parts[idx]}" if prefix else parts[idx]
        if base_spec.match_file(f"{prefix}/"):
            return True
    return base_spec.match_file(anchored_file)


class _CtxPathSpec(pathspec.PathSpec):
    """Canonical project-anchored PathSpec enforcing git parent exclusions + .ctxignore overrides."""

    def __init__(
        self,
        base_spec: pathspec.PathSpec,
        ctxignore_spec: pathspec.PathSpec,
        *,
        ctxignore_negated_dir_prefixes: frozenset[str],
        sub_prefix: str = "",
    ) -> None:
        super().__init__([*base_spec.patterns, *ctxignore_spec.patterns])
        self._base_spec = base_spec
        self._ctxignore_spec = ctxignore_spec
        self._ctxignore_negated_dir_prefixes = ctxignore_negated_dir_prefixes
        self._sub_prefix = sub_prefix.strip("/")

    def _ctxignore_decision(self, anchored_file: str) -> bool | None:
        decision: bool | None = None
        for pat in self._ctxignore_spec.patterns:
            if pat.include is None:
                continue
            if pat.match_file(anchored_file) is not None:
                decision = bool(pat.include)
        return decision

    def match_file(
        self,
        file: str | os.PathLike[str],
        separators: Iterable[str] | None = None,
    ) -> bool:
        del separators  # normalized to POSIX '/' below
        raw_str = os.fspath(file).replace("\\", "/")
        trailing = "/" if raw_str.endswith("/") else ""
        clean = raw_str.strip("/")
        if self._sub_prefix:
            anchored_file = f"{self._sub_prefix}/{clean}{trailing}" if clean else f"{self._sub_prefix}/"
        else:
            anchored_file = f"{clean}{trailing}" if clean else ""
        if not anchored_file:
            return False

        # Explicit .ctxignore rules override .gitignore (in either direction).
        # First check if any ancestor directory was explicitly positively ignored in .ctxignore
        # without a later negation matching anchored_file.
        parts = anchored_file.strip("/").split("/")
        ancestor_count = len(parts) if anchored_file.endswith("/") else len(parts) - 1
        ctx_ancestor_decision: bool | None = None
        prefix = ""
        for idx in range(ancestor_count):
            prefix = f"{prefix}/{parts[idx]}" if prefix else parts[idx]
            dir_dec = self._ctxignore_decision(f"{prefix}/")
            if dir_dec is not None:
                ctx_ancestor_decision = dir_dec

        direct_decision = self._ctxignore_decision(anchored_file)
        if direct_decision is not None:
            return direct_decision
        if ctx_ancestor_decision is not None:
            return ctx_ancestor_decision

        base_ignored = _is_base_ignored(anchored_file, self._base_spec)
        if base_ignored and anchored_file.endswith("/"):
            dir_key = anchored_file.strip("/")
            if dir_key in self._ctxignore_negated_dir_prefixes:
                return False
        return base_ignored


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


def _extract_negated_dir_prefixes(ctxignore_lines: list[str]) -> frozenset[str]:
    """Return concrete ancestor directory prefixes needed to traverse to negated .ctxignore paths."""
    prefixes: set[str] = set()
    for line in ctxignore_lines:
        neg, core, _ = _split_pattern(line)
        if neg != "!" or not core:
            continue
        anchored = core.lstrip("/")
        parts = [p for p in anchored.split("/") if p]
        accum: list[str] = []
        for seg in parts[:-1]:
            if any(ch in seg for ch in ("*", "?", "[")):
                break
            accum.append(seg)
            prefixes.add("/".join(accum))
    return frozenset(prefixes)


def _collect_gitignore_hierarchy(anchor: Path, default_lines: list[str]) -> pathspec.PathSpec:
    """Collect .ctxignore.default + .gitignore top-down from *anchor*, pruning excluded directories."""
    base_lines = list(default_lines)
    root_gi = anchor / ".gitignore"
    if root_gi.is_file():
        try:
            base_lines.extend(_pattern_lines(root_gi.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass

    current_spec = pathspec.PathSpec.from_lines("gitignore", base_lines)
    if not anchor.is_dir():
        return current_spec

    for dirpath, dirnames, filenames in os.walk(anchor, topdown=True):
        current = Path(dirpath)
        if current != anchor and ".gitignore" in filenames:
            gi_path = current / ".gitignore"
            try:
                raw_lines = _pattern_lines(gi_path.read_text(encoding="utf-8", errors="replace"))
                if raw_lines:
                    rel_posix = current.relative_to(anchor).as_posix()
                    base_lines.extend(_rebase_nested_patterns(raw_lines, rel_posix))
                    current_spec = pathspec.PathSpec.from_lines("gitignore", base_lines)
            except OSError:
                pass

        kept_dirs: list[str] = []
        for d in sorted(dirnames):
            if d in _NESTED_WALK_PRUNE_DIRS:
                continue
            rel_child = (current / d).relative_to(anchor).as_posix()
            if _is_base_ignored(f"{rel_child}/", current_spec):
                continue
            kept_dirs.append(d)
        dirnames[:] = kept_dirs

    return current_spec


def _collect_ctxignore_hierarchy(anchor: Path) -> list[str]:
    """Collect .ctxignore overrides top-down from *anchor*."""
    ctx_lines: list[str] = []
    root_ci = anchor / ".ctxignore"
    if root_ci.is_file():
        try:
            ctx_lines.extend(_pattern_lines(root_ci.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass

    if not anchor.is_dir():
        return ctx_lines

    for dirpath, dirnames, filenames in os.walk(anchor, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if d not in _NESTED_WALK_PRUNE_DIRS)
        current = Path(dirpath)
        if current != anchor and ".ctxignore" in filenames:
            ci_path = current / ".ctxignore"
            try:
                raw_lines = _pattern_lines(ci_path.read_text(encoding="utf-8", errors="replace"))
                if raw_lines:
                    rel_posix = current.relative_to(anchor).as_posix()
                    ctx_lines.extend(_rebase_nested_patterns(raw_lines, rel_posix))
            except OSError:
                pass

    return ctx_lines


def load_ignore_patterns(
    target_root: Path,
    default_patterns_path: Optional[Path] = None,
) -> pathspec.PathSpec:
    """Load and merge ignore patterns from default, .gitignore (anchor/nested), and .ctxignore."""
    default_lines = _load_default_patterns(default_patterns_path)
    resolved_target = target_root.resolve() if target_root.exists() else target_root
    anchor = resolve_project_anchor(resolved_target) if resolved_target.exists() else resolved_target

    if not resolved_target.is_relative_to(anchor):
        anchor = resolved_target
    sub_prefix = resolved_target.relative_to(anchor).as_posix() if resolved_target != anchor else ""
    if sub_prefix == ".":
        sub_prefix = ""

    base_spec = _collect_gitignore_hierarchy(anchor, default_lines)
    ctx_lines = _collect_ctxignore_hierarchy(anchor)
    ctxignore_spec = pathspec.PathSpec.from_lines("gitignore", ctx_lines)
    negated_prefixes = _extract_negated_dir_prefixes(ctx_lines)

    return _CtxPathSpec(
        base_spec,
        ctxignore_spec,
        ctxignore_negated_dir_prefixes=negated_prefixes,
        sub_prefix=sub_prefix,
    )


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
