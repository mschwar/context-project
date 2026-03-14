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
from ctx.config import load_config
from ctx.generator import GenerateStats, generate_tree, get_status, update_tree
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

    config = load_config(target_path, **load_config_kwargs)
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


def _display_status_path(path: str) -> str:
    return "." if path == "." else f"./{path}"


@click.group()
@click.version_option(version=__version__, prog_name="ctx")
def cli() -> None:
    """ctx — Filesystem-native context layer for AI agents."""
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio", "bitnet"]), default=None, help="LLM provider.")
@click.option("--model", default=None, help="Model ID override.")
@click.option("--max-depth", type=int, default=None, help="Max directory depth to process.")
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
def init(path: str, provider: Optional[str], model: Optional[str], max_depth: Optional[int], token_budget: Optional[int], base_url: Optional[str]) -> None:
    """Generate CONTEXT.md files for a directory tree.

    Implementation:
        1. load_config(Path(path), provider=provider, model=model, max_depth=max_depth).
        2. load_ignore_patterns(Path(path)).
        3. create_client(config).
        4. Define a progress callback that prints: "  [{done}/{total}] Processing {dir_name}".
        5. click.echo(f"ctx init: generating manifests for {path}").
        6. stats = generate_tree(Path(path), config, client, spec, progress=progress_cb).
        7. Print summary: dirs processed, files processed, tokens used, errors.
    """
    target_path, config, spec, client, progress_cb = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        max_depth=max_depth,
        token_budget=token_budget,
        base_url=base_url,
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


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio", "bitnet"]), default=None)
@click.option("--model", default=None)
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
def update(path: str, provider: Optional[str], model: Optional[str], token_budget: Optional[int], base_url: Optional[str]) -> None:
    """Incrementally refresh stale CONTEXT.md files.

    Implementation:
        1. load_config, load_ignore_patterns, create_client (same as init).
        2. stats = update_tree(Path(path), config, client, spec, progress=progress_cb).
        3. Print summary: dirs refreshed, dirs skipped (fresh), tokens used.
    """
    target_path, config, spec, client, progress_cb = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        token_budget=token_budget,
        base_url=base_url,
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
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio", "bitnet"]), default=None)
@click.option("--model", default=None)
@click.option("--token-budget", type=int, default=None, help="Max total tokens before stopping.")
@click.option("--base-url", default=None, help="Custom API base URL.")
def smart_update(path: str, provider: Optional[str], model: Optional[str], token_budget: Optional[int], base_url: Optional[str]) -> None:
    """Incrementally refresh stale CONTEXT.md files, focusing on git-changed files.
    
    This command first identifies files that have changed in the git repository
    since the last commit (or are staged) and then triggers a regeneration of
    CONTEXT.md files only for the directories affected by these changes and their ancestors.
    """
    from ctx.git import get_changed_files # Import here to avoid circular dependencies if git depends on cli
    
    target_path, config, spec, client, progress_cb = _build_generation_runtime(
        path,
        provider=provider,
        model=model,
        token_budget=token_budget,
        base_url=base_url,
    )

    click.echo(f"ctx smart-update: refreshing manifests for {target_path} based on git changes")
    
    changed_files = get_changed_files(target_path)
    if not changed_files:
        click.echo("No git-changed files detected. Nothing to update.")
        return

    click.echo(f"Detected {len(changed_files)} changed files. Processing affected directories.")
    if config.token_budget:
        click.echo(f"Token budget: {config.token_budget:,}")
    stats = update_tree(target_path, config, client, spec, progress=progress_cb, changed_files=changed_files)
    click.echo(f"Directories refreshed: {stats.dirs_processed}")
    click.echo(f"Directories skipped: {stats.dirs_skipped}")
    click.echo(f"Tokens used: {stats.tokens_used}")
    click.echo(f"Errors: {len(stats.errors)}")
    _echo_generation_errors(stats)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host address for the server.")
@click.option("--port", type=int, default=8000, help="Port for the server.")
def serve(host: str, port: int) -> None:
    """Start the MCP server to expose CONTEXT.md manifests."""
    click.echo(f"Starting ctx MCP server on http://{host}:{port}")
    from ctx.server import start_server
    start_server(host=host, port=port)

