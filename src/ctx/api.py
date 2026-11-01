"""Unified API layer for ctx canonical commands."""

from __future__ import annotations

import logging
import os
import subprocess
import time as _time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ctx.config import (
    DEFAULT_BASE_URLS,
    LOCAL_PROVIDERS,
    MissingApiKeyError,
    PROVIDER_DETECTED_VIA,
    Config,
    _iter_config_dirs,
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
from ctx.lock import (
    CtxLock,
    LockSupersededError,
    assert_lock_ownership_for_path,
    fenced_mkdir,
    fenced_unlink,
)


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
    tokens_saved: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    input_tokens_saved: int = 0
    output_tokens_saved: int = 0
    tokens_saved_exact: bool = False
    warnings: list[str] = field(default_factory=list)


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
    operational_surfaces: list[dict[str, object]] = field(default_factory=list)
    dependency_summary: dict[str, object] = field(default_factory=dict)


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
    for directory in _iter_config_dirs(start_dir):
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


def _resolve_tier2_root(root: Path) -> Path | None:
    """Return the enclosing Tier 2 project root if *root* (or its project anchor) is in Tier 2 mode."""
    from ctx.config import resolve_project_anchor
    from ctx.stats_board import load_json_safe

    candidates = [root]
    if root.exists():
        anchor = resolve_project_anchor(root)
        if anchor not in candidates:
            candidates.append(anchor)

    for candidate in candidates:
        meta_path = candidate / ".ctx" / "metadata.json"
        if not meta_path.is_file():
            continue
        data = load_json_safe(meta_path, {})
        if isinstance(data, dict) and data.get("mode") == "tier2":
            return candidate
    return None


def _is_tier2_repo(root: Path) -> bool:
    """Return True when *root* (or its enclosing project anchor) is initialized in Tier 2 (.ctx/ mode: tier2)."""
    return _resolve_tier2_root(root) is not None


def _refresh_tier2_locked(
    root: Path,
    *,
    force: bool = False,
    max_depth: int | None = None,
    touch_last_refresh: bool = False,
    synthesize: bool = False,
    provider: str | None = None,
    model: str | None = None,
    token_budget: int | None = None,
    base_url: str | None = None,
) -> RefreshResult | None:
    """Refresh Tier 2 (.ctx/) maps while the caller already holds CtxLock(root).

    Returns None when .ctx/metadata.json no longer declares mode == 'tier2'.
    """
    from datetime import datetime, timezone

    from ctx.config import resolve_tier2_synthesize_preference
    from ctx.init import _restore_dir_snapshot, _snapshot_dir
    from ctx.invariants import (
        has_cached_synthesis_for_hashes,
        synthesize_tier2_invariants,
    )
    from ctx.skeleton import (
        extract_skeleton,
        render_context_0,
        render_context_1,
        render_context_full,
        should_invoke_llm,
    )
    from ctx.stats_board import load_json_safe, save_json_atomic, write_text_atomic

    ctx_dir = root / ".ctx"
    meta_path = ctx_dir / "metadata.json"
    expected_exports = ("CONTEXT.md", "CONTEXT-1.md", "CONTEXT-0.md")

    meta_exists = meta_path.is_file()
    meta = load_json_safe(meta_path, {}) if meta_exists else {}
    if not (meta_exists and isinstance(meta, dict) and meta.get("mode") == "tier2"):
        return None

    prev_synth_flag = bool(meta.get("synthesize_invariants", False))
    should_synth = resolve_tier2_synthesize_preference(
        root,
        explicit_flag=synthesize,
        persisted_meta=meta,
    )
    synth_toggled = should_synth != prev_synth_flag

    skeleton = extract_skeleton(root, max_depth=max_depth)
    exports_missing = any(
        not (ctx_dir / name).is_file() or (ctx_dir / name).stat().st_size == 0
        for name in expected_exports
    )
    missing_synth_cache = should_synth and not has_cached_synthesis_for_hashes(
        root,
        skeleton.structural_hash,
        skeleton.boundary_doc_hash,
    )
    needs_update = (
        force
        or exports_missing
        or synth_toggled
        or missing_synth_cache
        or should_invoke_llm(meta, skeleton)
    )
    subsystem_count = max(1, len(skeleton.subsystems))

    if not needs_update:
        if touch_last_refresh and meta_path.is_file():
            meta["last_refresh"] = datetime.now(timezone.utc).isoformat()
            save_json_atomic(meta_path, meta)
        return RefreshResult(
            dirs_processed=0,
            dirs_skipped=subsystem_count,
            files_processed=0,
            tokens_used=0,
            errors=[],
            budget_exhausted=False,
            strategy="tier2",
            est_cost_usd=0.0,
            stale_directories=[],
        )

    prior_snapshot = _snapshot_dir(ctx_dir)
    tokens_used = 0
    in_tok = 0
    out_tok = 0
    est_cost = 0.0
    budget_exhausted = False
    budget_guardrail: str | None = None
    refresh_warnings: list[str] = []
    synth_model: str | None = model
    try:
        fenced_mkdir(ctx_dir, parents=True, exist_ok=True)
        synthesized_invs: list[dict[str, str]] | None = None
        if should_synth:
            inv_res = synthesize_tier2_invariants(
                root,
                skeleton,
                prev_metadata=meta,
                force=force,
                provider=provider,
                model=model,
                token_budget=token_budget,
                base_url=base_url,
            )
            synthesized_invs = inv_res.invariants or None
            tokens_used = inv_res.tokens_used
            in_tok = inv_res.input_tokens
            out_tok = inv_res.output_tokens
            est_cost = inv_res.est_cost_usd
            budget_exhausted = inv_res.budget_exhausted
            budget_guardrail = inv_res.budget_guardrail
            synth_model = inv_res.model or model
            meta["synthesize_invariants"] = True
            meta["invariants_gate_action"] = inv_res.gate_action
            if inv_res.warning:
                meta["invariants_warning"] = inv_res.warning
                refresh_warnings.append(inv_res.warning)
            else:
                meta.pop("invariants_warning", None)
        else:
            meta["synthesize_invariants"] = False
            meta.pop("invariants_warning", None)

        rendered_c0 = render_context_0(skeleton, synthesized_invariants=synthesized_invs)
        rendered_c1 = render_context_1(skeleton, synthesized_invariants=synthesized_invs)
        rendered_full = render_context_full(skeleton, synthesized_invariants=synthesized_invs)
        write_text_atomic(ctx_dir / "CONTEXT-0.md", rendered_c0)
        write_text_atomic(ctx_dir / "CONTEXT-1.md", rendered_c1)
        write_text_atomic(ctx_dir / "CONTEXT.md", rendered_full)
        meta["mode"] = "tier2"
        meta["structural_hash"] = skeleton.structural_hash
        meta["boundary_doc_hash"] = skeleton.boundary_doc_hash
        meta["last_refresh"] = datetime.now(timezone.utc).isoformat()
        save_json_atomic(meta_path, meta)
    except LockSupersededError:
        raise
    except Exception:
        _restore_dir_snapshot(ctx_dir, prior_snapshot)
        raise

    tier2_errors: list[str] = [budget_guardrail] if budget_guardrail is not None else []
    tier2_result = RefreshResult(
        dirs_processed=subsystem_count,
        dirs_skipped=0,
        files_processed=skeleton.total_files,
        tokens_used=tokens_used,
        errors=tier2_errors,
        budget_exhausted=budget_exhausted,
        strategy="tier2",
        est_cost_usd=est_cost,
        stale_directories=[],
        budget_guardrail=budget_guardrail,
        input_tokens=in_tok,
        output_tokens=out_tok,
        warnings=refresh_warnings,
    )
    if tokens_used > 0 or est_cost > 0.0:
        try:
            from ctx.stats_board import record_run

            tier2_cfg = load_config(
                root,
                provider=provider,
                model=synth_model,
                token_budget=token_budget,
                base_url=base_url,
                require_api_key=False,
            )
            record_run(root, tier2_result, tier2_cfg)
        except Exception as exc:
            logger.warning("Tier 2 stats recording failed: %s", exc)
    return tier2_result


def _refresh_tier2(
    root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    max_depth: int | None = None,
    touch_last_refresh: bool = False,
    synthesize: bool = False,
    provider: str | None = None,
    model: str | None = None,
    token_budget: int | None = None,
    base_url: str | None = None,
    _allow_fallback: bool = True,
    _from_hook: bool = False,
    _mode_hops: int = 0,
    _fallback_kwargs: dict[str, object] | None = None,
) -> RefreshResult:
    """Refresh deterministic Tier 2 (.ctx/) architectural maps without requiring LLM credentials."""
    from ctx.skeleton import extract_skeleton, should_invoke_llm
    from ctx.stats_board import load_json_safe

    ctx_dir = root / ".ctx"
    meta_path = ctx_dir / "metadata.json"
    expected_exports = ("CONTEXT.md", "CONTEXT-1.md", "CONTEXT-0.md")

    if dry_run:
        from ctx.config import resolve_tier2_synthesize_preference
        from ctx.invariants import has_cached_synthesis_for_hashes

        meta = load_json_safe(meta_path, {})
        if not isinstance(meta, dict):
            meta = {}
        prev_synth_flag = bool(meta.get("synthesize_invariants", False))
        should_synth = resolve_tier2_synthesize_preference(
            root,
            explicit_flag=synthesize,
            persisted_meta=meta,
        )
        synth_toggled = should_synth != prev_synth_flag
        skeleton = extract_skeleton(root, max_depth=max_depth)
        exports_missing = any(
            not (ctx_dir / name).is_file() or (ctx_dir / name).stat().st_size == 0
            for name in expected_exports
        )
        missing_synth_cache = should_synth and not has_cached_synthesis_for_hashes(
            root,
            skeleton.structural_hash,
            skeleton.boundary_doc_hash,
        )
        needs_update = (
            force
            or exports_missing
            or synth_toggled
            or missing_synth_cache
            or should_invoke_llm(meta, skeleton)
        )
        stale_dirs = ["."] if needs_update else []
        return RefreshResult(
            dirs_processed=0,
            dirs_skipped=len(stale_dirs),
            files_processed=0,
            tokens_used=0,
            errors=[],
            budget_exhausted=False,
            strategy="tier2",
            est_cost_usd=0.0,
            stale_directories=stale_dirs,
        )

    with CtxLock(root, command="refresh"):
        locked_result = _refresh_tier2_locked(
            root,
            force=force,
            max_depth=max_depth,
            touch_last_refresh=touch_last_refresh,
            synthesize=synthesize,
            provider=provider,
            model=model,
            token_budget=token_budget,
            base_url=base_url,
        )
        if locked_result is not None:
            return locked_result
        if _from_hook and not meta_path.is_file():
            return RefreshResult(
                dirs_processed=0,
                dirs_skipped=0,
                files_processed=0,
                tokens_used=0,
                errors=[],
                budget_exhausted=False,
                strategy="tier2",
                est_cost_usd=0.0,
                stale_directories=[],
            )

    if _allow_fallback and _mode_hops < 4:
        fb_kwargs = dict(_fallback_kwargs or {})
        fb_kwargs.update(
            force=force,
            dry_run=dry_run,
            max_depth=max_depth,
            _mode_hops=_mode_hops + 1,
        )
        return refresh(root, **fb_kwargs)
    return RefreshResult(
        dirs_processed=0,
        dirs_skipped=0,
        files_processed=0,
        tokens_used=0,
        errors=[],
        budget_exhausted=False,
        strategy="tier2",
        est_cost_usd=0.0,
        stale_directories=[],
    )


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


def _estimate_usage_cost(
    tokens_used: int,
    input_tokens: int,
    output_tokens: int,
    provider: str,
    model: str,
) -> float:
    if input_tokens > 0 or output_tokens > 0:
        remainder = max(0, tokens_used - (input_tokens + output_tokens))
        return estimate_cost(
            tokens_used,
            provider,
            model,
            input_tokens=input_tokens + remainder,
            output_tokens=output_tokens,
        )
    return estimate_cost(tokens_used, provider, model)


def _budget_guardrail_message(config: Config, stats: GenerateStats) -> str | None:
    """Return a hard-budget error message when a Stage 3 guardrail is hit."""

    if config.max_tokens_per_run is not None and stats.tokens_used >= config.max_tokens_per_run:
        return (
            f"Token budget guardrail reached: {stats.tokens_used:,} tokens used "
            f"(limit {config.max_tokens_per_run:,})."
        )
    if config.max_usd_per_run is not None:
        est_cost = _estimate_usage_cost(
            stats.tokens_used,
            stats.input_tokens,
            stats.output_tokens,
            config.provider,
            config.resolved_model(),
        )
        if est_cost >= config.max_usd_per_run:
            return (
                f"USD budget guardrail reached: ${est_cost:.4f} estimated spend "
                f"(limit ${config.max_usd_per_run:.4f})."
            )
    return None


def _sync_tier1_ctx_exports(root: Path) -> None:
    """Atomically synchronize .ctx/ exports and metadata while holding CtxLock."""
    from ctx.config import resolve_project_anchor

    target_root = resolve_project_anchor(root) if root.exists() else root
    meta_path = target_root / ".ctx" / "metadata.json"
    if not meta_path.is_file() or _resolve_tier2_root(target_root) is not None:
        return
    try:
        from datetime import datetime, timezone

        from ctx.init import _populate_ctx_dir
        from ctx.stats_board import load_json_safe, save_json_atomic

        _populate_ctx_dir(target_root, target_root / ".ctx")
        meta = load_json_safe(meta_path, {})
        if isinstance(meta, dict):
            meta["last_refresh"] = datetime.now(timezone.utc).isoformat()
            save_json_atomic(meta_path, meta)
    except LockSupersededError:
        raise
    except Exception as exc:
        logger.warning("Tier 1 .ctx/ export sync failed: %s", exc)


def refresh(
    root: Path,
    *,
    force: bool = False,
    setup: bool = False,
    watch: bool = False,
    dry_run: bool = False,
    until_complete: bool = False,
    synthesize: bool = False,
    provider: str | None = None,
    model: str | None = None,
    max_depth: int | None = None,
    token_budget: int | None = None,
    base_url: str | None = None,
    cache_path: str | None = None,
    progress: ProgressCallback | None = None,
    _force_tier1: bool = False,
    _on_locked_begin: Callable[[], None] | None = None,
    _on_locked_success: Callable[[], None] | None = None,
    _on_locked_rollback: Callable[[], None] | None = None,
    _mode_hops: int = 0,
) -> RefreshResult:
    """Run canonical refresh behavior with strategy selection."""
    from ctx.config import resolve_project_anchor
    from ctx.git import get_changed_files

    if setup and watch:
        raise ValueError("--setup and --watch cannot be used together.")
    if dry_run and watch:
        raise ValueError("--dry-run and --watch cannot be used together.")

    fallback_kwargs: dict[str, object] = {
        "until_complete": until_complete,
        "synthesize": synthesize,
        "provider": provider,
        "model": model,
        "token_budget": token_budget,
        "base_url": base_url,
        "cache_path": cache_path,
        "progress": progress,
    }

    tier2_root = None if _force_tier1 else _resolve_tier2_root(root)
    if tier2_root is not None:
        if setup or watch:
            unsupported = "--setup" if setup else "--watch"
            raise ValueError(
                f"{unsupported} is not supported in Tier 2 (.ctx/-only) repositories. "
                "Run 'ctx init --force' to switch to Tier 1 per-directory manifests."
            )
        return _refresh_tier2(
            tier2_root,
            force=force,
            dry_run=dry_run,
            max_depth=max_depth,
            synthesize=synthesize,
            provider=provider,
            model=model,
            token_budget=token_budget,
            base_url=base_url,
            _allow_fallback=_mode_hops < 4,
            _mode_hops=_mode_hops,
            _fallback_kwargs=fallback_kwargs,
        )

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
    preexisting_manifests: dict[Path, bytes] = {}
    tx_started = False
    manifests_snapshotted = False

    def _rollback_manifests() -> None:
        from ctx.init import _write_bytes_atomic

        assert_lock_ownership_for_path(root)
        for manifest_path in _iter_tree_manifests(root):
            if manifest_path not in preexisting_manifests:
                fenced_unlink(manifest_path, missing_ok=True)
        for manifest_path, prior_bytes in preexisting_manifests.items():
            _write_bytes_atomic(manifest_path, prior_bytes)

    switched_to_tier2_root: Path | None = None
    while True:
        should_continue_cycles = False
        lock_root = resolve_project_anchor(root) if root.exists() else root
        with CtxLock(lock_root, command="refresh"):
            if not _force_tier1:
                locked_tier2_root = _resolve_tier2_root(root)
                if locked_tier2_root is not None:
                    if setup or watch:
                        unsupported = "--setup" if setup else "--watch"
                        raise ValueError(
                            f"{unsupported} is not supported in Tier 2 (.ctx/-only) repositories. "
                            "Run 'ctx init --force' to switch to Tier 1 per-directory manifests."
                        )
                    if locked_tier2_root.resolve() == lock_root.resolve():
                        inline_tier2 = _refresh_tier2_locked(
                            locked_tier2_root,
                            force=force,
                            max_depth=max_depth,
                            synthesize=synthesize,
                            provider=provider,
                            model=model,
                            token_budget=token_budget,
                            base_url=base_url,
                        )
                        if inline_tier2 is not None:
                            return inline_tier2
                    else:
                        switched_to_tier2_root = locked_tier2_root
                        break

            try:
                if not tx_started:
                    tx_started = True
                    if _on_locked_begin is not None:
                        _on_locked_begin()
                        spec = load_ignore_patterns(root)
                        if not force:
                            strategy = "full" if not _has_manifests(root) else "incremental"
                            changed_files = None
                    elif not force and not _has_manifests(root):
                        strategy = "full"
                        changed_files = None
                    if _on_locked_success is not None or _on_locked_rollback is not None:
                        preexisting_manifests = {
                            p: p.read_bytes() for p in _iter_tree_manifests(root)
                        }
                        manifests_snapshotted = True

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
                cumulative_stats.input_tokens += stats.input_tokens
                cumulative_stats.output_tokens += stats.output_tokens
                # Replace (not extend) errors each pass so that directories which
                # were retried and succeeded no longer appear as errors.
                cumulative_stats.errors = list(stats.errors)
                cumulative_stats.budget_exhausted = stats.budget_exhausted
                cumulative_stats.local_batch_fallbacks = max(
                    cumulative_stats.local_batch_fallbacks,
                    stats.local_batch_fallbacks,
                )
                cumulative_stats.cache_hits += stats.cache_hits
                cumulative_stats.cache_misses += stats.cache_misses
                cumulative_stats.tokens_saved += stats.tokens_saved
                cumulative_stats.input_tokens_saved += stats.input_tokens_saved
                cumulative_stats.output_tokens_saved += stats.output_tokens_saved
                cumulative_stats.tokens_saved_exact = (
                    cumulative_stats.tokens_saved_exact or stats.tokens_saved_exact
                )

                if (
                    until_complete
                    and stats.dirs_processed > 0
                    and (stats.budget_exhausted or bool(stats.errors))
                ):
                    should_continue_cycles = True
                    if config.max_usd_per_run is not None:
                        est_cost = _estimate_usage_cost(
                            cumulative_stats.tokens_used,
                            cumulative_stats.input_tokens,
                            cumulative_stats.output_tokens,
                            config.provider,
                            config.resolved_model(),
                        )
                        if est_cost >= config.max_usd_per_run:
                            should_continue_cycles = False

                if not should_continue_cycles and not dry_run:
                    if _on_locked_success is not None:
                        if cumulative_stats.errors or not (root / "CONTEXT.md").is_file():
                            err_detail = (
                                cumulative_stats.errors[0]
                                if cumulative_stats.errors
                                else f"Failed to generate root CONTEXT.md in {root}"
                            )
                            raise RuntimeError(err_detail)
                        _on_locked_success()
                    else:
                        _sync_tier1_ctx_exports(root)
            except LockSupersededError:
                raise
            except Exception:
                if manifests_snapshotted:
                    _rollback_manifests()
                if _on_locked_rollback is not None:
                    _on_locked_rollback()
                raise

        if not should_continue_cycles:
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

    if switched_to_tier2_root is not None:
        return _refresh_tier2(
            switched_to_tier2_root,
            force=force,
            dry_run=dry_run,
            max_depth=max_depth,
            synthesize=synthesize,
            provider=provider,
            model=model,
            token_budget=token_budget,
            base_url=base_url,
            _allow_fallback=_mode_hops < 4,
            _mode_hops=_mode_hops + 1,
            _fallback_kwargs=fallback_kwargs,
        )

    budget_guardrail = _budget_guardrail_message(config, cumulative_stats)
    errors = list(cumulative_stats.errors)
    if budget_guardrail is not None:
        errors.append(budget_guardrail)

    if watch and not errors:
        from ctx.watcher import run_watch

        run_watch(root, config, client, spec)

    if cumulative_stats.cache_hits or cumulative_stats.cache_misses:
        cache_hits, cache_misses = cumulative_stats.cache_hits, cumulative_stats.cache_misses
    elif hasattr(client, "hit_miss_counts"):
        cache_hits, cache_misses = client.hit_miss_counts
    else:
        cache_hits, cache_misses = 0, 0
    tokens_saved = cumulative_stats.tokens_saved or int(getattr(client, "tokens_saved", 0) or 0)
    input_tokens_saved = cumulative_stats.input_tokens_saved or int(
        getattr(client, "input_tokens_saved", 0) or 0
    )
    output_tokens_saved = cumulative_stats.output_tokens_saved or int(
        getattr(client, "output_tokens_saved", 0) or 0
    )

    result = RefreshResult(
        dirs_processed=cumulative_stats.dirs_processed,
        dirs_skipped=cumulative_stats.dirs_skipped,
        files_processed=cumulative_stats.files_processed,
        tokens_used=cumulative_stats.tokens_used,
        errors=errors,
        budget_exhausted=cumulative_stats.budget_exhausted or budget_guardrail is not None,
        strategy=strategy,
        est_cost_usd=_estimate_usage_cost(
            cumulative_stats.tokens_used,
            cumulative_stats.input_tokens,
            cumulative_stats.output_tokens,
            config.provider,
            config.resolved_model(),
        ),
        stale_directories=[],
        budget_guardrail=budget_guardrail,
        config_written=config_written,
        setup_provider=setup_provider,
        setup_model=setup_model,
        setup_detected_via=setup_detected_via,
        local_batch_fallbacks=max(
            cumulative_stats.local_batch_fallbacks,
            int(getattr(client, "local_batch_fallbacks", 0) or 0),
        ),
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        tokens_saved=tokens_saved,
        input_tokens=cumulative_stats.input_tokens,
        output_tokens=cumulative_stats.output_tokens,
        input_tokens_saved=input_tokens_saved,
        output_tokens_saved=output_tokens_saved,
        tokens_saved_exact=cumulative_stats.tokens_saved_exact or hasattr(client, "tokens_saved"),
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

    tier2_root = _resolve_tier2_root(root)
    if tier2_root is not None:
        return _check_tier2(
            tier2_root,
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
    _force_tier1: bool = False,
) -> ExportResult:
    """Export manifests with filter/depth controls."""
    tier2_root = None if _force_tier1 else _resolve_tier2_root(root)
    if tier2_root is not None:
        from ctx.sdk import CtxProject

        if depth == 0:
            target_name = "CONTEXT-0.md"
        elif depth == 1:
            target_name = "CONTEXT-1.md"
        else:
            target_name = "CONTEXT.md"
        target_file = tier2_root / ".ctx" / target_name
        label = f".ctx/{target_name}"
        proj = CtxProject.load(tier2_root, walk_parents=False)
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
    from ctx.config import resolve_project_anchor

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
        if manifests:
            for manifest in manifests:
                fenced_unlink(manifest, missing_ok=True)
            _sync_tier1_ctx_exports(root)

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
) -> FleetCapsuleResult:
    """Generate a compact deterministic capsule for project-ledger and gbrain ingestion."""
    import hashlib
    import json
    from dataclasses import asdict, replace
    from ctx.impact import build_dependency_graph
    from ctx.skeleton import (
        extract_skeleton,
        render_context_0,
        render_context_1,
        strip_tier2_chrome,
    )

    resolved_root = root.resolve()
    skeleton = extract_skeleton(resolved_root)
    try:
        dep_graph = build_dependency_graph(resolved_root, skeleton=skeleton)
    except Exception:
        dep_graph = None
    repo_id = f"sha256:{hashlib.sha256(str(resolved_root).encode('utf-8')).hexdigest()}"

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
            # Treat src/<pkg> as depth 1 logical subsystem for capsule ingestion
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


def jev_list_heads(root: Path | None = None) -> list[dict[str, object]]:
    """Return validated Jev System-One decision head specifications."""
    from ctx.jev import list_heads_safe

    heads, _warnings = list_heads_safe(root)
    return heads


def jev_list_heads_with_warnings(
    root: Path | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    """Return validated Jev heads plus warnings for any malformed custom head files."""
    from ctx.jev import list_heads_safe

    return list_heads_safe(root)


def jev_decide(
    head_ids: list[str],
    state: dict[str, object],
    *,
    root: Path | None = None,
    provider: str | None = None,
    allow_vault: bool = False,
    record_trace: bool = True,
) -> dict[str, object]:
    """Run one or more governed Type 1 Jev heads on *state*."""
    from ctx.jev import decide as _decide

    return _decide(
        head_ids,
        state,
        root=root,
        provider=provider,
        allow_vault=allow_vault,
        record_trace=record_trace,
    )


def evaluate_jev_heads(
    root: Path | None = None,
    *,
    provider: str = "code",
    head_ids: list[str] | None = None,
    allow_vault: bool = False,
    skip_pre_rule_for_jev: bool = False,
) -> dict[str, object]:
    """Evaluate governed Type 1 Jev heads against the gold evaluation corpus."""
    from ctx.jev import evaluate_heads as _evaluate_heads

    return _evaluate_heads(
        root,
        provider=provider,
        head_ids=head_ids,
        allow_vault=allow_vault,
        skip_pre_rule_for_jev=skip_pre_rule_for_jev,
    )


def run_benchmark(
    paths: list[Path],
    *,
    output_file: str | None = None,
) -> dict[str, object]:
    """Run the Phase 27.1 A/B/C agent navigation benchmark across *paths*."""
    import json
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

