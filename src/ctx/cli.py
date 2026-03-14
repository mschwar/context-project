"""Click CLI entry point for ctx.

Commands:
    ctx init <path>     Generate CONTEXT.md files for a directory tree.
    ctx update <path>   Incrementally refresh stale CONTEXT.md files.
    ctx status [path]   Show manifest health across a directory tree.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable, Optional

import click

from ctx import __version__
from ctx.config import (
    DEFAULT_BASE_URLS,
    PROVIDER_DETECTED_VIA,
    MissingApiKeyError,
    detect_provider,
    load_config,
    write_default_config,
)
from ctx.generator import GenerateStats, check_stale_dirs, generate_tree, get_status, update_tree
from ctx.ignore import load_ignore_patterns
from ctx.llm import create_client


def _build_generation_runtime(
    path: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_depth: Optional[int] = None,
    token_budget: Optional[int] = None,
    base_url: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> tuple[Path, object, object, object, Callable[[Path, int, int], None]]:
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
    spec = load_ignore_patterns(target_path)
    client = create_client(config)
    progress_cb = _progress_callback()
    return target_path, config, spec, client, progress_cb


def _progress_callback() -> Callable[[Path, int, int], None]:
    def callback(current_dir: Path, done: int, total: int) -> None:
        click.echo(f"  [{done}/{total}] Processing {current_dir.name or current_dir}")

    return callback


def _echo_generation_errors(stats: GenerateStats) -> None:
    if not stats.errors:
        return

    click.echo("Errors:")
    for error in stats.errors:
        click.echo(f"  - {error}")


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


@click.group()
@click.version_option(version=__version__, prog_name="ctx")
def cli() -> None:
    """ctx — Filesystem-native context layer for AI agents."""
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None, help="LLM provider.")
@click.option("--model", default=None, help="Model ID override.")
@click.option("--max-depth", type=int, default=None, help="Max directory depth to process.")
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
@click.option("--cache-path", default=None, help="Disk cache file path. Set to '' to disable.")
def init(path: str, provider: Optional[str], model: Optional[str], max_depth: Optional[int], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str]) -> None:
    """Generate CONTEXT.md files for a directory tree."""
    target_path, config, spec, client, progress_cb = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        max_depth=max_depth,
        token_budget=token_budget,
        base_url=base_url,
        cache_path=cache_path,
    )

    click.echo(f"ctx init: generating manifests for {target_path}")
    if config.token_budget:
        click.echo(f"Token budget: {config.token_budget:,}")
    stats = generate_tree(target_path, config, client, spec, progress=progress_cb)
    click.echo(f"Directories processed: {stats.dirs_processed}")
    click.echo(f"Files processed: {stats.files_processed}")
    click.echo(f"Tokens used: {stats.tokens_used}")
    click.echo(f"Errors: {len(stats.errors)}")
    _echo_generation_errors(stats)
    _echo_budget_warning(stats, config)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
@click.option("--cache-path", default=None, help="Disk cache file path. Set to '' to disable.")
@click.option("--dry-run", is_flag=True, help="List stale directories without regenerating.")
def update(path: str, provider: Optional[str], model: Optional[str], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str], dry_run: bool) -> None:
    """Incrementally refresh stale CONTEXT.md files."""
    target_path = Path(path)
    spec = load_ignore_patterns(target_path)

    if dry_run:
        config = load_config(target_path, provider=provider, model=model, token_budget=token_budget, base_url=base_url, cache_path=cache_path, require_api_key=False)
        stale = check_stale_dirs(target_path, config, spec)
        if not stale:
            click.echo("All manifests are fresh. Nothing to regenerate.")
            return
        _echo_stale_dirs(stale, target_path)
        return

    target_path, config, spec, client, progress_cb = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        token_budget=token_budget,
        base_url=base_url,
        cache_path=cache_path,
    )

    click.echo(f"ctx update: refreshing manifests for {target_path}")
    if config.token_budget:
        click.echo(f"Token budget: {config.token_budget:,}")
    stats = update_tree(target_path, config, client, spec, progress=progress_cb)
    click.echo(f"Directories refreshed: {stats.dirs_processed}")
    click.echo(f"Directories skipped: {stats.dirs_skipped}")
    click.echo(f"Tokens used: {stats.tokens_used}")
    click.echo(f"Errors: {len(stats.errors)}")
    _echo_generation_errors(stats)
    _echo_budget_warning(stats, config)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--check-exit-code", is_flag=True, help="Exit with code 1 if any manifests are stale or missing.")
def status(path: str, check_exit_code: bool) -> None:
    """Show manifest health across a directory tree.

    Implementation:
        1. load_ignore_patterns(Path(path)).
        2. results = get_status(Path(path), spec, Path(path)).
        3. Print a table:
           STATUS   PATH
           fresh    ./src
           stale    ./src/routes
           missing  ./tests
        4. Print summary counts: N fresh, N stale, N missing.
        5. If check_exit_code is True and stale or missing > 0, sys.exit(1).
    """
    target_path = Path(path)
    spec = load_ignore_patterns(target_path)
    results = get_status(target_path, spec, target_path)

    click.echo("STATUS   PATH")
    for result in results:
        click.echo(f"{result['status']:<8} {_display_status_path(result['path'])}")

    counts = Counter(result["status"] for result in results)
    click.echo(
        f"{counts.get('fresh', 0)} fresh, {counts.get('stale', 0)} stale, "
        f"{counts.get('missing', 0)} missing"
    )

    if check_exit_code and (counts.get("stale", 0) > 0 or counts.get("missing", 0) > 0):
        import sys
        sys.exit(1)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
@click.option("--cache-path", default=None, help="Disk cache file path. Set to '' to disable.")
@click.option("--dry-run", is_flag=True, help="List affected directories without regenerating.")
def smart_update(path: str, provider: Optional[str], model: Optional[str], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str], dry_run: bool) -> None:
    """Incrementally refresh stale CONTEXT.md files, focusing on git-changed files."""
    from ctx.git import get_changed_files

    target_path = Path(path)
    spec = load_ignore_patterns(target_path)

    changed_files = get_changed_files(target_path)
    if not changed_files:
        click.echo("No git-changed files detected. Nothing to update.")
        return

    if dry_run:
        config = load_config(target_path, provider=provider, model=model, token_budget=token_budget, base_url=base_url, cache_path=cache_path, require_api_key=False)
        stale = check_stale_dirs(target_path, config, spec, changed_files=changed_files)
        click.echo(f"Detected {len(changed_files)} changed files.")
        if not stale:
            click.echo("All affected manifests are fresh. Nothing to regenerate.")
            return
        _echo_stale_dirs(stale, target_path)
        return

    target_path, config, spec, client, progress_cb = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        token_budget=token_budget,
        base_url=base_url,
        cache_path=cache_path,
    )

    click.echo(f"ctx smart-update: refreshing manifests for {target_path} based on git changes")
    click.echo(f"Detected {len(changed_files)} changed files. Processing affected directories.")
    if config.token_budget:
        click.echo(f"Token budget: {config.token_budget:,}")
    stats = update_tree(target_path, config, client, spec, progress=progress_cb, changed_files=changed_files)
    click.echo(f"Directories refreshed: {stats.dirs_processed}")
    click.echo(f"Directories skipped: {stats.dirs_skipped}")
    click.echo(f"Tokens used: {stats.tokens_used}")
    click.echo(f"Errors: {len(stats.errors)}")
    _echo_generation_errors(stats)
    _echo_budget_warning(stats, config)


@cli.command()
@click.argument("path", default=".")
@click.option("--provider", default=None, help="LLM provider.")
@click.option("--model", default=None, help="Model name.")
@click.option("--base-url", default=None, help="Base URL for local providers.")
@click.option("--cache-path", default=None, help="Path to LLM disk cache file.")
def watch(path: str, provider: Optional[str], model: Optional[str], base_url: Optional[str], cache_path: Optional[str]) -> None:
    """Watch a directory tree and regenerate manifests on file changes."""
    from ctx.watcher import run_watch
    target_path, config, spec, client, _ = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        base_url=base_url,
        cache_path=cache_path,
    )
    run_watch(target_path, config, client, spec)


@cli.command()
@click.argument("path", default=".", required=False)
def setup(path: str) -> None:
    """Auto-detect LLM provider and write .ctxconfig."""
    target_path = Path(path)
    config_file = target_path / ".ctxconfig"

    if config_file.exists():
        click.echo(f".ctxconfig already exists:\n\n{config_file.read_text(encoding='utf-8')}")
        if not click.confirm("Overwrite?", default=False):
            click.echo("Cancelled.")
            return

    result = detect_provider()
    if result is None:
        raise click.UsageError(
            "No LLM provider detected.\n"
            "  Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or start Ollama / LM Studio first."
        )

    provider, model = result
    base_url = DEFAULT_BASE_URLS.get(provider)
    write_default_config(target_path, provider, model=model, base_url=base_url)

    detected_via = PROVIDER_DETECTED_VIA.get(provider, provider)
    click.echo(f"Detected: {provider} ({detected_via})")
    click.echo(f"Config written to {config_file}")
    click.echo("\nNext step: run `ctx init .` to generate manifests.")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host address for the server.")
@click.option("--port", type=int, default=8000, help="Port for the server.")
def serve(host: str, port: int) -> None:
    """Start the MCP server to expose CONTEXT.md manifests."""
    click.echo(f"Starting ctx MCP server on http://{host}:{port}")
    from ctx.server import start_server
    start_server(host=host, port=port)

