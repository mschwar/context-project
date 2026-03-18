"""Unified API layer for ctx canonical commands."""

from __future__ import annotations

import os
import subprocess
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


def _has_manifests(root: Path) -> bool:
    return any(root.rglob("CONTEXT.md"))


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
        except RuntimeError:
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

    with CtxLock(root, command="refresh"):
        stats: GenerateStats
        if strategy == "full":
            stats = generate_tree(root, config, client, spec, progress=progress)
        elif strategy == "smart":
            stats = update_tree(root, config, client, spec, progress=progress, changed_files=changed_files)
        else:
            stats = update_tree(root, config, client, spec, progress=progress)

    budget_guardrail = _budget_guardrail_message(config, stats)
    errors = list(stats.errors)
    if budget_guardrail is not None:
        errors.append(budget_guardrail)

    if watch and not errors:
        run_watch(root, config, client, spec)

    return RefreshResult(
        dirs_processed=stats.dirs_processed,
        dirs_skipped=stats.dirs_skipped,
        files_processed=stats.files_processed,
        tokens_used=stats.tokens_used,
        errors=errors,
        budget_exhausted=stats.budget_exhausted or budget_guardrail is not None,
        strategy=strategy,
        est_cost_usd=estimate_cost(stats.tokens_used, config.provider, config.resolved_model()),
        stale_directories=[],
        budget_guardrail=budget_guardrail,
        config_written=config_written,
        setup_provider=setup_provider,
        setup_model=setup_model,
        setup_detected_via=setup_detected_via,
        local_batch_fallbacks=getattr(client, "local_batch_fallbacks", 0),
    )


def _path_relative(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return rel or "."


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
            for manifest in sorted(root.rglob("CONTEXT.md")):
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
    summary = {
        "total": len(health_entries),
        "fresh": counts.get("fresh", 0),
        "stale": counts.get("stale", 0),
        "missing": counts.get("missing", 0),
        "check_exit": check_exit,
    }
    return CheckResult(mode="health", directories=directories, summary=summary)


def export_context(
    root: Path,
    *,
    output_file: str | None = None,
    filter_mode: str = "all",
    depth: int | None = None,
) -> ExportResult:
    """Export manifests with filter/depth controls."""
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
    manifests = sorted(root.rglob("CONTEXT.md"))
    paths = [_path_relative(manifest, root) for manifest in manifests]

    if dry_run:
        return ResetResult(manifests_removed=0, paths=paths)

    if not yes:
        raise ConfirmationRequiredError("--yes flag required in non-interactive mode")

    with CtxLock(root, command="reset"):
        for manifest in manifests:
            manifest.unlink()

    return ResetResult(manifests_removed=len(manifests), paths=paths)
