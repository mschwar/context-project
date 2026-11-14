"""Unified deterministic zero-LLM API layer for ctx commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ctx.config import resolve_project_anchor
from ctx.init import (
    _build_metadata,
    _restore_dir_snapshot,
    _snapshot_dir,
    compute_repo_id,
    init_project,
    uninit_project,
)
from ctx.lock import (
    CtxLock,
    LockSupersededError,
    fenced_mkdir,
    fenced_unlink,
    load_json_safe,
    save_json_atomic,
    write_text_atomic,
)

if TYPE_CHECKING:
    from ctx.skeleton import RepoSkeleton


class ConfirmationRequiredError(Exception):
    """Raised when a destructive operation requires explicit confirmation."""


@dataclass
class RefreshResult:
    """Result of a deterministic .ctx/ refresh operation."""

    dirs_processed: int
    dirs_skipped: int
    files_processed: int
    tokens_used: int = 0
    errors: list[str] = field(default_factory=list)
    budget_exhausted: bool = False
    strategy: str = "tier2"
    est_cost_usd: float = 0.0
    stale_directories: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    """Result of a deterministic .ctx/ health/freshness check."""

    mode: str
    directories: list[dict]
    summary: dict


@dataclass
class ExportResult:
    """Result of an export operation."""

    manifests_exported: int
    filter: str
    depth: int | None
    content: str


@dataclass
class ResetResult:
    """Result of a reset (clean) operation removing legacy source-tree CONTEXT.md files."""

    manifests_removed: int
    paths: list[str]


@dataclass
class FleetCapsuleResult:
    """Compact structural & invariant capsule for project-ledger and gbrain ingestion."""

    repo_id: str
    repo_name: str
    root: str
    structural_hash: str
    boundary_doc_hash: str
    total_files: int
    languages: dict[str, int]
    entrypoints: list[str]
    authority_boundaries: list[dict[str, object]]
    subsystems: list[dict[str, object]]
    capsule_markdown: str
    operational_surfaces: list[dict[str, object]] = field(default_factory=list)
    dependency_summary: dict[str, object] = field(default_factory=dict)


def _estimate_tokens(text: str) -> int:
    """Deterministic ~4-char/token heuristic without external tokenizer dependencies."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _path_relative(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return rel or "."


def _iter_tree_manifests(root: Path) -> list[Path]:
    """Return legacy source-tree CONTEXT.md paths under root, excluding .ctx/ and .ctx-cache/."""
    if not root.exists():
        return []
    return sorted(
        p
        for p in root.rglob("CONTEXT.md")
        if ".ctx" not in p.relative_to(root).parts
        and ".ctx-cache" not in p.relative_to(root).parts
    )


def _resolve_ctx_root(root: Path) -> Path | None:
    """Return the enclosing .ctx/ project root if initialized, else None."""
    candidates = [root.resolve()]
    if root.exists():
        anchor = resolve_project_anchor(root)
        if anchor not in candidates:
            candidates.append(anchor)

    for candidate in candidates:
        meta_path = candidate / ".ctx" / "metadata.json"
        if meta_path.is_file():
            return candidate
    return None


def refresh(
    root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    max_depth: Optional[int] = None,
) -> RefreshResult:
    """Deterministically refresh .ctx/ architectural & boundary maps with zero LLM calls."""
    from ctx.skeleton import (
        extract_skeleton,
        is_skeleton_stale,
        render_context_0,
        render_context_1,
        render_context_full,
    )

    target_root = _resolve_ctx_root(root) or root.resolve()
    ctx_dir = target_root / ".ctx"
    meta_path = ctx_dir / "metadata.json"
    expected_exports = ("CONTEXT.md", "CONTEXT-1.md", "CONTEXT-0.md")

    skeleton = extract_skeleton(target_root, max_depth=max_depth)
    subsystem_count = max(1, len(skeleton.subsystems))

    meta = load_json_safe(meta_path, {}) if meta_path.is_file() else {}
    if not isinstance(meta, dict):
        meta = {}
    exports_missing = any(
        not (ctx_dir / name).is_file() or (ctx_dir / name).stat().st_size == 0
        for name in expected_exports
    )
    needs_update = (
        force
        or not meta_path.is_file()
        or exports_missing
        or is_skeleton_stale(meta, skeleton)
    )

    if dry_run:
        stale_dirs = ["."] if needs_update else []
        return RefreshResult(
            dirs_processed=0,
            dirs_skipped=len(stale_dirs),
            files_processed=0,
            strategy="tier2",
            stale_directories=stale_dirs,
        )

    if not needs_update:
        return RefreshResult(
            dirs_processed=0,
            dirs_skipped=subsystem_count,
            files_processed=0,
            strategy="tier2",
            stale_directories=[],
        )

    with CtxLock(target_root, command="refresh"):
        locked_meta = load_json_safe(meta_path, {}) if meta_path.is_file() else {}
        if not isinstance(locked_meta, dict) or not locked_meta:
            locked_meta = _build_metadata(target_root)

        prior_snapshot = _snapshot_dir(ctx_dir)
        try:
            capsule = build_fleet_capsule(target_root, depth=1, skeleton=skeleton)
            fenced_mkdir(ctx_dir, parents=True, exist_ok=True)
            if not (ctx_dir / ".gitignore").is_file():
                write_text_atomic(ctx_dir / ".gitignore", "*\n")
            write_text_atomic(ctx_dir / "CONTEXT-0.md", render_context_0(skeleton))
            write_text_atomic(ctx_dir / "CONTEXT-1.md", render_context_1(skeleton))
            write_text_atomic(ctx_dir / "CONTEXT.md", render_context_full(skeleton))
            save_json_atomic(ctx_dir / "capsule.json", asdict(capsule))
            locked_meta["mode"] = "tier2"
            locked_meta["repo_id"] = compute_repo_id(target_root)
            locked_meta["structural_hash"] = skeleton.structural_hash
            locked_meta["boundary_doc_hash"] = skeleton.boundary_doc_hash
            locked_meta["last_refresh"] = datetime.now(timezone.utc).isoformat()
            save_json_atomic(meta_path, locked_meta)
        except LockSupersededError:
            raise
        except Exception:
            _restore_dir_snapshot(ctx_dir, prior_snapshot)
            raise

    return RefreshResult(
        dirs_processed=subsystem_count,
        dirs_skipped=0,
        files_processed=skeleton.total_files,
        strategy="tier2",
        stale_directories=[],
    )


def check(
    root: Path,
    *,
    verify: bool = False,
    stats: bool = False,
    diff: bool = False,
    verbose: bool = False,
    since: str | None = None,
    check_exit: bool = False,
    quiet: bool = False,
    stat: bool = False,
) -> CheckResult:
    """Evaluate deterministic .ctx/ freshness, coverage, and structure."""
    _ = since  # Preserved for caller compatibility.
    modes = [verify, stats, diff]
    if sum(1 for enabled in modes if enabled) > 1:
        raise ValueError("Only one check mode may be selected.")

    from ctx.sdk import CtxProject, CtxProjectNotFoundError

    target_root = _resolve_ctx_root(root) or root.resolve()
    ctx_dir = target_root / ".ctx"
    expected_exports = ("CONTEXT.md", "CONTEXT-0.md", "CONTEXT-1.md")
    missing_exports = [name for name in expected_exports if not (ctx_dir / name).is_file()]

    try:
        proj = CtxProject.load(target_root, walk_parents=False)
        is_stale_flag = proj.is_stale()
    except CtxProjectNotFoundError:
        proj = None
        is_stale_flag = True

    if proj is None or len(missing_exports) == len(expected_exports):
        status = "missing"
    elif missing_exports or is_stale_flag:
        status = "stale"
    else:
        status = "fresh"

    full_map_path = ctx_dir / "CONTEXT.md"
    full_map_text = full_map_path.read_text(encoding="utf-8") if full_map_path.is_file() else ""
    tokens_est = _estimate_tokens(full_map_text)

    if diff:
        stale_list = [".ctx/CONTEXT.md"] if status != "fresh" else []
        directories = [{"path": p, "status": "stale"} for p in stale_list]
        summary: dict[str, object] = {
            "modified": 0,
            "new": 0,
            "stale": len(stale_list),
            "quiet": quiet,
            "stat": stat,
            "tier2": True,
        }
        return CheckResult(mode="diff", directories=directories, summary=summary)

    if stats:
        directories = (
            [{"path": ".", "status": "covered" if status == "fresh" else status, "tokens": tokens_est}]
            if verbose
            else []
        )
        summary = {
            "dirs": 1,
            "covered": 0 if status == "missing" else 1,
            "missing": 1 if status == "missing" else 0,
            "stale": 1 if status == "stale" else 0,
            "tokens": tokens_est,
            "tier2": True,
        }
        return CheckResult(mode="stats", directories=directories, summary=summary)

    if verify:
        has_valid_header = full_map_text.startswith("---\n") and "mode: tier2" in full_map_text
        directories = []
        invalid_body_count = 0
        if status == "missing":
            directories.append({"path": ".", "status": "missing"})
            invalid_count = 1
        elif missing_exports or not has_valid_header:
            issues = [f"Missing .ctx/ export: .ctx/{name}" for name in missing_exports]
            if not has_valid_header:
                issues.append(".ctx/CONTEXT.md is missing valid mode: tier2 frontmatter.")
            directories.append({"path": ".", "status": "invalid_body", "issues": issues})
            invalid_count = 1
            invalid_body_count = 1
        elif status == "stale":
            directories.append({"path": ".", "status": "stale"})
            invalid_count = 1
        else:
            invalid_count = 0

        summary = {
            "dirs": 1,
            "fresh": 1 if invalid_count == 0 else 0,
            "stale": 1 if status == "stale" else 0,
            "missing": 1 if status == "missing" else 0,
            "invalid": invalid_count,
            "invalid_body": invalid_body_count,
            "check_exit": check_exit,
            "tier2": True,
        }
        return CheckResult(mode="verify", directories=directories, summary=summary)

    directories = [{"path": ".", "status": status}]
    summary = {
        "total": 1,
        "fresh": 1 if status == "fresh" else 0,
        "stale": 1 if status == "stale" else 0,
        "missing": 1 if status == "missing" else 0,
        "check_exit": check_exit,
        "tier2": True,
    }
    return CheckResult(mode="health", directories=directories, summary=summary)


def export_context(
    root: Path,
    *,
    output_file: str | None = None,
    filter_mode: str = "all",
    depth: int | None = None,
) -> ExportResult:
    """Export deterministic .ctx/ maps (or render on-the-fly when uninitialized)."""
    from ctx.sdk import CtxProject, CtxProjectNotFoundError
    from ctx.skeleton import (
        extract_skeleton,
        render_context_0,
        render_context_1,
        render_context_full,
    )

    ctx_root = _resolve_ctx_root(root)
    if depth == 0:
        target_name = "CONTEXT-0.md"
    elif depth == 1:
        target_name = "CONTEXT-1.md"
    else:
        target_name = "CONTEXT.md"
    label = f".ctx/{target_name}"

    if ctx_root is not None:
        target_file = ctx_root / ".ctx" / target_name
        try:
            proj = CtxProject.load(ctx_root, walk_parents=False)
            is_stale_flag = proj.is_stale()
        except CtxProjectNotFoundError:
            is_stale_flag = True

        if filter_mode == "missing":
            if not target_file.is_file():
                content = "# ./ [MISSING]"
                count = 1
            else:
                content = ""
                count = 0
        elif filter_mode == "stale":
            if target_file.is_file() and is_stale_flag:
                content = f"# {label}\n\n{target_file.read_text(encoding='utf-8')}"
                count = 1
            else:
                content = ""
                count = 0
        else:
            if target_file.is_file():
                content = f"# {label}\n\n{target_file.read_text(encoding='utf-8')}"
                count = 1
            else:
                content = ""
                count = 0
    else:
        if filter_mode == "missing":
            content = "# ./ [MISSING]"
            count = 1
        elif filter_mode == "stale":
            content = ""
            count = 0
        else:
            skeleton = extract_skeleton(root.resolve())
            if depth == 0:
                rendered = render_context_0(skeleton)
            elif depth == 1:
                rendered = render_context_1(skeleton)
            else:
                rendered = render_context_full(skeleton)
            content = f"# {label}\n\n{rendered}"
            count = 1

    if output_file:
        Path(output_file).write_text(content, encoding="utf-8")
    return ExportResult(
        manifests_exported=count,
        filter=filter_mode,
        depth=depth,
        content=content,
    )


def reset(
    root: Path,
    *,
    dry_run: bool = False,
    yes: bool = False,
) -> ResetResult:
    """Remove legacy source-tree CONTEXT.md files from a tree without touching .ctx/."""
    if dry_run:
        manifests = _iter_tree_manifests(root)
        paths = [_path_relative(manifest, root) for manifest in manifests]
        return ResetResult(manifests_removed=0, paths=paths)

    if not yes:
        raise ConfirmationRequiredError("--yes flag required in non-interactive mode")

    if not _iter_tree_manifests(root):
        return ResetResult(manifests_removed=0, paths=[])

    lock_root = resolve_project_anchor(root) if root.exists() else root
    with CtxLock(lock_root, command="reset"):
        manifests = _iter_tree_manifests(root)
        paths = [_path_relative(manifest, root) for manifest in manifests]
        for manifest in manifests:
            fenced_unlink(manifest, missing_ok=True)

    return ResetResult(manifests_removed=len(manifests), paths=paths)


def _file_within_capsule_depth(rel_path: str, depth: int | None) -> bool:
    if depth is None:
        return True
    dir_parts = Path(rel_path).parts[:-1]
    if not dir_parts:
        return True
    if depth == 0:
        return False
    effective_depth = 1 if (dir_parts[0] == "src" and len(dir_parts) == 2) else len(dir_parts)
    return effective_depth <= depth


def _entrypoint_within_capsule_depth(ep: str, depth: int | None, root: Path) -> bool:
    if depth is None:
        return True
    if ep.startswith("file:"):
        return _file_within_capsule_depth(ep[len("file:") :], depth)
    if ep.startswith("npm:") and " -> " in ep:
        from ctx.skeleton import resolve_config_target_path

        _, raw_target = ep.split(" -> ", 1)
        resolved_target = resolve_config_target_path(root, raw_target)
        if resolved_target is None:
            return False
        clean_rel = resolved_target.relative_to(root.resolve()).as_posix()
        return _file_within_capsule_depth(clean_rel, depth)
    if ep.startswith("cli:") and " -> " in ep:
        from ctx.skeleton import resolve_cli_entrypoint_target

        _, raw_target = ep.split(" -> ", 1)
        resolved_rel = resolve_cli_entrypoint_target(root, raw_target.strip())
        if resolved_rel is not None:
            return _file_within_capsule_depth(resolved_rel, depth)
        module_name = raw_target.strip().split(":", 1)[0].strip()
        mod_depth = max(0, len([seg for seg in module_name.split(".") if seg]) - 1)
        return mod_depth <= depth
    return True


def build_fleet_capsule(
    root: Path,
    *,
    depth: int | None = 1,
    output_file: str | None = None,
    skeleton: "RepoSkeleton | None" = None,
) -> FleetCapsuleResult:
    """Generate a compact deterministic capsule for project-ledger and gbrain ingestion."""
    from dataclasses import replace

    from ctx.impact import build_dependency_graph
    from ctx.skeleton import (
        extract_skeleton,
        render_context_0,
        render_context_1,
        strip_tier2_chrome,
    )

    resolved_root = root.resolve()
    skeleton = skeleton if skeleton is not None else extract_skeleton(resolved_root)
    try:
        dep_graph = build_dependency_graph(resolved_root, skeleton=skeleton)
    except Exception:
        dep_graph = None
    repo_id = compute_repo_id(resolved_root)

    kept_boundary_docs = [
        doc for doc in skeleton.boundary_docs if _file_within_capsule_depth(doc.relative_path, depth)
    ]
    kept_entrypoints = [
        ep
        for ep in skeleton.entrypoints
        if _entrypoint_within_capsule_depth(ep, depth, resolved_root)
    ]
    kept_surfaces = [
        surf
        for surf in skeleton.operational_surfaces
        if _file_within_capsule_depth(surf.file, depth)
    ]

    authority_boundaries = [
        {
            "path": doc.relative_path,
            "kind": doc.kind,
            "headings": list(doc.headings),
            "summary": doc.summary_line,
            "content_hash": doc.content_hash,
        }
        for doc in kept_boundary_docs
    ]

    kept_subsystem_objs = []
    filtered_subsystems = []
    for sub in skeleton.subsystems:
        if depth is not None and sub.path != ".":
            sub_depth = len(Path(sub.path).parts)
            effective_depth = 1 if (Path(sub.path).parts[0] == "src" and sub_depth == 2) else sub_depth
            if effective_depth > depth:
                continue
        kept_subsystem_objs.append(sub)
        filtered_subsystems.append(
            {
                "path": sub.path,
                "arch_role": sub.arch_role,
                "file_count": sub.file_count,
                "languages": list(sub.languages),
                "key_symbols": list(sub.key_symbols[:10]),
                "internal_deps": list(sub.internal_deps),
                "external_deps": list(sub.external_deps),
            }
        )

    operational_surfaces_payload: list[dict[str, object]] = [
        {
            "kind": surf.kind,
            "name": surf.name,
            "file": surf.file,
            "detail": surf.detail,
        }
        for surf in kept_surfaces[:60]
    ]
    dependency_summary: dict[str, object] = (
        {
            "internal_edge_count": dep_graph.internal_edge_count,
            "cycle_count": len(dep_graph.cycles),
            "subsystem_cycle_count": len(dep_graph.subsystem_cycles),
            "topological_layers_count": len(dep_graph.topological_layers),
            "top_hubs": [
                {"path": p, "inbound_count": len(callers)}
                for p, callers in sorted(
                    dep_graph.inbound_files.items(),
                    key=lambda kv: (-len(kv[1]), kv[0]),
                )[:5]
                if callers
            ],
        }
        if dep_graph is not None
        else {}
    )

    render_skeleton = replace(
        skeleton,
        subsystems=kept_subsystem_objs,
        boundary_docs=kept_boundary_docs,
        entrypoints=kept_entrypoints,
        operational_surfaces=kept_surfaces,
    )
    capsule_md = render_context_0(render_skeleton)
    if depth is None or depth >= 1:
        c1_body = strip_tier2_chrome(render_context_1(render_skeleton), strip_footer=False)
        capsule_md = (
            capsule_md.removesuffix("<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->\n")
            + "\n"
            + c1_body.rstrip()
            + "\n"
        )

    result = FleetCapsuleResult(
        repo_id=repo_id,
        repo_name=skeleton.repo_name,
        root=str(resolved_root),
        structural_hash=skeleton.structural_hash,
        boundary_doc_hash=skeleton.boundary_doc_hash,
        total_files=skeleton.total_files,
        languages=dict(skeleton.languages),
        entrypoints=kept_entrypoints,
        authority_boundaries=authority_boundaries,
        subsystems=filtered_subsystems,
        capsule_markdown=capsule_md,
        operational_surfaces=operational_surfaces_payload,
        dependency_summary=dependency_summary,
    )

    if output_file:
        out_path = Path(output_file)
        if out_path.suffix.lower() == ".json":
            out_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        else:
            out_path.write_text(capsule_md, encoding="utf-8")

    return result


def analyze_impact(
    root: Path,
    target: str,
    *,
    max_depth: int | None = None,
):
    """Analyze directed reverse-dependency blast radius, coupled tests, and governing docs."""
    from ctx.impact import analyze_impact as _analyze_impact

    return _analyze_impact(root, target, max_depth=max_depth)


def analyze_diff_impact(
    root: Path,
    *,
    git_diff: str | None = None,
    staged: bool = False,
    max_depth: int | None = None,
):
    """Compile a git diff into blast radius, coupled tests, and proportional verification checks."""
    from ctx.impact import analyze_diff_impact as _analyze_diff_impact

    return _analyze_diff_impact(root, git_diff=git_diff, staged=staged, max_depth=max_depth)


def run_benchmark(
    paths: list[Path],
    *,
    output_file: str | None = None,
) -> dict[str, object]:
    """Run the Phase 27.1 A/B/C agent navigation benchmark across *paths*."""
    from ctx.benchmark import render_benchmark_markdown, run_navigation_benchmark

    report = run_navigation_benchmark(paths)
    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        else:
            out_path.write_text(render_benchmark_markdown(report), encoding="utf-8")
    return report
