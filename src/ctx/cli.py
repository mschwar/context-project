"""Click CLI entry point for ctx.

Commands:
    ctx init [path]       Bootstrap self-maintaining .ctx/ infrastructure.
    ctx uninit [path]     Remove .ctx/ infrastructure and git hooks.
    ctx refresh <path>    Generate or update CONTEXT.md manifests.
    ctx check <path>      Validate manifest health and coverage.
    ctx export <path>     Concatenate manifests for agent ingestion.
    ctx reset <path>      Remove generated manifests.
    ctx stats [path]      Show coverage summary or refresh history.
    ctx impact <target>   Analyze reverse-dependency blast radius and coupled tests.
    ctx jev <subcommand>  Run or evaluate governed Type 1 Jev System-One heads.
    ctx benchmark [paths] Run Phase 27.1 A/B/C agent navigation benchmark.
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
    estimate_cost as _estimate_cost,
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
    inspect_directory_health,
    validate_manifest_body,
    update_tree,
)
from ctx.ignore import load_ignore_patterns
from ctx.llm import create_client
from ctx.lock import CtxLock
from ctx.manifest import read_manifest
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


def _sparkline(values: list[float]) -> str:
    """Render a list of values as an ASCII sparkline."""
    if not values:
        return ""
    blocks = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    lo, hi = min(values), max(values)
    if lo == hi:
        return blocks[4] * len(values)
    return "".join(blocks[min(int((v - lo) / (hi - lo) * 7), 7)] for v in values)


def _json_mode(ctx: click.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("json_mode"))


def _resolve_json_mode(ctx: click.Context, sub_output_mode: str | None = None) -> bool:
    ctx.ensure_object(dict)
    if sub_output_mode is not None:
        ctx.obj["json_mode"] = sub_output_mode.strip().lower() == "json"
    return bool(ctx.obj.get("json_mode"))


_subcommand_output_option = click.option(
    "--output",
    "sub_output_mode",
    type=click.Choice(["human", "json"]),
    default=None,
    help="Output format (human or json).",
)


def _exit_for_broker(broker: OutputBroker, *, json_mode: bool) -> None:
    if not json_mode:
        return
    if broker.handled_exception:
        sys.exit(1)
    if broker.errors and broker.data:
        # Budget-only exhaustion → exit 2; real errors → exit 1
        all_budget = all(e.get("code") == "budget_exhausted" for e in broker.errors)
        sys.exit(2 if all_budget else 1)
    if broker.errors:
        sys.exit(1)


def _echo_legacy_warning(
    command_name: str,
    replacement: str,
    *,
    json_mode: bool,
    suppress: bool = False,
) -> None:
    """Warn humans when they invoke a hidden legacy command."""

    if json_mode or suppress:
        return
    click.echo(
        f"Warning: `ctx {command_name}` is deprecated. Use `ctx {replacement}` instead.",
        err=True,
    )


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
@click.option("--until-complete", is_flag=True, help="Loop until all directories are covered, pausing between cycles.")
@click.option("--synthesize", is_flag=True, help="Synthesize semantic cross-module invariants in Tier 2 (.ctx/) mode.")
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--max-depth", type=int, default=None)
@click.option("--token-budget", type=int, default=None)
@click.option("--base-url", default=None)
@click.option("--cache-path", default=None)
@_subcommand_output_option
@click.pass_context
def refresh(
    ctx: click.Context,
    path: str,
    force: bool,
    do_setup: bool,
    do_watch: bool,
    dry_run: bool,
    until_complete: bool,
    synthesize: bool,
    provider: Optional[str],
    model: Optional[str],
    max_depth: Optional[int],
    token_budget: Optional[int],
    base_url: Optional[str],
    cache_path: Optional[str],
    sub_output_mode: Optional[str] = None,
) -> None:
    """Generate or update CONTEXT.md manifests."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        state = ProgressState(start_time=time.time())
        refresh_extra: dict[str, object] = {}
        if synthesize:
            refresh_extra["synthesize"] = True
        result = api.refresh(
            Path(path),
            force=force,
            setup=do_setup,
            watch=do_watch,
            dry_run=dry_run,
            until_complete=until_complete,
            provider=provider,
            model=model,
            max_depth=max_depth,
            token_budget=token_budget,
            base_url=base_url,
            cache_path=cache_path,
            progress=_progress_callback(state, json_mode=json_mode),
            **refresh_extra,
        )
        broker.set_data(asdict(result))
        broker.set_tokens(result.tokens_used, result.est_cost_usd)
        if result.errors:
            for error in result.errors:
                # Preserve the dedicated machine-readable error code when the
                # appended refresh error came from the hard Stage 3 guardrail.
                if result.budget_guardrail and error == result.budget_guardrail:
                    broker.add_error("budget_exhausted", error)
                else:
                    broker.add_error("partial_failure", error)

        if not json_mode:
            for warning_msg in result.warnings:
                click.echo(f"Warning: {warning_msg}", err=True)
            if result.setup_provider:
                click.echo(f"Detected: {result.setup_provider} ({result.setup_detected_via or result.setup_provider})")
            if result.config_written:
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
            if result.local_batch_fallbacks > 0:
                click.echo(f"Local batch fallbacks: {result.local_batch_fallbacks}")
            click.echo(f"Errors: {len(result.errors)}")
            if result.errors:
                click.echo("Error details:")
                for error in result.errors:
                    click.echo(f"  - {error}")
                # Exit 2 for budget-only exhaustion (partial success),
                # exit 1 for real errors.
                real_errors = [
                    e for e in result.errors
                    if not (result.budget_guardrail and e == result.budget_guardrail)
                ]
                sys.exit(1 if real_errors else 2)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--force", is_flag=True, help="Reinitialize even if already initialized.")
@click.option(
    "--tier2",
    is_flag=True,
    help="Synthesize a gitignored .ctx/ architectural & invariant map without writing per-directory CONTEXT.md files.",
)
@click.option(
    "--synthesize",
    is_flag=True,
    help="Layer LLM-synthesized cross-module invariants onto Tier 2 (.ctx/) maps.",
)
@_subcommand_output_option
@click.pass_context
def init(
    ctx: click.Context,
    path: str,
    force: bool,
    tier2: bool = False,
    synthesize: bool = False,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Bootstrap self-maintaining .ctx/ infrastructure in a git repo."""
    from ctx.init import init_project, InitError

    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="init", json_mode=json_mode) as broker:
        try:
            init_kwargs: dict[str, object] = {"force": force}
            if tier2:
                init_kwargs["tier2"] = True
            if synthesize:
                init_kwargs["synthesize"] = True
            result = init_project(Path(path), **init_kwargs)
        except InitError as exc:
            if json_mode:
                broker.add_error("init_failed", str(exc))
            else:
                click.echo(f"Error: {exc}", err=True)
                sys.exit(1)
        else:
            broker.set_data(result)
            if not json_mode:
                for warning_msg in result.get("warnings", []):
                    click.echo(f"Warning: {warning_msg}", err=True)
                click.echo(f"Initialized ctx in {result['root']}")
                click.echo(f"  .ctx/ created with {len(result['exports'])} exports")
                click.echo(f"  Hooks installed: {', '.join(result['hooks_installed'])}")
                click.echo(f"  Manifests refreshed: {result['manifests_refreshed']} directories")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@_subcommand_output_option
@click.pass_context
def uninit(ctx: click.Context, path: str, sub_output_mode: Optional[str] = None) -> None:
    """Remove .ctx/ infrastructure and git hooks."""
    from ctx.init import uninit_project, InitError

    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="uninit", json_mode=json_mode) as broker:
        try:
            result = uninit_project(Path(path))
        except InitError as exc:
            if json_mode:
                broker.add_error("uninit_failed", str(exc))
            else:
                click.echo(f"Error: {exc}", err=True)
                sys.exit(1)
        else:
            broker.set_data(result)
            if not json_mode:
                click.echo(f"Removed ctx from {result['root']}")
                click.echo(f"  Hooks removed: {', '.join(result['hooks_removed'])}")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(name="_hook", hidden=True)
@click.option("--trigger", required=True, help="Hook trigger type (e.g. post-commit).")
@click.option("--root", "root_path", required=True, type=click.Path(exists=True, file_okay=False), help="Repository root.")
def hook_entrypoint(trigger: str, root_path: str) -> None:
    """Internal: hook entrypoint called by git hooks. Not for direct use."""
    from ctx.init import run_hook
    run_hook(Path(root_path), trigger)


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
    _echo_legacy_warning("update", "refresh", json_mode=json_mode)
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
        if stats.local_batch_fallbacks > 0:
            click.echo(f"Local batch fallbacks: {stats.local_batch_fallbacks}")
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
                "local_batch_fallbacks": stats.local_batch_fallbacks,
            }
        )
        broker.set_tokens(stats.tokens_used, cost)
        if stats.errors:
            for error in stats.errors:
                broker.add_error("partial_failure", error)
            if not json_mode:
                sys.exit(2 if stats.budget_exhausted and not any(
                    TRANSIENT_ERROR_PREFIX in e for e in stats.errors
                ) else 1)
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
    _echo_legacy_warning("status", "check", json_mode=json_mode)
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
@_subcommand_output_option
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
    sub_output_mode: Optional[str] = None,
) -> None:
    """Check manifest health, coverage, validation, or diffs."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
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
        elif result.mode == "health":
            click.echo("STATUS   PATH")
            for entry in result.directories:
                click.echo(f"{entry['status']:<8} {_display_status_path(str(entry['path']))}")
            summary = result.summary
            click.echo(f"{summary['fresh']} fresh, {summary['stale']} stale, {summary['missing']} missing")
            if check_exit and (summary["stale"] > 0 or summary["missing"] > 0):
                sys.exit(1)
        elif result.mode == "stats":
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
        elif result.mode == "diff":
            modified = sorted(entry["path"] for entry in result.directories if entry["status"] == "modified")
            new_files = sorted(entry["path"] for entry in result.directories if entry["status"] == "new")
            stale = sorted(entry["path"] for entry in result.directories if entry["status"] == "stale")
            changed = sorted(set(modified) | set(new_files))
            if quiet:
                if changed or stale:
                    sys.exit(1)
            elif stat:
                if stale:
                    click.echo(f"{len(stale)} stale")
                else:
                    parts = []
                    if modified:
                        parts.append(f"{len(modified)} modified")
                    if new_files:
                        parts.append(f"{len(new_files)} new")
                    click.echo(", ".join(parts) if parts else "No CONTEXT.md files changed.")
            elif stale:
                click.echo(f"{len(stale)} CONTEXT.md file{'s' if len(stale) != 1 else ''} may be stale (mtime check):")
                for file_path in stale:
                    click.echo(f"  [stale] {file_path}")
            elif not changed:
                click.echo("No CONTEXT.md files changed.")
            else:
                click.echo(f"{len(changed)} CONTEXT.md file{'s' if len(changed) != 1 else ''} changed:")
                for file_path in changed:
                    label = "new" if file_path in new_files else "mod"
                    click.echo(f"  [{label}] {file_path}")
        else:
            invalid_entries = [entry for entry in result.directories if entry["status"] != "fresh"]
            malformed = [entry["path"] for entry in invalid_entries if entry["status"] == "malformed"]
            missing = [entry["path"] for entry in invalid_entries if entry["status"] == "missing"]
            stale = [entry["path"] for entry in invalid_entries if entry["status"] == "stale"]
            missing_fields = [entry for entry in invalid_entries if entry["status"] == "missing_fields"]
            invalid_bodies = [entry for entry in invalid_entries if entry["status"] == "invalid_body"]
            if malformed:
                click.echo("Malformed frontmatter:")
                for rel in malformed:
                    click.echo(f"  {rel}")
            if missing_fields:
                click.echo("Missing required fields:")
                for item in missing_fields:
                    click.echo(f"  {item['path']}: {', '.join(item['fields'])}")
            if invalid_bodies:
                click.echo("Invalid manifest bodies:")
                for item in invalid_bodies:
                    click.echo(f"  {item['path']}:")
                    for issue in item["issues"]:
                        click.echo(f"    - {issue}")
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
    _echo_legacy_warning("smart-update", "refresh", json_mode=json_mode)
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
                sys.exit(2 if stats.budget_exhausted and not any(
                    TRANSIENT_ERROR_PREFIX in e for e in stats.errors
                ) else 1)
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
    _echo_legacy_warning("watch", "refresh --watch", json_mode=json_mode)
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


@cli.command()
@click.argument("path", default=".", required=False)
@click.option("--check", "check_only", is_flag=True, help="Print detected provider without writing config.")
@_subcommand_output_option
@click.pass_context
def setup(
    ctx: click.Context,
    path: str,
    check_only: bool,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Auto-detect LLM provider, run preflight checks, or write .ctxconfig."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    _echo_legacy_warning("setup", "refresh --setup", json_mode=json_mode, suppress=check_only)
    with OutputBroker(command="setup", json_mode=json_mode) as broker:
        target_path = Path(path)
        config_file = target_path / ".ctxconfig"

        if check_only:
            from ctx.preflight import run_preflight
            result = run_preflight(path)

            if not json_mode:
                click.echo("ctx preflight — checking readiness for ctx refresh\n")
                for check in result.checks:
                    prefix = {"ok": "[ OK ]", "fail": "[FAIL]", "info": "[INFO]"}[check.status]
                    label = check.name.replace("_", " ").title()
                    click.echo(f"{prefix} {label}: {check.detail}")
                    if check.fix:
                        click.echo(f"  Fix: {check.fix}")
                click.echo()
                if result.ready:
                    click.echo("Ready to run: ctx refresh .")
                else:
                    click.echo("Preflight failed. Fix the issues above and re-run: ctx setup --check")

            broker.set_data({
                "check_only": True,
                "checks": {
                    c.name: {"status": c.status, "detail": c.detail, **({"fix": c.fix} if c.fix else {})}
                    for c in result.checks
                },
                "ready": result.ready,
                "provider": result.provider,
                "model": result.model,
            })
            if not result.ready and not json_mode:
                sys.exit(1)
            elif not result.ready:
                broker.add_error(
                    "preflight_failed",
                    f"{sum(1 for c in result.checks if c.status == 'fail')} check(s) failed",
                    hint="ctx setup --check",
                )
        else:
            def _probe_msg(provider: str) -> None:
                label = {"ollama": "Ollama", "lmstudio": "LM Studio"}.get(provider, provider)
                click.echo(f"Probing {label}...")

            cancelled = False
            if config_file.exists():
                click.echo(f".ctxconfig already exists:\n\n{config_file.read_text(encoding='utf-8')}")
                if not click.confirm("Overwrite?", default=False):
                    click.echo("Cancelled.")
                    broker.set_data({"configured": False, "provider": None, "model": None})
                    cancelled = True

            if not cancelled:
                det = detect_provider(_probe_callback=_probe_msg)
                if det is None:
                    raise click.UsageError(
                        "No LLM provider detected.\n"
                        "  Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or start Ollama / LM Studio first."
                    )

                provider_name, model_name = det
                detected_via = PROVIDER_DETECTED_VIA.get(provider_name, provider_name)
                click.echo(f"Detected: {provider_name} ({detected_via})")

                base_url_value = DEFAULT_BASE_URLS.get(provider_name)
                write_default_config(target_path, provider_name, model=model_name, base_url=base_url_value)
                click.echo(f"Config written to {config_file}")
                click.echo("\nNext step: run `ctx refresh .` to generate manifests.")
                broker.set_data({"configured": True, "provider": provider_name, "model": model_name})
                broker.set_recommended_next("ctx refresh .")
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
    _echo_legacy_warning("diff", "check --diff", json_mode=json_mode, suppress=output_format == "json" or quiet)
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
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output file path (default: stdout), or 'json'/'human' to select output format.",
)
@click.option(
    "--out-file",
    default=None,
    help="Output file path (unambiguous alternative to -o/--output).",
)
@click.option(
    "--filter", "filter_mode",
    type=click.Choice(["all", "stale", "missing"]),
    default="all",
    help="Which manifests to export: all (default), stale, or missing.",
)
@click.option("--depth", type=int, default=None, help="Limit export to N levels of nesting (0 = root only).")
@click.option(
    "--capsule",
    is_flag=True,
    help="Emit a deterministic structural & invariant capsule for project-ledger and gbrain ingestion.",
)
@click.pass_context
def export(
    ctx: click.Context,
    path: str,
    output: Optional[str],
    out_file: Optional[str] = None,
    filter_mode: str = "all",
    depth: Optional[int] = None,
    capsule: bool = False,
) -> None:
    """Concatenate all CONTEXT.md files to stdout or a file.

    Each manifest is prefixed with a header line:
        # path/to/CONTEXT.md

    Respects .ctxignore patterns (same as ctx init/update).
    """
    resolved_out_file = out_file
    sub_output_mode: Optional[str] = None
    if output is not None:
        if output.strip().lower() in ("json", "human"):
            sub_output_mode = output.strip().lower()
        elif resolved_out_file is None:
            resolved_out_file = output

    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="export", json_mode=json_mode) as broker:
        root = Path(path).resolve()
        if capsule:
            capsule_res = api.build_fleet_capsule(
                root,
                depth=1 if depth is None else depth,
                output_file=resolved_out_file,
            )
            broker.set_data(asdict(capsule_res))
            if not json_mode:
                if resolved_out_file:
                    click.echo(f"Exported fleet capsule for {capsule_res.repo_name} to {resolved_out_file}")
                else:
                    click.echo(capsule_res.capsule_markdown, nl=False)
        else:
            exp_res = api.export_context(
                root,
                output_file=resolved_out_file,
                filter_mode=filter_mode,
                depth=depth,
            )
            broker.set_data(asdict(exp_res))
            if not json_mode:
                if resolved_out_file:
                    n = exp_res.manifests_exported
                    if filter_mode == "missing":
                        click.echo(f"Exported {n} missing director{'y' if n == 1 else 'ies'} to {resolved_out_file}")
                    else:
                        click.echo(f"Exported {n} manifest{'s' if n != 1 else ''} to {resolved_out_file}")
                elif exp_res.content:
                    click.echo(exp_res.content, nl=False)
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="Show per-directory breakdown table.")
@click.option("--format", "output_format", type=click.Choice(["text", "json", "csv"]), default="text", help="Output format.")
@click.option("--board", is_flag=True, help="Show the running board (refresh history).")
@click.option("--global", "show_global", is_flag=True, help="Show global running board across all repos.")
@click.option("--since", default=None, help="Filter runs to a time window (e.g. 7d, 4w, 2026-03-01).")
@click.option("--trend", is_flag=True, help="Show cost and cache-hit sparklines.")
@click.pass_context
def stats(ctx: click.Context, path: str, verbose: bool, output_format: str, board: bool, show_global: bool, since: Optional[str], trend: bool) -> None:
    """Show coverage summary across all directories.

    Reports:
      dirs        — total directories found (respects .ctxignore)
      covered     — directories with a CONTEXT.md
      missing     — directories without a CONTEXT.md
      stale       — directories whose manifest hash no longer matches current contents
      tokens      — sum of tokens_total from all manifest frontmatters
    """
    json_mode = _json_mode(ctx)
    _echo_legacy_warning("stats", "check --stats", json_mode=json_mode, suppress=output_format == "json" or board)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        root = Path(path).resolve()

        if board:
            from ctx.stats_board import read_board, read_global_board, read_trend
            from ctx.config import load_config as _load_cfg

            if show_global:
                board_data = read_global_board()
                broker.set_data(board_data)
                if output_format == "json" and not json_mode:
                    click.echo(json.dumps(board_data, indent=2))
                else:
                    totals = board_data.get("totals", {})
                    repos = board_data.get("repos", {})
                    if not totals.get("total_runs", 0):
                        click.echo("No runs recorded yet.")
                    else:
                        click.echo("ctx running board — global\n")
                        click.echo(f"Repos tracked:      {totals.get('repos_touched', 0)}")
                        click.echo(f"Total runs:         {totals.get('total_runs', 0)}")
                        click.echo(f"Total directories:  {totals.get('total_dirs_processed', 0)}")
                        tu = totals.get("total_tokens_used", 0)
                        ts = totals.get("total_tokens_saved", 0)
                        click.echo(f"Total tokens:       {tu / 1_000_000:.2f}M" if tu >= 1_000_000 else f"Total tokens:       {tu}")
                        click.echo(f"Total cost:         ${totals.get('total_cost_usd', 0.0):.3f}")
                        click.echo(f"Total tokens saved: {ts / 1_000_000:.2f}M  (est.)" if ts >= 1_000_000 else f"Total tokens saved: {ts}  (est.)")
                        click.echo(f"Total cost saved:   ${totals.get('total_cost_saved_usd', 0.0):.3f} (est.)")
                        if repos:
                            click.echo("\nPer-repo breakdown:")
                            for repo_key, repo_val in repos.items():
                                click.echo(
                                    f"  {repo_key:<40} {repo_val.get('run_count', 0):3d} runs"
                                    f"  {repo_val.get('total_dirs_processed', 0):4d} dirs"
                                    f"  ${repo_val.get('total_cost_usd', 0.0):.2f}"
                                )
            else:
                try:
                    config = _load_cfg(root, require_api_key=False)
                except Exception:
                    from ctx.config import Config as _Cfg
                    config = _Cfg()
                board_data = read_board(root, config, since=since)
                broker.set_data(board_data)
                if output_format == "csv" and not json_mode:
                    recent = board_data.get("recent_runs", [])
                    if recent:
                        headers = list(recent[0].keys())
                        click.echo(",".join(headers))
                        for run in recent:
                            click.echo(",".join(str(run.get(h, "")) for h in headers))
                    else:
                        click.echo("No runs recorded yet.")
                elif output_format == "json" and not json_mode:
                    click.echo(json.dumps(board_data, indent=2))
                else:
                    agg = board_data.get("aggregate", {})
                    recent = board_data.get("recent_runs", [])
                    if not agg.get("run_count", 0):
                        click.echo("No runs recorded yet.")
                    else:
                        click.echo(f"ctx running board — {board_data.get('repo', str(root))}\n")
                        click.echo(f"Runs:           {agg.get('run_count', 0)}")
                        click.echo(f"Directories:    {agg.get('total_dirs_processed', 0):>8}  total processed")
                        tu = agg.get("total_tokens_used", 0)
                        ts = agg.get("total_tokens_saved", 0)
                        click.echo(f"Tokens used:    {tu / 1_000_000:>8.2f}M  across all runs" if tu >= 1_000_000 else f"Tokens used:    {tu:>8}  across all runs")
                        click.echo(f"Tokens saved:   {ts / 1_000_000:>8.2f}M  (est. via cache)" if ts >= 1_000_000 else f"Tokens saved:   {ts:>8}  (est. via cache)")
                        click.echo(f"Cost:           ${agg.get('total_cost_usd', 0.0):>8.3f}")
                        click.echo(f"Cost saved:     ${agg.get('total_cost_saved_usd', 0.0):>8.3f}  (est. via cache)")
                        hr = agg.get("cache_hit_rate", 0.0)
                        click.echo(f"Cache hit rate: {hr * 100:>7.0f}%")
                        if recent:
                            click.echo("\nRecent runs (last 5):")
                            for run in recent:
                                ts_str = run.get("ts", "")[:16].replace("T", " ")
                                rt = run.get("tokens_used", 0)
                                rhr = run.get("cache_hits", 0)
                                rmr = run.get("cache_misses", 0)
                                r_total = rhr + rmr
                                r_hr_pct = round(rhr * 100 / r_total) if r_total > 0 else 0
                                click.echo(
                                    f"  {ts_str}  {run.get('strategy', ''):<13}"
                                    f"  {run.get('dirs_processed', 0):4d} dirs"
                                    f"  {rt / 1000:.0f}K tokens"
                                    f"  ${run.get('est_cost_usd', 0.0):.3f}"
                                    f"  {r_hr_pct}% cache"
                                )
                        per_model = board_data.get("per_model", {})
                        if per_model:
                            click.echo("\nPer-model breakdown:")
                            for model_key, model_val in per_model.items():
                                click.echo(
                                    f"  {model_key:<40} {model_val.get('run_count', 0):3d} runs"
                                    f"  {model_val.get('total_tokens_used', 0):>8} tokens"
                                    f"  ${model_val.get('total_cost_usd', 0.0):.3f}"
                                )
                        if trend:
                            trend_data = read_trend(root, config)
                            if trend_data:
                                costs = [t["est_cost_usd"] for t in trend_data]
                                hit_rates = [t["cache_hit_rate"] for t in trend_data]
                                click.echo(f"\nTrend (last {len(trend_data)} runs):")
                                click.echo(f"  Cost:      {_sparkline(costs)}")
                                click.echo(f"  Cache hit: {_sparkline(hit_rates)}")
            _exit_for_broker(broker, json_mode=json_mode)
            return

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


def _execute_reset_command(
    root: Path,
    *,
    yes: bool,
    dry_run: bool,
    json_mode: bool,
    broker: OutputBroker,
    confirm_error_code: str = "confirmation_required",
    legacy_empty_noop: bool = False,
) -> None:
    """Shared implementation for `ctx reset` and legacy `ctx clean` delegating to `api.reset`."""
    if legacy_empty_noop and not dry_run and not api._iter_tree_manifests(root):
        broker.set_data({"manifests_removed": 0, "paths": []})
        if not json_mode:
            click.echo("No CONTEXT.md files found.")
        return

    if json_mode and not yes and not dry_run:
        broker.add_error(
            confirm_error_code,
            "--yes flag required in non-interactive mode",
            hint="Use: ctx reset . --yes --output json",
        )
        broker.set_data({"manifests_removed": 0, "paths": []})
        return

    aborted = False
    if not yes and not dry_run and not json_mode:
        manifests = api._iter_tree_manifests(root)
        if manifests:
            confirmed = click.confirm(
                f"Found {len(manifests)} CONTEXT.md file(s). Delete all?",
                default=False,
            )
            if not confirmed:
                click.echo("Aborted.")
                broker.set_data({"manifests_removed": 0, "paths": []})
                aborted = True
        if not aborted:
            yes = True

    if not aborted:
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
            elif legacy_empty_noop and result.manifests_removed == 0 and not result.paths:
                click.echo("No CONTEXT.md files found.")
            else:
                click.echo(f"Removed {result.manifests_removed} CONTEXT.md file(s).")


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--dry-run", is_flag=True, help="List CONTEXT.md files that would be deleted without removing them.")
@_subcommand_output_option
@click.pass_context
def reset(
    ctx: click.Context,
    path: str,
    yes: bool,
    dry_run: bool,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Remove all CONTEXT.md files from the directory tree."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="reset", json_mode=json_mode) as broker:
        _execute_reset_command(
            Path(path).resolve(),
            yes=yes,
            dry_run=dry_run,
            json_mode=json_mode,
            broker=broker,
            confirm_error_code="confirmation_required",
        )
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(hidden=True)
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--dry-run", is_flag=True, help="List CONTEXT.md files that would be deleted without removing them.")
@_subcommand_output_option
@click.pass_context
def clean(
    ctx: click.Context,
    path: str,
    yes: bool,
    dry_run: bool,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Remove all CONTEXT.md files from the directory tree."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    _echo_legacy_warning("clean", "reset", json_mode=json_mode)
    with OutputBroker(command="reset", json_mode=json_mode) as broker:
        _execute_reset_command(
            Path(path).resolve(),
            yes=yes,
            dry_run=dry_run,
            json_mode=json_mode,
            broker=broker,
            confirm_error_code="unknown_error",
            legacy_empty_noop=True,
        )
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
    _echo_legacy_warning("verify", "check --verify", json_mode=json_mode, suppress=output_format == "json")
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
        invalid_bodies: list[tuple[str, list[str]]] = []

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
                invalid_bodies.append((entry.relative_path, issues))

        stale_manifests = sorted(
            entry.relative_path for entry in health_entries
            if entry.status == "stale"
            and entry.error is None
            and entry.relative_path not in invalid_field_paths
        )

        invalid_paths = (
            set(malformed_manifests)
            | invalid_field_paths
            | {rel for rel, _issues in invalid_bodies}
            | set(stale_manifests)
            | set(missing_manifests)
        )
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
            "invalid_body": [
                {"path": rel, "issues": issues}
                for rel, issues in sorted(invalid_bodies)
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
                "invalid_body": [
                    {"path": rel, "issues": issues}
                    for rel, issues in sorted(invalid_bodies)
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

        if invalid_bodies:
            click.echo("Invalid manifest bodies:")
            for rel, issues in sorted(invalid_bodies):
                click.echo(f"  {rel}:")
                for issue in issues:
                    click.echo(f"    - {issue}")

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
@click.option("--host", default="127.0.0.1", help="Host address for the HTTP server.")
@click.option("--port", type=int, default=8000, help="Port for the HTTP server.")
@click.option("--mcp", is_flag=True, help="Launch stdio MCP server instead of HTTP.")
@click.pass_context
def serve(ctx: click.Context, path: str, host: str, port: int, mcp: bool) -> None:
    """Start the ctx server.

    Default mode serves manifests over HTTP. With --mcp, start the stdio MCP server.
    """
    root = Path(path).resolve()
    if mcp:
        from ctx.mcp_server import CtxMCPServer

        CtxMCPServer(root).run()
        return

    try:
        from ctx.server import start_server
    except ImportError as exc:
        raise click.UsageError(
            "HTTP server requires FastAPI. Install with: pip install ctx-tool[serve]"
        ) from exc

    click.echo(f"Starting ctx HTTP server on http://{host}:{port}")
    click.echo(f"Serving manifests from: {root}")
    start_server(host=host, port=port, root=root)


@cli.command("impact")
@click.argument("target")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--depth", type=int, default=None, help="Maximum reverse-dependency BFS depth (>= 1).")
@_subcommand_output_option
@click.pass_context
def impact(
    ctx: click.Context,
    target: str,
    path: str,
    depth: Optional[int],
    sub_output_mode: Optional[str] = None,
) -> None:
    """Analyze reverse-dependency blast radius, coupled tests, and governing docs."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="impact", json_mode=json_mode) as broker:
        try:
            result = api.analyze_impact(Path(path), target, max_depth=depth)
        except ValueError as exc:
            if json_mode:
                broker.add_error("invalid_target", str(exc))
            else:
                raise click.ClickException(str(exc)) from exc
            result = None

        if result is not None:
            broker.set_data(asdict(result))
            if not json_mode:
                click.echo(f"Target: {result.target} ({result.target_kind})")
                click.echo(f"Matched files ({len(result.matched_files)}): {', '.join(result.matched_files)}")
                if result.matched_symbols:
                    preview_syms = ", ".join(result.matched_symbols[:8])
                    suffix = f" (+{len(result.matched_symbols) - 8} more)" if len(result.matched_symbols) > 8 else ""
                    click.echo(f"Matched symbols ({len(result.matched_symbols)}): {preview_syms}{suffix}")
                if result.layer_index is not None:
                    click.echo(f"Topological layer: {result.layer_index + 1} / {result.total_layers}")
                click.echo(
                    f"Direct outbound deps ({len(result.direct_outbound_deps)}): "
                    f"{', '.join(result.direct_outbound_deps) if result.direct_outbound_deps else 'none'}"
                )
                click.echo(
                    f"Direct inbound dependents ({len(result.direct_inbound_dependents)}): "
                    f"{', '.join(result.direct_inbound_dependents) if result.direct_inbound_dependents else 'none'}"
                )
                click.echo(f"Transitive inbound dependents: {len(result.transitive_inbound_dependents)}")
                for rec in result.transitive_inbound_dependents[:15]:
                    tag = " [test]" if rec.get("is_test") else ""
                    click.echo(f"  - [d={rec['distance']}] {rec['path']}{tag}")
                if len(result.transitive_inbound_dependents) > 15:
                    click.echo(f"  ... (+{len(result.transitive_inbound_dependents) - 15} more)")
                click.echo(f"Coupled tests ({len(result.coupled_tests)}):")
                for test_rec in result.coupled_tests[:15]:
                    dist_part = f", d={test_rec['distance']}" if test_rec.get("distance") is not None else ""
                    click.echo(f"  - {test_rec['path']} ({test_rec['reason']}{dist_part})")
                if len(result.coupled_tests) > 15:
                    click.echo(f"  ... (+{len(result.coupled_tests) - 15} more)")
                click.echo(
                    f"Affected subsystems ({len(result.affected_subsystems)}): "
                    f"{', '.join(result.affected_subsystems) if result.affected_subsystems else 'none'}"
                )
                if result.affected_entrypoints:
                    click.echo(f"Affected entrypoints & surfaces ({len(result.affected_entrypoints)}):")
                    for ep in result.affected_entrypoints[:15]:
                        click.echo(f"  - {ep}")
                    if len(result.affected_entrypoints) > 15:
                        click.echo(f"  ... (+{len(result.affected_entrypoints) - 15} more)")
                if result.governing_docs:
                    click.echo(f"Governing docs: {', '.join(result.governing_docs)}")
                if result.cycles_involving_target:
                    click.echo(f"Cycles involving target ({len(result.cycles_involving_target)}):")
                    for cyc in result.cycles_involving_target:
                        click.echo(f"  - {' -> '.join(cyc)}")
    _exit_for_broker(broker, json_mode=json_mode)


def _parse_cli_state_json(raw_state: str) -> dict[str, object]:
    """Load a state dictionary from inline JSON or `@path/to/file.json`."""
    payload_str = raw_state
    if raw_state.startswith("@"):
        state_path = Path(raw_state[1:])
        try:
            payload_str = state_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Unable to read state file {state_path}: {exc}") from exc
    try:
        parsed = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON state payload: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("State payload must be a JSON object.")
    return parsed


@cli.group("jev")
def jev_group() -> None:
    """Inspect, execute, and evaluate governed Type 1 Jev System-One heads."""


@jev_group.command("heads")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@_subcommand_output_option
@click.pass_context
def jev_heads_cmd(
    ctx: click.Context,
    path: str,
    sub_output_mode: Optional[str] = None,
) -> None:
    """List governed Type 1 Jev decision heads."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="jev.heads", json_mode=json_mode) as broker:
        heads, warnings = api.jev_list_heads_with_warnings(Path(path))
        payload: dict[str, object] = {"heads": heads, "count": len(heads)}
        if warnings:
            payload["warnings"] = warnings
        broker.set_data(payload)
        if not json_mode:
            for w in warnings:
                click.echo(f"Warning: Skipped invalid custom Jev head ({w})", err=True)
            click.echo(f"Governed Type 1 Jev heads ({len(heads)}):")
            for h in heads:
                auth_flag = " [authority ceiling: ADVISORY]" if h.get("authority") else ""
                prov = h.get("provider", {}) if isinstance(h.get("provider"), dict) else {}
                click.echo(
                    f"  - {h['id']} (v{h['version']}, type={h['type']}, "
                    f"state={h['promotion_state']}, model={prov.get('model')}){auth_flag}"
                )
    _exit_for_broker(broker, json_mode=json_mode)


@jev_group.command("decide")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--head", "head_ids", multiple=True, required=True, help="Head ID to execute (repeatable).")
@click.option("--state", "raw_state", required=True, help="JSON state object or @path/to/state.json.")
@click.option("--provider", type=click.Choice(["code", "jev"]), default=None, help="Override execution provider.")
@click.option("--live", is_flag=True, help="Permit 1Password vault resolution when TYPESAFE_API_KEY is unset.")
@click.option("--no-trace", is_flag=True, help="Do not append decision trace to .ctx-cache/jev_decisions.jsonl.")
@_subcommand_output_option
@click.pass_context
def jev_decide_cmd(
    ctx: click.Context,
    path: str,
    head_ids: tuple[str, ...],
    raw_state: str,
    provider: Optional[str],
    live: bool,
    no_trace: bool,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Run one or more governed Type 1 Jev heads on a structured JSON state."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="jev.decide", json_mode=json_mode) as broker:
        try:
            state_obj = _parse_cli_state_json(raw_state)
            result = api.jev_decide(
                list(head_ids),
                state_obj,
                root=Path(path),
                provider=provider,
                allow_vault=live,
                record_trace=not no_trace,
            )
        except ValueError as exc:
            if json_mode:
                broker.add_error("invalid_input", str(exc))
                result = None
            else:
                raise click.ClickException(str(exc)) from exc

        if result is not None:
            decisions = result.get("decisions", []) if isinstance(result, dict) else []
            tok = sum(int(d.get("input_tokens") or 0) for d in decisions if isinstance(d, dict))
            cost = sum(float(d.get("cost_usd") or 0.0) for d in decisions if isinstance(d, dict))
            broker.set_data(result)
            broker.set_tokens(tok, cost)
            if not json_mode:
                for d in decisions:
                    conf = f"{d['confidence']:.3f}" if isinstance(d.get("confidence"), (int, float)) else "n/a"
                    click.echo(
                        f"[{d['head_id']}] effective={d['effective_output']!r} "
                        f"(tier={d['tier']}, provider={d['provider']}, model={d['model']}, "
                        f"route={d['route']}, confidence={conf})"
                    )
    _exit_for_broker(broker, json_mode=json_mode)


@jev_group.command("eval")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["code", "jev"]), default="code", help="Provider to evaluate.")
@click.option("--head", "head_ids", multiple=True, help="Restrict evaluation to specific head ID(s).")
@click.option("--live", is_flag=True, help="Permit 1Password vault resolution when TYPESAFE_API_KEY is unset.")
@click.option("--skip-pre-rule", is_flag=True, help="Force raw model inference even on pre_rule cases.")
@_subcommand_output_option
@click.pass_context
def jev_eval_cmd(
    ctx: click.Context,
    path: str,
    provider: str,
    head_ids: tuple[str, ...],
    live: bool,
    skip_pre_rule: bool,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Evaluate governed Type 1 Jev heads against the gold evaluation corpus."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="jev.eval", json_mode=json_mode) as broker:
        try:
            report = api.evaluate_jev_heads(
                Path(path),
                provider=provider,
                head_ids=list(head_ids) if head_ids else None,
                allow_vault=live,
                skip_pre_rule_for_jev=skip_pre_rule,
            )
        except ValueError as exc:
            if json_mode:
                broker.add_error("invalid_input", str(exc))
                report = None
            else:
                raise click.ClickException(str(exc)) from exc

        if report is not None:
            broker.set_data(report)
            broker.set_tokens(int(report.get("total_input_tokens") or 0), float(report.get("total_cost_usd") or 0.0))
            if not json_mode:
                acc = report.get("accuracy")
                acc_str = f"{acc * 100:.1f}%" if isinstance(acc, (int, float)) else "n/a"
                brier = report.get("brier_score")
                brier_str = f"{brier:.6f}" if isinstance(brier, (int, float)) else "n/a"
                click.echo(
                    f"Jev Gold Evaluation (provider={report['provider']}): "
                    f"evaluated={report['evaluated']}/{report['total']} "
                    f"(coverage={report['coverage'] * 100:.1f}%), accuracy={acc_str}, brier={brier_str}"
                )
                for hid, summary in sorted((report.get("per_head") or {}).items()):
                    h_acc = summary.get("accuracy")
                    h_acc_s = f"{h_acc * 100:.1f}%" if isinstance(h_acc, (int, float)) else "n/a"
                    click.echo(
                        f"  - {hid}: {summary['evaluated']}/{summary['total']} evaluated, accuracy={h_acc_s}"
                    )
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command("benchmark")
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
)
@click.option(
    "--out-file",
    "-o",
    "output_file",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write Markdown or .json benchmark report to file.",
)
@_subcommand_output_option
@click.pass_context
def benchmark_cmd(
    ctx: click.Context,
    paths: tuple[str, ...],
    output_file: Optional[str],
    sub_output_mode: Optional[str] = None,
) -> None:
    """Run the Phase 27.1 A/B/C agent navigation & blast-radius benchmark."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    target_paths = [Path(p) for p in paths] if paths else [Path(".").resolve()]
    with OutputBroker(command="benchmark", json_mode=json_mode) as broker:
        report = api.run_benchmark(target_paths, output_file=output_file)
        broker.set_data(report)
        if not json_mode:
            summary = report["summary"]
            aggs = summary["aggregates"]
            click.echo(
                f"Phase 27.1 Navigation Benchmark ({report['repos_evaluated']} repo(s)):\n"
                f"  Token reduction vs raw_grep: {summary['token_reduction_vs_raw_grep_pct']:+.1f}%\n"
                f"  Turn reduction vs raw_grep:  {summary['turn_reduction_vs_raw_grep_pct']:+.1f}%\n"
                f"  Mean recall gain vs raw_grep: {summary['recall_gain_vs_raw_grep_pct']:+.1f} pp"
            )
            for cond in ("raw_grep", "tier1_manifests", "tier2_plus_impact"):
                c = aggs[cond]
                click.echo(
                    f"  - {cond}: turns={c['mean_tool_turns']}, "
                    f"tokens={c['mean_context_tokens_read']}, "
                    f"mean_recall={c['mean_recall'] * 100:.1f}%, "
                    f"blast_recall={c['mean_blast_radius_recall'] * 100:.1f}%"
                )
            if output_file:
                click.echo(f"Wrote benchmark report to {output_file}")
    _exit_for_broker(broker, json_mode=json_mode)

