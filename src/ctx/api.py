"""Unified API layer for ctx canonical commands."""

from __future__ import annotations

import logging
import os
import subprocess
import time as _time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ctx.config import (
    DEFAULT_BASE_URLS,
    LOCAL_PROVIDERS,
    MissingApiKeyError,
    PROVIDER_DETECTED_VIA,
    Config,
    detect_provider,
    estimate_cost,
    load_config,
    probe_provider_connectivity,
    write_default_config,
)
from ctx.generator import (
    GenerateStats,
    check_stale_dirs,
    generate_tree,
    inspect_directory_health,
    update_tree,
    validate_manifest_body,
)
from ctx.ignore import load_ignore_patterns
from ctx.manifest import read_manifest
from ctx.llm import create_client
from ctx.lock import CtxLock


ProgressCallback = Callable[[Path, int, int, int], None]
logger = logging.getLogger(__name__)


class ConfirmationRequiredError(Exception):
    """Raised when a destructive operation requires explicit confirmation."""


class BudgetExhaustedError(Exception):
    """Raised when refresh hits a hard per-run token or USD spending ceiling."""


@dataclass
class RefreshResult:
    """Result of a refresh operation."""

    dirs_processed: int
    dirs_skipped: int
    files_processed: int
    tokens_used: int
    errors: list[str]
    budget_exhausted: bool
    strategy: str  # "full", "incremental", "smart"
    est_cost_usd: float
    stale_directories: list[str]
    budget_guardrail: str | None = None
    config_written: bool = False
    setup_provider: str | None = None
    setup_model: str | None = None
    setup_detected_via: str | None = None
    local_batch_fallbacks: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class CheckResult:
    """Result of a health check."""

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
    """Result of a reset (clean) operation."""

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


def _build_generation_runtime(
    root: Path,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_depth: Optional[int] = None,
    token_budget: Optional[int] = None,
    base_url: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> tuple[Config, object, object]:
    load_config_kwargs: dict[str, object] = {
        "provider": provider,
        "model": model,
    }
    if max_depth is not None:
        load_config_kwargs["max_depth"] = max_depth
    if token_budget is not None:
        load_config_kwargs["token_budget"] = token_budget
    if base_url is not None:
        load_config_kwargs["base_url"] = base_url
    if cache_path is not None:
        load_config_kwargs["cache_path"] = cache_path

    config = load_config(root, **load_config_kwargs)
    if config.provider not in LOCAL_PROVIDERS:
        ok, conn_error = probe_provider_connectivity(config.provider, config.api_key, config.base_url)
        if not ok:
            raise RuntimeError(f"Pre-flight check failed: {conn_error or 'unknown error'}")

    spec = load_ignore_patterns(root)
    client = create_client(config)
    return config, spec, client


def _find_config_path(target_path: Path) -> Path | None:
    """Return the nearest .ctxconfig for a path, if any."""

    start_dir = target_path if target_path.is_dir() else target_path.parent
    for directory in (start_dir, *start_dir.parents):
        config_path = directory / ".ctxconfig"
        if config_path.exists():
            return config_path
    return None


def _iter_tree_manifests(root: Path) -> list[Path]:
    """Return source-tree CONTEXT.md paths under root, excluding .ctx/ and .ctx-cache/."""
    return sorted(
        p
        for p in root.rglob("CONTEXT.md")
        if ".ctx" not in p.relative_to(root).parts
        and ".ctx-cache" not in p.relative_to(root).parts
    )


def _has_manifests(root: Path) -> bool:
    return bool(_iter_tree_manifests(root))


def _is_tier2_repo(root: Path) -> bool:
    """Return True when root is initialized in Tier 2 (.ctx/ only, no root CONTEXT.md)."""
    meta_path = root / ".ctx" / "metadata.json"
    if not meta_path.is_file() or (root / "CONTEXT.md").is_file():
        return False
    from ctx.stats_board import load_json_safe

    data = load_json_safe(meta_path, {})
    return isinstance(data, dict) and data.get("mode") == "tier2"


def _directory_within_depth(path: Path, root: Path, depth: Optional[int]) -> bool:
    if depth is None:
        return True
    return len(path.relative_to(root).parts) <= depth


def _apply_token_guardrail(config: Config) -> None:
    """Fold the hard token guardrail into the generator token budget."""

    if config.max_tokens_per_run is None:
        return
    # A smaller explicit token_budget is already stricter, so only clamp when
    # the generator budget is unset or looser than the hard per-run ceiling.
    if config.token_budget is None or config.token_budget > config.max_tokens_per_run:
        config.token_budget = config.max_tokens_per_run


def _budget_guardrail_message(config: Config, stats: GenerateStats) -> str | None:
    """Return a hard-budget error message when a Stage 3 guardrail is hit."""

    if config.max_tokens_per_run is not None and stats.tokens_used >= config.max_tokens_per_run:
        return (
            f"Token budget guardrail reached: {stats.tokens_used:,} tokens used "
            f"(limit {config.max_tokens_per_run:,})."
        )
    if config.max_usd_per_run is not None:
        est_cost = estimate_cost(stats.tokens_used, config.provider, config.resolved_model())
        if est_cost >= config.max_usd_per_run:
            return (
                f"USD budget guardrail reached: ${est_cost:.4f} estimated spend "
                f"(limit ${config.max_usd_per_run:.4f})."
            )
    return None


def refresh(
    root: Path,
    *,
    force: bool = False,
    setup: bool = False,
    watch: bool = False,
    dry_run: bool = False,
    until_complete: bool = False,
    provider: str | None = None,
    model: str | None = None,
    max_depth: int | None = None,
    token_budget: int | None = None,
    base_url: str | None = None,
    cache_path: str | None = None,
    progress: ProgressCallback | None = None,
) -> RefreshResult:
    """Run canonical refresh behavior with strategy selection."""
    from ctx.git import get_changed_files
    from ctx.watcher import run_watch

    if setup and watch:
        raise ValueError("--setup and --watch cannot be used together.")
    if dry_run and watch:
        raise ValueError("--dry-run and --watch cannot be used together.")

    setup_provider: str | None = None
    setup_model: str | None = None
    setup_detected_via: str | None = None
    config_written = False

    if setup:
        detected = detect_provider()
        if detected is None:
            raise ValueError(
                "No LLM provider detected. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or start Ollama / LM Studio."
            )
        setup_provider, setup_model = detected
        setup_detected_via = PROVIDER_DETECTED_VIA.get(setup_provider, setup_provider)
        if not dry_run:
            write_default_config(
                root,
                setup_provider,
                model=setup_model,
                base_url=DEFAULT_BASE_URLS.get(setup_provider),
            )
            config_written = True
        provider = provider or setup_provider
        model = model or setup_model
        base_url = base_url or DEFAULT_BASE_URLS.get(setup_provider)

    changed_files: list[Path] | None = None
    if force:
        strategy = "full"
    elif not _has_manifests(root):
        strategy = "full"
    else:
        try:
            changed_files = get_changed_files(root)
        except RuntimeError as exc:
            logger.info(
                "Git-aware refresh unavailable for %s: %s. Falling back to incremental refresh.",
                root,
                exc,
            )
            changed_files = None
        strategy = "smart" if changed_files else "incremental"

    if dry_run:
        config = load_config(
            root,
            provider=provider,
            model=model,
            max_depth=max_depth,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
            require_api_key=False,
        )
        spec = load_ignore_patterns(root)
        stale = check_stale_dirs(root, config, spec, changed_files=changed_files if strategy == "smart" else None)
        return RefreshResult(
            dirs_processed=0,
            dirs_skipped=len(stale),
            files_processed=0,
            tokens_used=0,
            errors=[],
            budget_exhausted=False,
            strategy=strategy,
            est_cost_usd=0.0,
            stale_directories=[_path_relative(directory, root) for directory in stale],
            config_written=config_written,
            setup_provider=setup_provider,
            setup_model=setup_model,
            setup_detected_via=setup_detected_via,
        )

    try:
        config, spec, client = _build_generation_runtime(
            root,
            provider=provider,
            model=model,
            max_depth=max_depth,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
        )
    except MissingApiKeyError as exc:
        config_path = _find_config_path(root)
        if provider is not None:
            raise MissingApiKeyError(f"{exc} (while loading provider '{provider}')") from exc
        if config_path is not None:
            raise MissingApiKeyError(f"{exc} (while loading configuration from {config_path})") from exc
        env_provider = os.getenv("CTX_PROVIDER", "").strip()
        if env_provider:
            raise MissingApiKeyError(
                f"{exc} (while loading provider '{env_provider}' from CTX_PROVIDER)"
            ) from exc
        detected = detect_provider()
        if detected is None:
            raise
        setup_provider, setup_model = detected
        setup_detected_via = PROVIDER_DETECTED_VIA.get(setup_provider, setup_provider)
        detected_base_url = DEFAULT_BASE_URLS.get(setup_provider)
        if setup_provider in LOCAL_PROVIDERS and not dry_run:
            write_default_config(root, setup_provider, model=setup_model, base_url=detected_base_url)
            config_written = True
        config, spec, client = _build_generation_runtime(
            root,
            provider=setup_provider,
            model=model or setup_model,
            max_depth=max_depth,
            token_budget=token_budget,
            base_url=base_url or detected_base_url,
            cache_path=cache_path,
        )

    _apply_token_guardrail(config)

    cumulative_stats = GenerateStats()

    while True:
        with CtxLock(root, command="refresh"):
            stats: GenerateStats
            if strategy == "full" and cumulative_stats.dirs_processed == 0:
                stats = generate_tree(root, config, client, spec, progress=progress)
            elif strategy == "smart":
                stats = update_tree(root, config, client, spec, progress=progress, changed_files=changed_files)
            else:
                stats = update_tree(root, config, client, spec, progress=progress)

        cumulative_stats.dirs_processed += stats.dirs_processed
        cumulative_stats.dirs_skipped += stats.dirs_skipped
        cumulative_stats.files_processed += stats.files_processed
        cumulative_stats.files_binary += stats.files_binary
        cumulative_stats.tokens_used += stats.tokens_used
        # Replace (not extend) errors each pass so that directories which
        # were retried and succeeded no longer appear as errors.
        cumulative_stats.errors = list(stats.errors)
        cumulative_stats.budget_exhausted = stats.budget_exhausted
        cumulative_stats.local_batch_fallbacks = max(
            cumulative_stats.local_batch_fallbacks,
            stats.local_batch_fallbacks,
        )

        if not until_complete:
            break
        # No forward progress this pass — stop to avoid infinite loops.
        if stats.dirs_processed == 0:
            break
        # Clean completion: no budget limit hit and no errors.
        if not stats.budget_exhausted and not stats.errors:
            break
        # Honor hard USD ceiling across cycles.  (The token budget is
        # per-pass by design — _apply_token_guardrail folds it into the
        # generator budget so each pass stops independently.)
        if config.max_usd_per_run is not None:
            est_cost = estimate_cost(cumulative_stats.tokens_used, config.provider, config.resolved_model())
            if est_cost >= config.max_usd_per_run:
                break

        reason = "budget" if stats.budget_exhausted else "errors"
        logger.info(
            "Cycle complete (%d dirs, %s). Cooling down %.0fs before next cycle.",
            cumulative_stats.dirs_processed,
            reason,
            config.resume_cooldown_seconds,
        )
        _time.sleep(config.resume_cooldown_seconds)
        strategy = "incremental"

    budget_guardrail = _budget_guardrail_message(config, cumulative_stats)
    errors = list(cumulative_stats.errors)
    if budget_guardrail is not None:
        errors.append(budget_guardrail)

    if watch and not errors:
        run_watch(root, config, client, spec)

    cache_hits, cache_misses = (
        client.hit_miss_counts
        if hasattr(client, "hit_miss_counts")
        else (0, 0)
    )

    result = RefreshResult(
        dirs_processed=cumulative_stats.dirs_processed,
        dirs_skipped=cumulative_stats.dirs_skipped,
        files_processed=cumulative_stats.files_processed,
        tokens_used=cumulative_stats.tokens_used,
        errors=errors,
        budget_exhausted=cumulative_stats.budget_exhausted or budget_guardrail is not None,
        strategy=strategy,
        est_cost_usd=estimate_cost(cumulative_stats.tokens_used, config.provider, config.resolved_model()),
        stale_directories=[],
        budget_guardrail=budget_guardrail,
        config_written=config_written,
        setup_provider=setup_provider,
        setup_model=setup_model,
        setup_detected_via=setup_detected_via,
        local_batch_fallbacks=int(getattr(client, "local_batch_fallbacks", 0) or 0),
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )

    if not dry_run:
        try:
            from ctx.stats_board import record_run
            record_run(root, result, config)
        except Exception as exc:
            logger.warning("Stats recording failed: %s", exc)

    return result


def _path_relative(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return rel or "."


def _check_tier2(
    root: Path,
    *,
    verify: bool = False,
    stats: bool = False,
    diff: bool = False,
    verbose: bool = False,
    check_exit: bool = False,
    quiet: bool = False,
    stat: bool = False,
) -> CheckResult:
    """Evaluate freshness, coverage, and structure for a Tier 2 (.ctx/-only) repository."""
    from ctx.generator import _estimate_tokens
    from ctx.sdk import CtxProject
    from ctx.stats_board import load_json_safe

    ctx_dir = root / ".ctx"
    expected_exports = ("CONTEXT.md", "CONTEXT-0.md", "CONTEXT-1.md")
    missing_exports = [name for name in expected_exports if not (ctx_dir / name).is_file()]
    proj = CtxProject.load(root, walk_parents=False)
    is_stale_flag = proj.is_stale() if proj is not None else True

    if len(missing_exports) == len(expected_exports):
        status = "missing"
    elif missing_exports or is_stale_flag:
        status = "stale"
    else:
        status = "fresh"

    full_map_path = ctx_dir / "CONTEXT.md"
    full_map_text = full_map_path.read_text(encoding="utf-8") if full_map_path.is_file() else ""
    tokens_est = _estimate_tokens(full_map_text) if full_map_text else 0

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
            issues = [f"Missing Tier 2 export: .ctx/{name}" for name in missing_exports]
            if not has_valid_header:
                issues.append("Tier 2 .ctx/CONTEXT.md is missing valid mode: tier2 frontmatter.")
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
    hook_log_path = ctx_dir / "hook_log.json"
    if hook_log_path.is_file():
        hook_data = load_json_safe(hook_log_path, {"runs": []})
        runs = hook_data.get("runs", []) if isinstance(hook_data, dict) else []
        if isinstance(runs, list):
            summary["hook_runs"] = len(runs)
            summary["hook_failures"] = sum(
                1 for r in runs if isinstance(r, dict) and not r.get("success", True)
            )
    return CheckResult(mode="health", directories=directories, summary=summary)


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
    """Run canonical check behavior."""
    modes = [verify, stats, diff]
    if sum(1 for enabled in modes if enabled) > 1:
        raise ValueError("Only one check mode may be selected.")

    if _is_tier2_repo(root):
        return _check_tier2(
            root,
            verify=verify,
            stats=stats,
            diff=diff,
            verbose=verbose,
            check_exit=check_exit,
            quiet=quiet,
            stat=stat,
        )

    if diff:
        ref = since or "HEAD"
        modified: list[str] = []
        new_files: list[str] = []
        stale: list[str] = []
        git_available = True

        def _split_lines(stdout: str) -> list[str]:
            return [line.strip() for line in stdout.splitlines() if line.strip()]

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", ref, "--", "*/CONTEXT.md", "CONTEXT.md"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
            )
            changed = _split_lines(result.stdout)
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "--", "*/CONTEXT.md", "CONTEXT.md"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
            )
            new_files = sorted(set(_split_lines(untracked.stdout)))
            new_set = set(new_files)
            modified = sorted(line for line in changed if line not in new_set)
        except (FileNotFoundError, subprocess.CalledProcessError):
            git_available = False

        if not git_available:
            if since is not None:
                raise ValueError("--since requires git to be available and the path to be inside a git repository.")
            for manifest in _iter_tree_manifests(root):
                try:
                    manifest_mtime = manifest.stat().st_mtime
                    if any(
                        entry.stat().st_mtime > manifest_mtime
                        for entry in manifest.parent.iterdir()
                        if entry.is_file() and entry.name != "CONTEXT.md"
                    ):
                        stale.append(_path_relative(manifest, root))
                except OSError:
                    continue

        directories = []
        if modified:
            directories.extend({"path": path, "status": "modified"} for path in modified)
        if new_files:
            directories.extend({"path": path, "status": "new"} for path in new_files)
        if stale:
            directories.extend({"path": path, "status": "stale"} for path in stale)
        summary = {"modified": len(modified), "new": len(new_files), "stale": len(stale), "quiet": quiet, "stat": stat}
        return CheckResult(mode="diff", directories=directories, summary=summary)

    spec = load_ignore_patterns(root)
    health_entries = inspect_directory_health(root, spec, root)

    if stats:
        directories = []
        if verbose:
            directories = [
                {
                    "path": entry.relative_path,
                    "status": "covered" if entry.status == "fresh" else entry.status,
                    "tokens": entry.tokens_total,
                }
                for entry in health_entries
            ]
        summary = {
            "dirs": len(health_entries),
            "covered": sum(1 for entry in health_entries if entry.status != "missing"),
            "missing": sum(1 for entry in health_entries if entry.status == "missing"),
            "stale": sum(1 for entry in health_entries if entry.status == "stale"),
            "tokens": sum(entry.tokens_total or 0 for entry in health_entries),
        }
        return CheckResult(mode="stats", directories=directories, summary=summary)

    if verify:
        required_fields = ["generated", "generator", "model", "content_hash", "files", "dirs", "tokens_total"]
        malformed = sorted(entry.relative_path for entry in health_entries if entry.error is not None)
        missing = sorted(entry.relative_path for entry in health_entries if entry.status == "missing")
        missing_fields: list[dict[str, object]] = []
        for entry in health_entries:
            if entry.status == "missing" or entry.error is not None or entry.frontmatter is None:
                continue
            missing_field_names: list[str] = []
            for field in required_fields:
                value = getattr(entry.frontmatter, field, None)
                if value is None or value == "":
                    missing_field_names.append(field)
            if missing_field_names:
                missing_fields.append({"path": entry.relative_path, "fields": missing_field_names})

        invalid_field_paths = {item["path"] for item in missing_fields}
        invalid_bodies: list[dict[str, object]] = []
        for entry in health_entries:
            if (
                entry.status != "fresh"
                or entry.error is not None
                or entry.frontmatter is None
                or entry.relative_path in invalid_field_paths
            ):
                continue
            manifest = read_manifest(entry.path)
            if manifest is None:
                continue
            issues = validate_manifest_body(entry.path, root, spec, manifest)
            if issues:
                invalid_bodies.append({"path": entry.relative_path, "status": "invalid_body", "issues": issues})

        stale = sorted(
            entry.relative_path
            for entry in health_entries
            if entry.status == "stale"
            and entry.error is None
            and entry.relative_path not in invalid_field_paths
        )
        directories: list[dict] = []
        directories.extend({"path": path, "status": "malformed"} for path in malformed)
        directories.extend({"path": item["path"], "status": "missing_fields", "fields": item["fields"]} for item in missing_fields)
        directories.extend(invalid_bodies)
        directories.extend({"path": path, "status": "stale"} for path in stale)
        directories.extend({"path": path, "status": "missing"} for path in missing)
        summary = {
            "dirs": len(health_entries),
            "fresh": sum(1 for entry in health_entries if entry.status == "fresh"),
            "stale": sum(1 for entry in health_entries if entry.status == "stale"),
            "missing": len(missing),
            "invalid": len({*malformed, *stale, *missing, *invalid_field_paths, *(item["path"] for item in invalid_bodies)}),
            "invalid_body": len(invalid_bodies),
            "check_exit": check_exit,
        }
        return CheckResult(mode="verify", directories=directories, summary=summary)

    directories = [{"path": entry.relative_path, "status": entry.status} for entry in health_entries]
    counts = Counter(entry.status for entry in health_entries)
    summary: dict[str, object] = {
        "total": len(health_entries),
        "fresh": counts.get("fresh", 0),
        "stale": counts.get("stale", 0),
        "missing": counts.get("missing", 0),
        "check_exit": check_exit,
    }
    hook_log_path = root / ".ctx" / "hook_log.json"
    if hook_log_path.is_file():
        from ctx.stats_board import load_json_safe

        hook_data = load_json_safe(hook_log_path, {"runs": []})
        runs = hook_data.get("runs", []) if isinstance(hook_data, dict) else []
        if isinstance(runs, list):
            summary["hook_runs"] = len(runs)
            summary["hook_failures"] = sum(
                1 for r in runs if isinstance(r, dict) and not r.get("success", True)
            )
    return CheckResult(mode="health", directories=directories, summary=summary)


def export_context(
    root: Path,
    *,
    output_file: str | None = None,
    filter_mode: str = "all",
    depth: int | None = None,
) -> ExportResult:
    """Export manifests with filter/depth controls."""
    if _is_tier2_repo(root):
        from ctx.sdk import CtxProject

        if depth == 0:
            target_name = "CONTEXT-0.md"
        elif depth == 1:
            target_name = "CONTEXT-1.md"
        else:
            target_name = "CONTEXT.md"
        target_file = root / ".ctx" / target_name
        label = f".ctx/{target_name}"
        proj = CtxProject.load(root, walk_parents=False)
        is_stale_flag = proj.is_stale() if proj is not None else True

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

        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
        return ExportResult(
            manifests_exported=count,
            filter=filter_mode,
            depth=depth,
            content=content,
        )

    spec = load_ignore_patterns(root)
    health_entries = [
        entry
        for entry in inspect_directory_health(root, spec, root)
        if _directory_within_depth(entry.path, root, depth)
    ]

    if filter_mode == "missing":
        missing_dirs: list[str] = []
        for entry in health_entries:
            if entry.status != "missing":
                continue
            rel_display = entry.relative_path if entry.relative_path != "." else ""
            missing_dirs.append((rel_display + "/") if rel_display else "./")
        content = "\n".join(f"# {directory} [MISSING]" for directory in missing_dirs)
        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
        return ExportResult(
            manifests_exported=len(missing_dirs),
            filter=filter_mode,
            depth=depth,
            content=content,
        )

    files = [
        entry.path / "CONTEXT.md"
        for entry in health_entries
        if entry.status != "missing" and (filter_mode != "stale" or entry.status == "stale")
    ]
    parts: list[str] = []
    for file_path in files:
        rel = _path_relative(file_path, root)
        parts.append(f"# {rel}\n\n{file_path.read_text(encoding='utf-8')}")
    content = "\n\n".join(parts)

    if output_file:
        Path(output_file).write_text(content, encoding="utf-8")
    return ExportResult(
        manifests_exported=len(files),
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
    """Remove CONTEXT.md files from a tree."""
    manifests = _iter_tree_manifests(root)
    paths = [_path_relative(manifest, root) for manifest in manifests]

    if dry_run:
        return ResetResult(manifests_removed=0, paths=paths)

    if not yes:
        raise ConfirmationRequiredError("--yes flag required in non-interactive mode")

    with CtxLock(root, command="reset"):
        for manifest in manifests:
            manifest.unlink()

    return ResetResult(manifests_removed=len(manifests), paths=paths)


def build_fleet_capsule(
    root: Path,
    *,
    depth: int | None = 1,
    output_file: str | None = None,
) -> FleetCapsuleResult:
    """Generate a compact deterministic capsule for project-ledger and gbrain ingestion."""
    import hashlib
    import json
    from dataclasses import asdict
    from ctx.skeleton import extract_skeleton, render_context_0, render_context_1

    resolved_root = root.resolve()
    skeleton = extract_skeleton(resolved_root)
    repo_id = f"sha256:{hashlib.sha256(str(resolved_root).encode('utf-8')).hexdigest()}"

    authority_boundaries = [
        {
            "path": doc.relative_path,
            "kind": doc.kind,
            "headings": list(doc.headings),
            "summary": doc.summary_line,
            "content_hash": doc.content_hash,
        }
        for doc in skeleton.boundary_docs
    ]

    filtered_subsystems = []
    for sub in skeleton.subsystems:
        if depth is not None and sub.path != ".":
            sub_depth = len(Path(sub.path).parts)
            # Treat src/<pkg> as depth 1 logical subsystem for capsule ingestion
            effective_depth = 1 if (Path(sub.path).parts[0] == "src" and sub_depth == 2) else sub_depth
            if effective_depth > depth:
                continue
        filtered_subsystems.append(
            {
                "path": sub.path,
                "file_count": sub.file_count,
                "languages": list(sub.languages),
                "key_symbols": list(sub.key_symbols[:10]),
                "internal_deps": list(sub.internal_deps),
                "external_deps": list(sub.external_deps),
            }
        )

    capsule_md = render_context_0(skeleton)
    if depth is None or depth >= 1:
        c1_lines = render_context_1(skeleton).splitlines()[12:]
        capsule_md = (
            capsule_md.removesuffix("<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->\n")
            + "\n"
            + "\n".join(c1_lines)
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
        entrypoints=list(skeleton.entrypoints),
        authority_boundaries=authority_boundaries,
        subsystems=filtered_subsystems,
        capsule_markdown=capsule_md,
    )

    if output_file:
        out_path = Path(output_file)
        if out_path.suffix.lower() == ".json":
            out_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        else:
            out_path.write_text(capsule_md, encoding="utf-8")

    return result

