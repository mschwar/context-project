"""Click CLI entry point for ctx.

Commands:
    ctx init <path>     Generate CONTEXT.md files for a directory tree.
    ctx update <path>   Incrementally refresh stale CONTEXT.md files.
    ctx status [path]   Show manifest health across a directory tree.
    ctx diff [path]     Show which CONTEXT.md files changed since last generation.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import click

from ctx import api
from ctx import __version__
from ctx.config import (
    DEFAULT_BASE_URLS,
    LOCAL_PROVIDERS,
    PROVIDER_DETECTED_VIA,
    PROXY_ENV_VARS,
    MissingApiKeyError,
    detect_provider,
    load_config,
    probe_provider_connectivity,
    write_default_config,
)
from ctx.llm import TRANSIENT_ERROR_PREFIX
from ctx.generator import (
    GenerateStats,
    check_stale_dirs,
    generate_tree,
    inspect_directory_health,
    update_tree,
)
from ctx.ignore import load_ignore_patterns
from ctx.llm import create_client
from ctx.lock import CtxLock
from ctx.output import OutputBroker, _classify_exception, build_envelope


@dataclass
class ProgressState:
    """Mutable state for progress tracking across callbacks."""

    start_time: float
    tokens_accumulated: int = 0

    def elapsed(self) -> float:
        return time.time() - self.start_time


def _format_elapsed(seconds: float) -> str:
    """Format elapsed time in seconds to a readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


# Pricing per 1M tokens in USD.
_PRICING_DATA: dict[str, dict] = {
    "anthropic": {
        "models": [
            ("claude-3-opus", 15.0),
            ("claude-3-sonnet", 3.0),
            ("claude-3-haiku", 0.25),
        ],
        "default": 3.0,  # Sonnet pricing
    },
    "openai": {
        "models": [
            ("gpt-4o", 5.0),
            ("gpt-4-o", 5.0),
            ("gpt-4", 30.0),
            ("gpt-3.5-turbo", 0.5),
            ("gpt-3.5", 0.5),
        ],
        "default": 5.0,  # GPT-4o pricing
    },
    "ollama": {"default": 0.0},
    "lmstudio": {"default": 0.0},
}
_DEFAULT_UNKNOWN_PROVIDER_PRICE = 3.0  # Default for unknown providers


def _estimate_cost(tokens: int, provider: str, model: str) -> float:
    """Estimate cost in USD based on tokens used and provider pricing.

    Pricing is per 1M tokens (input + output averaged/estimated).
    These are approximate prices as of early 2025.
    """
    provider_lower = provider.lower()
    model_lower = model.lower()

    provider_pricing = _PRICING_DATA.get(provider_lower)
    if not provider_pricing:
        return tokens * _DEFAULT_UNKNOWN_PROVIDER_PRICE / 1_000_000

    # Local providers have a default of 0.0 and no specific models
    if "models" not in provider_pricing:
        return tokens * provider_pricing["default"] / 1_000_000

    for model_key, price_per_million in provider_pricing["models"]:
        if model_key in model_lower:
            return tokens * price_per_million / 1_000_000

    return tokens * provider_pricing["default"] / 1_000_000


def _echo_cost_summary(stats: GenerateStats, provider: str, model: str) -> None:
    """Print estimated cost summary after generation."""
    if stats.tokens_used == 0:
        return

    cost = _estimate_cost(stats.tokens_used, provider, model)
    if cost == 0.0:
        click.echo("Estimated cost: $0.00 (local provider)")
    elif cost < 0.01:
        click.echo(f"Estimated cost: ${cost:.4f} ({stats.tokens_used:,} tokens)")
    else:
        click.echo(f"Estimated cost: ${cost:.2f} ({stats.tokens_used:,} tokens)")


def _build_generation_runtime(
    path: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_depth: Optional[int] = None,
    token_budget: Optional[int] = None,
    base_url: Optional[str] = None,
    cache_path: Optional[str] = None,
    progress_state: Optional[ProgressState] = None,
    json_mode: bool = False,
) -> tuple[Path, object, object, object, Callable[[Path, int, int, int], None]]:
    target_path = Path(path)
    load_config_kwargs: dict[str, Optional[str] | int] = {
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

    try:
        config = load_config(target_path, **load_config_kwargs)
    except MissingApiKeyError:
        raise click.UsageError(
            "ctx needs an LLM provider to generate summaries.\n"
            "  Run `ctx setup` to auto-detect your environment and create a .ctxconfig file.\n"
            "  Or set ANTHROPIC_API_KEY / OPENAI_API_KEY in your environment."
        ) from None

    # Pre-flight connectivity check for cloud providers
    if config.provider not in LOCAL_PROVIDERS:
        ok, conn_error = probe_provider_connectivity(
            config.provider, config.api_key, config.base_url,
        )
        if not ok:
            _echo_connectivity_failure(conn_error or "unknown error")
            sys.exit(1)

    spec = load_ignore_patterns(target_path)
    client = create_client(config)
    state = progress_state if progress_state is not None else ProgressState(start_time=time.time())
    progress_cb = _progress_callback(state, json_mode=json_mode)
    return target_path, config, spec, client, progress_cb


def _progress_callback(
    state: ProgressState,
    *,
    json_mode: bool = False,
) -> Callable[[Path, int, int, int], None]:
    """Create a progress callback that shows elapsed time and running token total.

    Args:
        state: Mutable progress state shared across callbacks.

    Returns:
        Callback function for progress reporting.
    """

    def callback(current_dir: Path, done: int, total: int, tokens_used: int) -> None:
        state.tokens_accumulated = tokens_used
        if json_mode:
            return
        elapsed = state.elapsed()
        elapsed_str = _format_elapsed(elapsed)
        tokens_str = f"{tokens_used:,} tokens"
        click.echo(
            f"  [{done}/{total}] Processing {current_dir.name or current_dir} — {tokens_str}, {elapsed_str}"
        )

    return callback


def _active_proxy_vars() -> list[str]:
    """Return names of proxy-related env vars that are currently set."""
    return [v for v in PROXY_ENV_VARS if os.getenv(v)]


def _proxy_unset_hint(proxy_vars: list[str], *, platform_name: Optional[str] = None) -> str:
    """Return a shell-appropriate hint for unsetting proxy environment variables."""
    platform = platform_name or os.name
    if platform == "nt":
        commands = "; ".join(
            f"Remove-Item Env:{proxy_var} -ErrorAction SilentlyContinue"
            for proxy_var in proxy_vars
        )
        return f"PowerShell: {commands}"
    return "unset " + " ".join(proxy_vars)


def _echo_proxy_guidance(proxy_vars: list[str]) -> None:
    """Print shell-aware proxy guidance when active proxy variables are detected."""
    if not proxy_vars:
        return
    click.echo(
        f"Proxy env vars detected: {', '.join(proxy_vars)}. "
        "A broken proxy may be blocking requests. "
        f"Try unsetting them in your shell: {_proxy_unset_hint(proxy_vars)}",
        err=True,
    )


def _echo_connectivity_failure(error: str) -> None:
    """Print a connectivity failure message with optional proxy guidance."""
    click.echo(f"Pre-flight check failed: {error}", err=True)
    proxy_vars = _active_proxy_vars()
    _echo_proxy_guidance(proxy_vars)
    click.echo("Tip: run `ctx setup --check` for detailed provider diagnostics.", err=True)


def _echo_generation_errors(stats: GenerateStats) -> None:
    if not stats.errors:
        return

    click.echo("Errors:")
    for error in stats.errors:
        click.echo(f"  - {error}")
    if any(TRANSIENT_ERROR_PREFIX in e for e in stats.errors):
        click.echo(
            "Tip: transient errors may resolve on retry. Run the command again.",
            err=True,
        )
        _echo_proxy_guidance(_active_proxy_vars())


def _echo_stale_dirs(stale: list[Path], target_path: Path) -> None:
    """Print the list of stale directories for --dry-run output."""
    click.echo(f"{len(stale)} director{'y' if len(stale) == 1 else 'ies'} would be regenerated:")
    for directory in stale:
        try:
            rel = directory.relative_to(target_path).as_posix()
        except ValueError:
            rel = directory.as_posix()
        click.echo(f"  {rel or '.'}")


def _echo_budget_warning(stats: GenerateStats, config: object) -> None:
    if not stats.budget_exhausted:
        return
    budget = getattr(config, "token_budget", None)
    click.echo(
        f"Warning: token budget ({budget:,}) reached after {stats.tokens_used:,} tokens. "
        f"{stats.dirs_skipped} director{'y' if stats.dirs_skipped == 1 else 'ies'} skipped.",
        err=True,
    )


def _display_status_path(path: str) -> str:
    return "." if path == "." else f"./{path}"


def _json_mode(ctx: click.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("json_mode"))


def _exit_for_broker(broker: OutputBroker, *, json_mode: bool) -> None:
    if not json_mode:
        return
    if broker.handled_exception:
        sys.exit(1)
    if broker.errors and broker.data:
        sys.exit(2)
    if broker.errors:
        sys.exit(1)


class CtxGroup(click.Group):
    """Click group with JSON-safe global exception handling."""

    def invoke(self, ctx: click.Context) -> None:
        started = time.time()
        try:
            super().invoke(ctx)
        except Exception as exc:
            if _json_mode(ctx):
                code, message, hint = _classify_exception(exc)
                envelope = build_envelope(
                    command=ctx.invoked_subcommand or "unknown",
                    elapsed_ms=int((time.time() - started) * 1000),
                    data={},
                    errors=[{"code": code, "message": message, "hint": hint, "path": None}],
                    status="error",
                )
                click.echo(json.dumps(envelope))
                ctx.exit(1)
            raise


@click.group(cls=CtxGroup)
@click.version_option(version=__version__, prog_name="ctx")
@click.option(
    "--output",
    "output_mode",
    type=click.Choice(["human", "json"]),
    default=None,
    help="Output format. Default: human.",
)
@click.pass_context
def cli(ctx: click.Context, output_mode: str | None) -> None:
    """ctx — Filesystem-native context layer for AI agents."""
    ctx.ensure_object(dict)
    resolved_output_mode = output_mode
    if resolved_output_mode is None:
        resolved_output_mode = os.environ.get("CTX_OUTPUT", "human").strip().lower()
    ctx.obj["json_mode"] = resolved_output_mode == "json"


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--force", is_flag=True, help="Regenerate all manifests, even fresh ones.")
@click.option("--setup", "do_setup", is_flag=True, help="Auto-detect provider and write .ctxconfig first.")
@click.option("--watch", "do_watch", is_flag=True, help="After refresh, watch for changes and re-refresh.")
@click.option("--dry-run", is_flag=True, help="Preview what would be regenerated.")
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--max-depth", type=int, default=None)
@click.option("--token-budget", type=int, default=None)
@click.option("--base-url", default=None)
@click.option("--cache-path", default=None)
@click.pass_context
def refresh(
    ctx: click.Context,
    path: str,
    force: bool,
    do_setup: bool,
    do_watch: bool,
    dry_run: bool,
    provider: Optional[str],
    model: Optional[str],
    max_depth: Optional[int],
    token_budget: Optional[int],
    base_url: Optional[str],
    cache_path: Optional[str],
) -> None:
    """Generate or update CONTEXT.md manifests."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        state = ProgressState(start_time=time.time())
        result = api.refresh(
            Path(path),
            force=force,
            setup=do_setup,
            watch=do_watch,
            dry_run=dry_run,
            provider=provider,
            model=model,
            max_depth=max_depth,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
            progress=_progress_callback(state, json_mode=json_mode),
        )
        broker.set_data(asdict(result))
        broker.set_tokens(result.tokens_used, result.est_cost_usd)
        if result.errors:
            for error in result.errors:
                broker.add_error("partial_failure", error)

        if not json_mode:
            if result.setup_provider:
                click.echo(f"Detected: {result.setup_provider} ({result.setup_detected_via or result.setup_provider})")
                if do_setup and not dry_run:
                    click.echo(f"Config written to {Path(path) / '.ctxconfig'}")
            if dry_run:
                if not result.stale_directories:
                    click.echo("All manifests are fresh. Nothing to regenerate.")
                else:
                    click.echo(f"{len(result.stale_directories)} director{'y' if len(result.stale_directories) == 1 else 'ies'} would be regenerated:")
                    for directory in result.stale_directories:
                        click.echo(f"  {directory}")
                return
            click.echo(f"Directories refreshed: {result.dirs_processed}")
            click.echo(f"Directories skipped: {result.dirs_skipped}")
            click.echo(f"Files processed: {result.files_processed}")
            click.echo(f"Tokens used: {result.tokens_used}")
            if result.est_cost_usd == 0.0 and result.tokens_used > 0:
                click.echo("Estimated cost: $0.00 (local provider)")
            elif result.tokens_used > 0:
                click.echo(f"Estimated cost: ${result.est_cost_usd:.2f} ({result.tokens_used:,} tokens)")
            click.echo(f"Errors: {len(result.errors)}")
            if result.errors:
                sys.exit(1)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None, help="LLM provider.")
@click.option("--model", default=None, help="Model ID override.")
@click.option("--max-depth", type=int, default=None, help="Max directory depth to process.")
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
@click.option("--cache-path", default=None, help="Disk cache file path. Set to '' to disable.")
@click.option("--overwrite/--no-overwrite", default=True, help="Regenerate all manifests (default) or skip already-fresh ones.")
@click.pass_context
def init(ctx: click.Context, path: str, provider: Optional[str], model: Optional[str], max_depth: Optional[int], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str], overwrite: bool) -> None:
    """Generate CONTEXT.md files for a directory tree."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        progress_state = ProgressState(start_time=time.time())
        target_path, config, spec, client, progress_cb = _build_generation_runtime(
            path,
            provider=provider,
            model=model,
            max_depth=max_depth,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
            progress_state=progress_state,
            json_mode=json_mode,
        )

        click.echo(f"ctx init: generating manifests for {target_path}")
        if not overwrite:
            click.echo("Mode: incremental (skipping fresh manifests)")
        if config.token_budget:
            click.echo(f"Token budget: {config.token_budget:,}")
        with CtxLock(target_path, command="refresh"):
            if overwrite:
                stats = generate_tree(target_path, config, client, spec, progress=progress_cb)
            else:
                stats = update_tree(target_path, config, client, spec, progress=progress_cb)
        click.echo(f"Directories processed: {stats.dirs_processed}")
        click.echo(f"Files processed: {stats.files_processed}")
        click.echo(f"Tokens used: {stats.tokens_used}")
        _echo_cost_summary(stats, config.provider, config.resolved_model())
        click.echo(f"Errors: {len(stats.errors)}")
        _echo_generation_errors(stats)
        _echo_budget_warning(stats, config)

        cost = _estimate_cost(stats.tokens_used, config.provider, config.resolved_model())
        broker.set_data(
            {
                "dirs_processed": stats.dirs_processed,
                "dirs_skipped": stats.dirs_skipped,
                "files_processed": stats.files_processed,
                "tokens_used": stats.tokens_used,
                "errors_count": len(stats.errors),
                "budget_exhausted": stats.budget_exhausted,
                "strategy": "full" if overwrite else "incremental",
            }
        )
        broker.set_tokens(stats.tokens_used, cost)
        if stats.errors:
            for error in stats.errors:
                broker.add_error("partial_failure", error)
            if not json_mode:
                sys.exit(1)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
@click.option("--cache-path", default=None, help="Disk cache file path. Set to '' to disable.")
@click.option("--dry-run", is_flag=True, help="List stale directories without regenerating.")
@click.pass_context
def update(ctx: click.Context, path: str, provider: Optional[str], model: Optional[str], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str], dry_run: bool) -> None:
    """Incrementally refresh stale CONTEXT.md files."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        target_path = Path(path)
        spec = load_ignore_patterns(target_path)

        if dry_run:
            config = load_config(target_path, provider=provider, model=model, token_budget=token_budget, base_url=base_url, cache_path=cache_path, require_api_key=False)
            stale = check_stale_dirs(target_path, config, spec)
            if not stale:
                click.echo("All manifests are fresh. Nothing to regenerate.")
                broker.set_data(
                    {
                        "dirs_processed": 0,
                        "dirs_skipped": 0,
                        "files_processed": 0,
                        "tokens_used": 0,
                        "errors_count": 0,
                        "budget_exhausted": False,
                        "strategy": "incremental",
                    }
                )
                return
            _echo_stale_dirs(stale, target_path)
            broker.set_data(
                {
                    "dirs_processed": 0,
                    "dirs_skipped": len(stale),
                    "files_processed": 0,
                    "tokens_used": 0,
                    "errors_count": 0,
                    "budget_exhausted": False,
                    "strategy": "incremental",
                }
            )
            return

        progress_state = ProgressState(start_time=time.time())
        target_path, config, spec, client, progress_cb = _build_generation_runtime(
            path,
            provider=provider,
            model=model,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
            progress_state=progress_state,
            json_mode=json_mode,
        )

        click.echo(f"ctx update: refreshing manifests for {target_path}")
        if config.token_budget:
            click.echo(f"Token budget: {config.token_budget:,}")
        with CtxLock(target_path, command="refresh"):
            stats = update_tree(target_path, config, client, spec, progress=progress_cb)
        click.echo(f"Directories refreshed: {stats.dirs_processed}")
        click.echo(f"Directories skipped: {stats.dirs_skipped}")
        click.echo(f"Tokens used: {stats.tokens_used}")
        _echo_cost_summary(stats, config.provider, config.resolved_model())
        click.echo(f"Errors: {len(stats.errors)}")
        _echo_generation_errors(stats)
        _echo_budget_warning(stats, config)

        cost = _estimate_cost(stats.tokens_used, config.provider, config.resolved_model())
        broker.set_data(
            {
                "dirs_processed": stats.dirs_processed,
                "dirs_skipped": stats.dirs_skipped,
                "files_processed": stats.files_processed,
                "tokens_used": stats.tokens_used,
                "errors_count": len(stats.errors),
                "budget_exhausted": stats.budget_exhausted,
                "strategy": "incremental",
            }
        )
        broker.set_tokens(stats.tokens_used, cost)
        if stats.errors:
            for error in stats.errors:
                broker.add_error("partial_failure", error)
            if not json_mode:
                sys.exit(1)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--check-exit-code", is_flag=True, help="Exit with code 1 if any manifests are stale or missing.")
@click.pass_context
def status(ctx: click.Context, path: str, check_exit_code: bool) -> None:
    """Show manifest health across a directory tree.

    Implementation:
        1. load_ignore_patterns(Path(path)).
        2. results = inspect_directory_health(Path(path), spec, Path(path)).
        3. Print a table:
           STATUS   PATH
           fresh    ./src
           stale    ./src/routes
           missing  ./tests
        4. Print summary counts: N fresh, N stale, N missing.
        5. If check_exit_code is True and stale or missing > 0, sys.exit(1).
    """
    json_mode = _json_mode(ctx)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        target_path = Path(path)
        spec = load_ignore_patterns(target_path)
        results = inspect_directory_health(target_path, spec, target_path)

        click.echo("STATUS   PATH")
        for result in results:
            click.echo(f"{result.status:<8} {_display_status_path(result.relative_path)}")

        counts = Counter(result.status for result in results)
        click.echo(
            f"{counts.get('fresh', 0)} fresh, {counts.get('stale', 0)} stale, "
            f"{counts.get('missing', 0)} missing"
        )
        broker.set_data(
            {
                "mode": "health",
                "directories": [
                    {"path": entry.relative_path, "status": entry.status}
                    for entry in results
                ],
                "summary": {
                    "total": len(results),
                    "fresh": counts.get("fresh", 0),
                    "stale": counts.get("stale", 0),
                    "missing": counts.get("missing", 0),
                },
            }
        )

        has_issues = counts.get("stale", 0) > 0 or counts.get("missing", 0) > 0
        if check_exit_code and has_issues:
            if json_mode:
                if counts.get("stale", 0) > 0:
                    broker.add_error("stale_manifests", "Stale manifests detected.")
                if counts.get("missing", 0) > 0:
                    broker.add_error("no_manifests", "Missing manifests detected.")
            else:
                sys.exit(1)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(name="check")
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--verify", "verify_mode", is_flag=True)
@click.option("--stats", "stats_mode", is_flag=True)
@click.option("--diff", "diff_mode", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
@click.option("--since", default=None)
@click.option("--quiet", is_flag=True)
@click.option("--stat", is_flag=True)
@click.option("--check-exit", is_flag=True)
@click.pass_context
def check(
    ctx: click.Context,
    path: str,
    verify_mode: bool,
    stats_mode: bool,
    diff_mode: bool,
    verbose: bool,
    since: str | None,
    quiet: bool,
    stat: bool,
    check_exit: bool,
) -> None:
    """Check manifest health, coverage, validation, or diffs."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        result = api.check(
            Path(path),
            verify=verify_mode,
            stats=stats_mode,
            diff=diff_mode,
            verbose=verbose,
            since=since,
            check_exit=check_exit,
            quiet=quiet,
            stat=stat,
        )
        broker.set_data({"mode": result.mode, "directories": result.directories, "summary": result.summary})

        if json_mode:
            summary = result.summary
            if result.mode == "health" and check_exit and (summary.get("stale", 0) > 0 or summary.get("missing", 0) > 0):
                broker.add_error("stale_manifests", "Stale or missing manifests detected.")
            if result.mode == "verify" and summary.get("invalid", 0) > 0:
                broker.add_error("invalid_manifests", "Manifest verification found invalid entries.")
            if result.mode == "diff":
                changed_count = summary.get("modified", 0) + summary.get("new", 0) + summary.get("stale", 0)
                if quiet and changed_count > 0:
                    broker.add_error("stale_manifests", "Manifest changes detected.")
            return

        if result.mode == "health":
            click.echo("STATUS   PATH")
            for entry in result.directories:
                click.echo(f"{entry['status']:<8} {_display_status_path(str(entry['path']))}")
            summary = result.summary
            click.echo(f"{summary['fresh']} fresh, {summary['stale']} stale, {summary['missing']} missing")
            if check_exit and (summary["stale"] > 0 or summary["missing"] > 0):
                sys.exit(1)
            return

        if result.mode == "stats":
            summary = result.summary
            click.echo(f"dirs:    {summary['dirs']}")
            click.echo(f"covered: {summary['covered']}")
            click.echo(f"missing: {summary['missing']}")
            click.echo(f"stale:   {summary['stale']}")
            click.echo(f"tokens:  {summary['tokens']}")
            if verbose and result.directories:
                click.echo("")
                click.echo(f"{'Directory':<32} {'status':<9} {'tokens'}")
                click.echo(f"{'-'*32} {'-'*9} {'-'*6}")
                for row in result.directories:
                    token_str = str(row.get("tokens")) if row.get("tokens") is not None else "-"
                    click.echo(f"{str(row['path']):<32} {str(row['status']):<9} {token_str}")
            return

        if result.mode == "diff":
            modified = sorted(entry["path"] for entry in result.directories if entry["status"] == "modified")
            new_files = sorted(entry["path"] for entry in result.directories if entry["status"] == "new")
            stale = sorted(entry["path"] for entry in result.directories if entry["status"] == "stale")
            changed = sorted(set(modified) | set(new_files))
            if quiet:
                if changed or stale:
                    sys.exit(1)
                return
            if stat:
                if stale:
                    click.echo(f"{len(stale)} stale")
                else:
                    parts = []
                    if modified:
                        parts.append(f"{len(modified)} modified")
                    if new_files:
                        parts.append(f"{len(new_files)} new")
                    click.echo(", ".join(parts) if parts else "No CONTEXT.md files changed.")
                return
            if stale:
                click.echo(f"{len(stale)} CONTEXT.md file{'s' if len(stale) != 1 else ''} may be stale (mtime check):")
                for file_path in stale:
                    click.echo(f"  [stale] {file_path}")
            else:
                if not changed:
                    click.echo("No CONTEXT.md files changed.")
                else:
                    click.echo(f"{len(changed)} CONTEXT.md file{'s' if len(changed) != 1 else ''} changed:")
                    for file_path in changed:
                        label = "new" if file_path in new_files else "mod"
                        click.echo(f"  [{label}] {file_path}")
            return

        invalid_entries = [entry for entry in result.directories if entry["status"] != "fresh"]
        malformed = [entry["path"] for entry in invalid_entries if entry["status"] == "malformed"]
        missing = [entry["path"] for entry in invalid_entries if entry["status"] == "missing"]
        stale = [entry["path"] for entry in invalid_entries if entry["status"] == "stale"]
        missing_fields = [entry for entry in invalid_entries if entry["status"] == "missing_fields"]
        if malformed:
            click.echo("Malformed frontmatter:")
            for rel in malformed:
                click.echo(f"  {rel}")
        if missing_fields:
            click.echo("Missing required fields:")
            for item in missing_fields:
                click.echo(f"  {item['path']}: {', '.join(item['fields'])}")
        if stale:
            click.echo("Stale manifests:")
            for rel in stale:
                click.echo(f"  {rel}")
        if missing:
            click.echo("Missing manifests:")
            for rel in missing:
                click.echo(f"  {rel}")
        if invalid_entries:
            summary = result.summary
            click.echo(f"\nHealth summary: {summary['fresh']} fresh, {summary['stale']} stale, {summary['missing']} missing.")
            click.echo(f"Found {summary['invalid']} directory issue(s).")
            sys.exit(1)
        click.echo("All manifests are valid, present, and fresh.")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
@click.option("--cache-path", default=None, help="Disk cache file path. Set to '' to disable.")
@click.option("--dry-run", is_flag=True, help="List affected directories without regenerating.")
@click.pass_context
def smart_update(ctx: click.Context, path: str, provider: Optional[str], model: Optional[str], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str], dry_run: bool) -> None:
    """Incrementally refresh stale CONTEXT.md files, focusing on git-changed files."""
    from ctx.git import get_changed_files

    json_mode = _json_mode(ctx)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        target_path = Path(path)
        spec = load_ignore_patterns(target_path)

        changed_files = get_changed_files(target_path)
        if not changed_files:
            click.echo("No git-changed files detected. Nothing to update.")
            broker.set_data(
                {
                    "dirs_processed": 0,
                    "dirs_skipped": 0,
                    "files_processed": 0,
                    "tokens_used": 0,
                    "errors_count": 0,
                    "budget_exhausted": False,
                    "strategy": "smart",
                }
            )
            return

        if dry_run:
            config = load_config(target_path, provider=provider, model=model, token_budget=token_budget, base_url=base_url, cache_path=cache_path, require_api_key=False)
            stale = check_stale_dirs(target_path, config, spec, changed_files=changed_files)
            click.echo(f"Detected {len(changed_files)} changed files.")
            if not stale:
                click.echo("All affected manifests are fresh. Nothing to regenerate.")
                broker.set_data(
                    {
                        "dirs_processed": 0,
                        "dirs_skipped": 0,
                        "files_processed": 0,
                        "tokens_used": 0,
                        "errors_count": 0,
                        "budget_exhausted": False,
                        "strategy": "smart",
                    }
                )
                return
            _echo_stale_dirs(stale, target_path)
            broker.set_data(
                {
                    "dirs_processed": 0,
                    "dirs_skipped": len(stale),
                    "files_processed": 0,
                    "tokens_used": 0,
                    "errors_count": 0,
                    "budget_exhausted": False,
                    "strategy": "smart",
                }
            )
            return

        progress_state = ProgressState(start_time=time.time())
        target_path, config, spec, client, progress_cb = _build_generation_runtime(
            path,
            provider=provider,
            model=model,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
            progress_state=progress_state,
            json_mode=json_mode,
        )

        click.echo(f"ctx smart-update: refreshing manifests for {target_path} based on git changes")
        click.echo(f"Detected {len(changed_files)} changed files. Processing affected directories.")
        if config.token_budget:
            click.echo(f"Token budget: {config.token_budget:,}")
        with CtxLock(target_path, command="refresh"):
            stats = update_tree(target_path, config, client, spec, progress=progress_cb, changed_files=changed_files)
        click.echo(f"Directories refreshed: {stats.dirs_processed}")
        click.echo(f"Directories skipped: {stats.dirs_skipped}")
        click.echo(f"Tokens used: {stats.tokens_used}")
        _echo_cost_summary(stats, config.provider, config.resolved_model())
        click.echo(f"Errors: {len(stats.errors)}")
        _echo_generation_errors(stats)
        _echo_budget_warning(stats, config)

        cost = _estimate_cost(stats.tokens_used, config.provider, config.resolved_model())
        broker.set_data(
            {
                "dirs_processed": stats.dirs_processed,
                "dirs_skipped": stats.dirs_skipped,
                "files_processed": stats.files_processed,
                "tokens_used": stats.tokens_used,
                "errors_count": len(stats.errors),
                "budget_exhausted": stats.budget_exhausted,
                "strategy": "smart",
            }
        )
        broker.set_tokens(stats.tokens_used, cost)
        if stats.errors:
            for error in stats.errors:
                broker.add_error("partial_failure", error)
            if not json_mode:
                sys.exit(1)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", default=".")
@click.option("--provider", default=None, help="LLM provider.")
@click.option("--model", default=None, help="Model name.")
@click.option("--base-url", default=None, help="Base URL for local providers.")
@click.option("--cache-path", default=None, help="Path to LLM disk cache file.")
@click.pass_context
def watch(ctx: click.Context, path: str, provider: Optional[str], model: Optional[str], base_url: Optional[str], cache_path: Optional[str]) -> None:
    """Watch a directory tree and regenerate manifests on file changes."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        from ctx.watcher import run_watch

        target_path, config, spec, client, _ = _build_generation_runtime(
            path,
            provider=provider,
            model=model,
            base_url=base_url,
            cache_path=cache_path,
            json_mode=json_mode,
        )
        broker.set_data({"watching": str(target_path)})
        run_watch(target_path, config, client, spec)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", default=".", required=False)
@click.option("--check", "check_only", is_flag=True, help="Print detected provider without writing config.")
@click.pass_context
def setup(ctx: click.Context, path: str, check_only: bool) -> None:
    """Auto-detect LLM provider and write .ctxconfig."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        target_path = Path(path)
        config_file = target_path / ".ctxconfig"

        def _probe_msg(provider: str) -> None:
            label = {"ollama": "Ollama", "lmstudio": "LM Studio"}.get(provider, provider)
            click.echo(f"Probing {label}...")

        if not check_only and config_file.exists():
            click.echo(f".ctxconfig already exists:\n\n{config_file.read_text(encoding='utf-8')}")
            if not click.confirm("Overwrite?", default=False):
                click.echo("Cancelled.")
                broker.set_data({"configured": False, "provider": None, "model": None})
                return

        result = detect_provider(_probe_callback=_probe_msg)
        if result is None:
            raise click.UsageError(
                "No LLM provider detected.\n"
                "  Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or start Ollama / LM Studio first."
            )

        provider_name, model_name = result
        detected_via = PROVIDER_DETECTED_VIA.get(provider_name, provider_name)
        click.echo(f"Detected: {provider_name} ({detected_via})")

        if check_only:
            ok = True
            conn_error = None
            if provider_name in ("anthropic", "openai"):
                api_key_env = "ANTHROPIC_API_KEY" if provider_name == "anthropic" else "OPENAI_API_KEY"
                api_key = os.getenv(api_key_env, "")
                ok, conn_error = probe_provider_connectivity(provider_name, api_key)
                if ok:
                    click.echo("Connectivity: OK")
                else:
                    click.echo(f"Connectivity: FAILED — {conn_error}", err=True)
                    _echo_proxy_guidance(_active_proxy_vars())
                    if not json_mode:
                        sys.exit(1)
                    broker.add_error("provider_unreachable", str(conn_error), hint="Run ctx setup --check")
            broker.set_data({"configured": False, "provider": provider_name, "model": model_name, "check_only": True, "connectivity_ok": ok})
            return

        base_url_value = DEFAULT_BASE_URLS.get(provider_name)
        write_default_config(target_path, provider_name, model=model_name, base_url=base_url_value)
        click.echo(f"Config written to {config_file}")
        click.echo("\nNext step: run `ctx init .` to generate manifests.")
        broker.set_data({"configured": True, "provider": provider_name, "model": model_name})
        broker.set_recommended_next("ctx init .")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--since", default=None, help="Git ref (branch, commit, tag) to diff against. Defaults to HEAD.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format.")
@click.option("--quiet", is_flag=True, help="Exit code only: exit 1 if changes, exit 0 if clean. No stdout.")
@click.option("--stat", is_flag=True, help="Print summary count only, not file list.")
@click.pass_context
def diff(ctx: click.Context, path: str, since: Optional[str], output_format: str, quiet: bool, stat: bool) -> None:
    """Show CONTEXT.md files that changed since the last generation run.

    Uses git when available; falls back to mtime comparison when outside a
    git repository.

    Output labels:
      [mod]   — manifest modified (git path)
      [new]   — manifest untracked/new (git path)
      [stale] — manifest older than source files (mtime fallback path)
    """
    import subprocess

    from ctx.git import is_unborn_head_error

    json_mode = _json_mode(ctx)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        target_path = Path(path)
        ref = since or "HEAD"

        def _split_lines(stdout: str) -> list[str]:
            return [line.strip() for line in stdout.splitlines() if line.strip()]

        def _emit_git_results(modified_files: list[str], new_files_sorted: list[str], label: str) -> None:
            all_changed = sorted(set(modified_files) | set(new_files_sorted))
            data = {"mode": "diff", "modified": modified_files, "new": new_files_sorted, "stale": []}
            broker.set_data(data)

            if quiet:
                if all_changed and not json_mode:
                    sys.exit(1)
                if all_changed and json_mode:
                    broker.add_error("stale_manifests", "Manifest changes detected.")
                return

            if stat:
                mod_count = len(modified_files)
                new_count = len(new_files_sorted)
                parts = []
                if mod_count:
                    parts.append(f"{mod_count} modified")
                if new_count:
                    parts.append(f"{new_count} new")
                click.echo(", ".join(parts) if parts else f"No CONTEXT.md files changed {label}.")
                return

            if output_format == "json" and not json_mode:
                click.echo(json.dumps({"modified": modified_files, "new": new_files_sorted}))
                return

            if not all_changed:
                click.echo(f"No CONTEXT.md files changed {label}.")
                return
            click.echo(f"{len(all_changed)} CONTEXT.md file{'s' if len(all_changed) != 1 else ''} changed {label}:")
            for manifest_path in all_changed:
                prefix = "new" if manifest_path in set(new_files_sorted) else "mod"
                click.echo(f"  [{prefix}] {manifest_path}")

        def _fallback_to_mtime() -> None:
            if since is not None:
                raise click.UsageError("--since requires git to be available and the path to be inside a git repository.")
            click.echo("Warning: git not available or command failed. Falling back to mtime comparison.", err=True)

        # --- git path ---
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", ref, "--", "*/CONTEXT.md", "CONTEXT.md"],
                cwd=str(target_path),
                capture_output=True,
                text=True,
                check=True,
            )
            changed = _split_lines(result.stdout)
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "--", "*/CONTEXT.md", "CONTEXT.md"],
                cwd=str(target_path),
                capture_output=True,
                text=True,
                check=True,
            )
            new_files = _split_lines(untracked.stdout)
            new_files_set = set(new_files)
            modified_files = sorted(f for f in changed if f not in new_files_set)
            new_files_sorted = sorted(new_files_set)
            _emit_git_results(modified_files, new_files_sorted, f"since {ref}")
            return
        except subprocess.CalledProcessError as exc:
            if since is None and ref == "HEAD" and is_unborn_head_error(exc.stderr):
                staged = subprocess.run(
                    ["git", "diff", "--cached", "--name-only", "--", "*/CONTEXT.md", "CONTEXT.md"],
                    cwd=str(target_path),
                    capture_output=True,
                    text=True,
                    check=True,
                )
                untracked = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard", "--", "*/CONTEXT.md", "CONTEXT.md"],
                    cwd=str(target_path),
                    capture_output=True,
                    text=True,
                    check=True,
                )
                new_files_sorted = sorted(set(_split_lines(staged.stdout)) | set(_split_lines(untracked.stdout)))
                _emit_git_results([], new_files_sorted, "in repo without commits yet")
                return
            _fallback_to_mtime()
        except FileNotFoundError:
            _fallback_to_mtime()

        # --- mtime fallback (non-git repos) ---
        # Note: mtime path cannot distinguish modified vs new; all detected files use [stale].
        click.echo("Warning: git not available. Falling back to mtime comparison.", err=True)
        stale: list[str] = []
        for manifest in sorted(target_path.rglob("CONTEXT.md")):
            try:
                manifest_mtime = manifest.stat().st_mtime
                if any(
                    f.stat().st_mtime > manifest_mtime
                    for f in manifest.parent.iterdir()
                    if f.is_file() and f.name != "CONTEXT.md"
                ):
                    try:
                        rel = manifest.relative_to(target_path).as_posix()
                    except ValueError:
                        rel = manifest.as_posix()
                    stale.append(rel)
            except OSError:
                continue

        broker.set_data({"mode": "diff", "modified": [], "new": [], "stale": stale})
        if quiet:
            if stale and not json_mode:
                sys.exit(1)
            if stale and json_mode:
                broker.add_error("stale_manifests", "Stale manifests detected.")
            return

        if stat:
            click.echo(f"{len(stale)} stale" if stale else "No CONTEXT.md files appear stale (mtime check).")
            return

        if output_format == "json" and not json_mode:
            click.echo(json.dumps({"stale": stale}))
            return

        if not stale:
            click.echo("No CONTEXT.md files appear stale (mtime check).")
            return
        click.echo(f"{len(stale)} CONTEXT.md file{'s' if len(stale) != 1 else ''} may be stale (mtime check):")
        for f in stale:
            click.echo(f"  [stale] {f}")
    _exit_for_broker(broker, json_mode=json_mode)


def _directory_within_depth(path: Path, root: Path, depth: Optional[int]) -> bool:
    """Return True when a directory is within the requested export depth."""
    if depth is None:
        return True
    return len(path.relative_to(root).parts) <= depth


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output file path (default: stdout).")
@click.option(
    "--filter", "filter_mode",
    type=click.Choice(["all", "stale", "missing"]),
    default="all",
    help="Which manifests to export: all (default), stale, or missing.",
)
@click.option("--depth", type=int, default=None, help="Limit export to N levels of nesting (0 = root only).")
@click.pass_context
def export(ctx: click.Context, path: str, output: Optional[str], filter_mode: str, depth: Optional[int]) -> None:
    """Concatenate all CONTEXT.md files to stdout or a file.

    Each manifest is prefixed with a header line:
        # path/to/CONTEXT.md

    Respects .ctxignore patterns (same as ctx init/update).
    """
    json_mode = _json_mode(ctx)
    with OutputBroker(command="export", json_mode=json_mode) as broker:
        root = Path(path).resolve()
        spec = load_ignore_patterns(root)
        health_entries = [
            entry for entry in inspect_directory_health(root, spec, root)
            if _directory_within_depth(entry.path, root, depth)
        ]

        if filter_mode == "missing":
            missing_dirs = []
            for entry in health_entries:
                if entry.status != "missing":
                    continue
                rel_display = entry.relative_path if entry.relative_path != "." else ""
                missing_dirs.append((rel_display + "/") if rel_display else "./")
            content = "\n".join(f"# {d} [MISSING]" for d in missing_dirs)
            broker.set_data(
                {
                    "manifests_exported": len(missing_dirs),
                    "filter": filter_mode,
                    "depth": depth,
                    "content": content,
                }
            )
            if output:
                Path(output).write_text(content, encoding="utf-8")
                n = len(missing_dirs)
                click.echo(f"Exported {n} missing director{'y' if n == 1 else 'ies'} to {output}")
            elif content:
                click.echo(content, nl=False)
            return

        files = [
            entry.path / "CONTEXT.md"
            for entry in health_entries
            if entry.status != "missing" and (filter_mode != "stale" or entry.status == "stale")
        ]

        parts = []
        for f in files:
            try:
                rel = f.relative_to(root).as_posix()
            except ValueError:
                rel = f.as_posix()
            parts.append(f"# {rel}\n\n{f.read_text(encoding='utf-8')}")

        content = "\n\n".join(parts)
        broker.set_data(
            {
                "manifests_exported": len(files),
                "filter": filter_mode,
                "depth": depth,
                "content": content,
            }
        )

        if output:
            Path(output).write_text(content, encoding="utf-8")
            click.echo(f"Exported {len(files)} manifest{'s' if len(files) != 1 else ''} to {output}")
        else:
            click.echo(content, nl=False)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="Show per-directory breakdown table.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format.")
@click.pass_context
def stats(ctx: click.Context, path: str, verbose: bool, output_format: str) -> None:
    """Show coverage summary across all directories.

    Reports:
      dirs        — total directories found (respects .ctxignore)
      covered     — directories with a CONTEXT.md
      missing     — directories without a CONTEXT.md
      stale       — directories whose manifest hash no longer matches current contents
      tokens      — sum of tokens_total from all manifest frontmatters
    """
    json_mode = _json_mode(ctx)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        root = Path(path).resolve()
        spec = load_ignore_patterns(root)
        health_entries = inspect_directory_health(root, spec, root)

        dirs_total = len(health_entries)
        dirs_covered = sum(1 for entry in health_entries if entry.status != "missing")
        dirs_missing = sum(1 for entry in health_entries if entry.status == "missing")
        dirs_stale = sum(1 for entry in health_entries if entry.status == "stale")
        tokens_total = sum(entry.tokens_total or 0 for entry in health_entries)

        dir_rows: list[tuple[str, str, Optional[int]]] = []
        if verbose:
            dir_rows = [
                (
                    entry.relative_path,
                    "covered" if entry.status == "fresh" else entry.status,
                    entry.tokens_total,
                )
                for entry in health_entries
            ]
        data: dict[str, object] = {
            "mode": "stats",
            "aggregate": {
                "dirs": dirs_total,
                "covered": dirs_covered,
                "missing": dirs_missing,
                "stale": dirs_stale,
                "tokens": tokens_total,
            },
            "directories": [
                {"path": rel, "status": status, "tokens": tok}
                for rel, status, tok in dir_rows
            ] if verbose and dir_rows else [],
        }
        broker.set_data(data)

        def _render_json() -> None:
            """Render stats in JSON format."""
            output: dict[str, object] = {
                "aggregate": {
                    "dirs": dirs_total,
                    "covered": dirs_covered,
                    "missing": dirs_missing,
                    "stale": dirs_stale,
                    "tokens": tokens_total,
                },
            }
            if verbose and dir_rows:
                output["directories"] = [
                    {"path": rel, "status": status, "tokens": tok}
                    for rel, status, tok in dir_rows
                ]
            click.echo(json.dumps(output, indent=2))

        def _render_text() -> None:
            """Render stats in text format."""
            click.echo(f"dirs:    {dirs_total}")
            click.echo(f"covered: {dirs_covered}")
            click.echo(f"missing: {dirs_missing}")
            click.echo(f"stale:   {dirs_stale}")
            click.echo(f"tokens:  {tokens_total}")

            if verbose and dir_rows:
                click.echo("")
                click.echo(f"{'Directory':<32} {'status':<9} {'tokens'}")
                click.echo(f"{'-'*32} {'-'*9} {'-'*6}")
                for rel_path, status, tok in dir_rows:
                    tok_str = str(tok) if tok is not None else "-"
                    click.echo(f"{rel_path:<32} {status:<9} {tok_str}")

        if output_format == "json" and not json_mode:
            _render_json()
        else:
            _render_text()
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--dry-run", is_flag=True, help="List CONTEXT.md files that would be deleted without removing them.")
@click.pass_context
def reset(ctx: click.Context, path: str, yes: bool, dry_run: bool) -> None:
    """Remove all CONTEXT.md files from the directory tree."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="reset", json_mode=json_mode) as broker:
        root = Path(path).resolve()
        if json_mode and not yes and not dry_run:
            broker.add_error("confirmation_required", "--yes flag required in non-interactive mode", hint="Re-run with --yes.")
        else:
            if not yes and not dry_run and not json_mode:
                manifests = sorted(root.rglob("CONTEXT.md"))
                if manifests:
                    confirmed = click.confirm(
                        f"Found {len(manifests)} CONTEXT.md file(s). Delete all?", default=False
                    )
                    if not confirmed:
                        click.echo("Aborted.")
                        broker.set_data({"manifests_removed": 0, "paths": []})
                        return
                yes = True

            result = api.reset(root, dry_run=dry_run, yes=yes)
            broker.set_data(asdict(result))

            if not json_mode:
                if dry_run:
                    if not result.paths:
                        click.echo("No CONTEXT.md files found.")
                    else:
                        click.echo(f"{len(result.paths)} CONTEXT.md file(s) would be deleted:")
                        for path_item in result.paths:
                            click.echo(f"  {path_item}")
                else:
                    click.echo(f"Removed {result.manifests_removed} CONTEXT.md file(s).")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--dry-run", is_flag=True, help="List CONTEXT.md files that would be deleted without removing them.")
@click.pass_context
def clean(ctx: click.Context, path: str, yes: bool, dry_run: bool) -> None:
    """Remove all CONTEXT.md files from the directory tree."""
    json_mode = _json_mode(ctx)
    with OutputBroker(command="reset", json_mode=json_mode) as broker:
        root = Path(path).resolve()
        manifests = sorted(root.rglob("CONTEXT.md"))

        if not manifests:
            click.echo("No CONTEXT.md files found.")
            broker.set_data({"manifests_removed": 0, "paths": []})
            return

        rel_paths = [m.relative_to(root).as_posix() for m in manifests]
        if dry_run:
            click.echo(f"{len(manifests)} CONTEXT.md file(s) would be deleted:")
            for rel in rel_paths:
                click.echo(f"  {rel}")
            broker.set_data({"manifests_removed": 0, "paths": rel_paths})
            return

        if json_mode and not yes:
            broker.add_error("unknown_error", "--yes flag required in non-interactive mode",
                             hint="Use: ctx reset . --yes --output json")
            broker.set_data({"manifests_removed": 0, "paths": []})
            return
        if not yes:
            confirmed = click.confirm(
                f"Found {len(manifests)} CONTEXT.md file(s). Delete all?", default=False
            )
            if not confirmed:
                click.echo("Aborted.")
                broker.set_data({"manifests_removed": 0, "paths": []})
                return

        with CtxLock(root, command="reset"):
            for manifest_path in manifests:
                manifest_path.unlink()

        click.echo(f"Removed {len(manifests)} CONTEXT.md file(s).")
        broker.set_data({"manifests_removed": len(manifests), "paths": rel_paths})
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format.")
@click.pass_context
def verify(ctx: click.Context, path: str, output_format: str) -> None:
    """Check CONTEXT.md validity, freshness, and coverage.

    Required fields:
      - generated
      - generator
      - model
      - content_hash
      - files
      - dirs
      - tokens_total

    Output:
      - Malformed frontmatter reported separately from missing fields
      - Stale and missing directories are reported as verification failures
      - Exit 0 if all manifests are valid, fresh, and present; exit 1 otherwise
    """
    json_mode = _json_mode(ctx)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        root = Path(path).resolve()
        spec = load_ignore_patterns(root)
        health_entries = inspect_directory_health(root, spec, root)

        required_fields = [
            "generated",
            "generator",
            "model",
            "content_hash",
            "files",
            "dirs",
            "tokens_total",
        ]

        malformed_manifests = sorted(
            entry.relative_path for entry in health_entries
            if entry.error is not None
        )
        missing_manifests = sorted(
            entry.relative_path for entry in health_entries
            if entry.status == "missing"
        )
        invalid_manifests: list[tuple[str, list[str]]] = []

        for entry in health_entries:
            if entry.status == "missing" or entry.error is not None or entry.frontmatter is None:
                continue

            missing_fields = []
            for field in required_fields:
                value = getattr(entry.frontmatter, field, None)
                if value is None or value == "":
                    missing_fields.append(field)

            if missing_fields:
                invalid_manifests.append((entry.relative_path, missing_fields))

        invalid_field_paths = {rel for rel, _fields in invalid_manifests}
        stale_manifests = sorted(
            entry.relative_path for entry in health_entries
            if entry.status == "stale"
            and entry.error is None
            and entry.relative_path not in invalid_field_paths
        )

        invalid_paths = set(malformed_manifests) | invalid_field_paths | set(stale_manifests) | set(missing_manifests)
        aggregate = {
            "dirs": len(health_entries),
            "fresh": sum(1 for entry in health_entries if entry.status == "fresh"),
            "stale": sum(1 for entry in health_entries if entry.status == "stale"),
            "missing": len(missing_manifests),
            "invalid": len(invalid_paths),
        }
        output_payload = {
            "mode": "verify",
            "aggregate": aggregate,
            "malformed": malformed_manifests,
            "missing_fields": [
                {"path": rel, "fields": fields}
                for rel, fields in sorted(invalid_manifests)
            ],
            "stale": stale_manifests,
            "missing": missing_manifests,
        }
        broker.set_data(output_payload)

        if output_format == "json" and not json_mode:
            click.echo(json.dumps({
                "aggregate": aggregate,
                "malformed": malformed_manifests,
                "missing_fields": [
                    {"path": rel, "fields": fields}
                    for rel, fields in sorted(invalid_manifests)
                ],
                "stale": stale_manifests,
                "missing": missing_manifests,
            }, indent=2))
            sys.exit(1 if invalid_paths else 0)

        if malformed_manifests:
            click.echo("Malformed frontmatter:")
            for rel in malformed_manifests:
                click.echo(f"  {rel}")

        if invalid_manifests:
            click.echo("Missing required fields:")
            for rel, fields in sorted(invalid_manifests):
                field_list = ", ".join(fields)
                click.echo(f"  {rel}: {field_list}")

        if stale_manifests:
            click.echo("Stale manifests:")
            for rel in stale_manifests:
                click.echo(f"  {rel}")

        if missing_manifests:
            click.echo("Missing manifests:")
            for rel in missing_manifests:
                click.echo(f"  {rel}")

        if invalid_paths:
            click.echo(
                f"\nHealth summary: {aggregate['fresh']} fresh, {aggregate['stale']} stale, "
                f"{aggregate['missing']} missing."
            )
            click.echo(f"Found {len(invalid_paths)} directory issue(s).")
            if json_mode:
                broker.add_error("invalid_manifests", "Manifest verification found invalid entries.")
            else:
                sys.exit(1)
        elif not json_mode:
            click.echo("All manifests are valid, present, and fresh.")
            sys.exit(0)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--host", default="127.0.0.1", help="Host address for the server.")
@click.option("--port", type=int, default=8000, help="Port for the server.")
@click.pass_context
def serve(ctx: click.Context, path: str, host: str, port: int) -> None:
    """Start the MCP server to expose CONTEXT.md manifests.
    
    Serves manifests from the specified PATH (default: current directory).
    All manifest paths are resolved relative to this root.
    """
    from ctx.server import start_server

    root = Path(path).resolve()
    click.echo(f"Starting ctx MCP server on http://{host}:{port}")
    click.echo(f"Serving manifests from: {root}")
    start_server(host=host, port=port, root=root)

