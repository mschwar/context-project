"""Click CLI entry point for ctx.

Commands:
    ctx init <path>     Generate CONTEXT.md files for a directory tree.
    ctx update <path>   Incrementally refresh stale CONTEXT.md files.
    ctx status [path]   Show manifest health across a directory tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from ctx import __version__


@click.group()
@click.version_option(version=__version__, prog_name="ctx")
def cli() -> None:
    """ctx — Filesystem-native context layer for AI agents."""
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), default=None, help="LLM provider.")
@click.option("--model", default=None, help="Model ID override.")
@click.option("--max-depth", type=int, default=None, help="Max directory depth to process.")
def init(path: str, provider: Optional[str], model: Optional[str], max_depth: Optional[int]) -> None:
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
    raise NotImplementedError


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), default=None)
@click.option("--model", default=None)
def update(path: str, provider: Optional[str], model: Optional[str]) -> None:
    """Incrementally refresh stale CONTEXT.md files.

    Implementation:
        1. load_config, load_ignore_patterns, create_client (same as init).
        2. stats = update_tree(Path(path), config, client, spec, progress=progress_cb).
        3. Print summary: dirs refreshed, dirs skipped (fresh), tokens used.
    """
    raise NotImplementedError


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".")
def status(path: str) -> None:
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
    """
    raise NotImplementedError
