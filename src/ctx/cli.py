"""Click CLI entry point for ctx.

Commands:
    ctx init <path>     Generate CONTEXT.md files for a directory tree.
    ctx update <path>   Incrementally refresh stale CONTEXT.md files.
    ctx status [path]   Show manifest health across a directory tree.
    ctx diff [path]     Show which CONTEXT.md files changed since last generation.
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
from ctx.llm import TRANSIENT_ERROR_PREFIX
from ctx.generator import GenerateStats, check_stale_dirs, generate_tree, get_status, update_tree
from ctx.ignore import load_ignore_patterns, should_ignore
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
    if any(TRANSIENT_ERROR_PREFIX in e for e in stats.errors):
        click.echo(
            "Tip: transient errors may resolve on retry. Run the command again.",
            err=True,
        )


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
@click.option("--overwrite/--no-overwrite", default=True, help="Regenerate all manifests (default) or skip already-fresh ones.")
def init(path: str, provider: Optional[str], model: Optional[str], max_depth: Optional[int], token_budget: Optional[int], base_url: Optional[str], cache_path: Optional[str], overwrite: bool) -> None:
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
    if not overwrite:
        click.echo("Mode: incremental (skipping fresh manifests)")
    if config.token_budget:
        click.echo(f"Token budget: {config.token_budget:,}")
    if overwrite:
        stats = generate_tree(target_path, config, client, spec, progress=progress_cb)
    else:
        stats = update_tree(target_path, config, client, spec, progress=progress_cb)
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
@click.option("--check", "check_only", is_flag=True, help="Print detected provider without writing config.")
def setup(path: str, check_only: bool) -> None:
    """Auto-detect LLM provider and write .ctxconfig."""
    target_path = Path(path)
    config_file = target_path / ".ctxconfig"

    def _probe_msg(provider: str) -> None:
        label = {"ollama": "Ollama", "lmstudio": "LM Studio"}.get(provider, provider)
        click.echo(f"Probing {label}...")

    if not check_only and config_file.exists():
        click.echo(f".ctxconfig already exists:\n\n{config_file.read_text(encoding='utf-8')}")
        if not click.confirm("Overwrite?", default=False):
            click.echo("Cancelled.")
            return

    result = detect_provider(_probe_callback=_probe_msg)
    if result is None:
        raise click.UsageError(
            "No LLM provider detected.\n"
            "  Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or start Ollama / LM Studio first."
        )

    provider, model = result
    detected_via = PROVIDER_DETECTED_VIA.get(provider, provider)
    click.echo(f"Detected: {provider} ({detected_via})")

    if check_only:
        return

    base_url = DEFAULT_BASE_URLS.get(provider)
    write_default_config(target_path, provider, model=model, base_url=base_url)
    click.echo(f"Config written to {config_file}")
    click.echo("\nNext step: run `ctx init .` to generate manifests.")


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--since", default=None, help="Git ref (branch, commit, tag) to diff against. Defaults to HEAD.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format.")
@click.option("--quiet", is_flag=True, help="Exit code only: exit 1 if changes, exit 0 if clean. No stdout.")
def diff(path: str, since: Optional[str], output_format: str, quiet: bool) -> None:
    """Show CONTEXT.md files that changed since the last generation run.

    Uses git when available; falls back to mtime comparison when outside a
    git repository.

    Output labels:
      [mod]   — manifest modified (git path)
      [new]   — manifest untracked/new (git path)
      [stale] — manifest older than source files (mtime fallback path)
    """
    import json
    import subprocess
    import sys

    target_path = Path(path)
    ref = since or "HEAD"

    # --- git path ---
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref, "--", "*/CONTEXT.md", "CONTEXT.md"],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            check=True,
        )
        changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "*/CONTEXT.md", "CONTEXT.md"],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            check=True,
        )
        new_files = [line.strip() for line in untracked.stdout.splitlines() if line.strip()]
        new_files_set = set(new_files)
        modified_files = sorted(f for f in changed if f not in new_files_set)
        new_files_sorted = sorted(new_files_set)
        all_changed = sorted(set(changed) | new_files_set)
        label = f"since {ref}"

        if quiet:
            if all_changed:
                sys.exit(1)
            return

        if output_format == "json":
            click.echo(json.dumps({"modified": modified_files, "new": new_files_sorted}))
            return

        if not all_changed:
            click.echo(f"No CONTEXT.md files changed {label}.")
            return
        click.echo(f"{len(all_changed)} CONTEXT.md file{'s' if len(all_changed) != 1 else ''} changed {label}:")
        for f in all_changed:
            prefix = "new" if f in new_files_set else "mod"
            click.echo(f"  [{prefix}] {f}")
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        if since is not None:
            raise click.UsageError("--since requires git to be available and the path to be inside a git repository.")
        else:
            click.echo("Warning: git not available or command failed. Falling back to mtime comparison.", err=True)

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

    if quiet:
        if stale:
            sys.exit(1)
        return

    if output_format == "json":
        click.echo(json.dumps({"stale": stale}))
        return

    if not stale:
        click.echo("No CONTEXT.md files appear stale (mtime check).")
        return
    click.echo(f"{len(stale)} CONTEXT.md file{'s' if len(stale) != 1 else ''} may be stale (mtime check):")
    for f in stale:
        click.echo(f"  [stale] {f}")


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
def export(path: str, output: Optional[str], filter_mode: str, depth: Optional[int]) -> None:
    """Concatenate all CONTEXT.md files to stdout or a file.

    Each manifest is prefixed with a header line:
        # path/to/CONTEXT.md
    """
    import os

    root = Path(path).resolve()

    if filter_mode == "missing":
        # Walk the tree and list directories that lack a CONTEXT.md
        spec = load_ignore_patterns(root)
        missing_dirs: list[str] = []
        for dirpath, dirnames, _ in os.walk(root):
            d = Path(dirpath)
            dirnames[:] = [
                dn for dn in sorted(dirnames)
                if not should_ignore(d / dn, spec, root)
            ]
            if not (d / "CONTEXT.md").exists():
                try:
                    rel = d.relative_to(root).as_posix()
                except ValueError:
                    rel = d.as_posix()
                rel_display = rel if rel != "." else ""
                dir_label = (rel_display + "/") if rel_display else "./"
                missing_dirs.append(dir_label)
        content = "\n".join(f"# {missing_dir} [MISSING]" for missing_dir in missing_dirs)
        if output:
            Path(output).write_text(content, encoding="utf-8")
            click.echo(f"Exported {len(missing_dirs)} missing director{'y' if len(missing_dirs) == 1 else 'ies'} to {output}")
        else:
            if content:
                click.echo(content, nl=False)
        return

    files = sorted(root.rglob("CONTEXT.md"))

    # Apply depth filter
    if depth is not None:
        files = [f for f in files if len(f.relative_to(root).parts) - 1 <= depth]

    if filter_mode == "stale":
        stale_files = []
        for f in files:
            try:
                manifest_mtime = f.stat().st_mtime
                is_stale = any(
                    src.stat().st_mtime > manifest_mtime
                    for src in f.parent.iterdir()
                    if src.is_file() and src.name != "CONTEXT.md"
                )
                if is_stale:
                    stale_files.append(f)
            except OSError:
                pass
        files = stale_files

    parts = []
    for f in files:
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            rel = f.as_posix()
        parts.append(f"# {rel}\n\n{f.read_text(encoding='utf-8')}")

    content = "\n\n".join(parts)

    if output:
        Path(output).write_text(content, encoding="utf-8")
        click.echo(f"Exported {len(files)} manifest{'s' if len(files) != 1 else ''} to {output}")
    else:
        click.echo(content, nl=False)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="Show per-directory breakdown table.")
def stats(path: str, verbose: bool) -> None:
    """Show coverage summary across all directories.

    Reports:
      dirs        — total directories found (respects .ctxignore)
      covered     — directories with a CONTEXT.md
      missing     — directories without a CONTEXT.md
      stale       — directories whose CONTEXT.md is older than a source file
      tokens      — sum of tokens_total from all manifest frontmatters
    """
    import os
    import re as _re

    root = Path(path).resolve()
    spec = load_ignore_patterns(root)

    dirs_total = 0
    dirs_covered = 0
    dirs_missing = 0
    dirs_stale = 0
    tokens_total = 0

    _tokens_re = _re.compile(r"^tokens_total:\s*(\d+)", _re.MULTILINE)

    # Per-directory rows for --verbose
    dir_rows: list[tuple[str, str, Optional[int]]] = []  # (rel_path, status, tokens)

    for dirpath, dirnames, _ in os.walk(root):
        d = Path(dirpath)
        # Prune ignored subdirectories in-place to avoid descending into them
        dirnames[:] = [
            dn for dn in sorted(dirnames)
            if not should_ignore(d / dn, spec, root)
        ]

        dirs_total += 1
        manifest = d / "CONTEXT.md"

        try:
            rel = d.relative_to(root).as_posix()
        except ValueError:
            rel = d.as_posix()

        if not manifest.exists():
            dirs_missing += 1
            if verbose:
                dir_rows.append((rel, "missing", None))
        else:
            dirs_covered += 1
            dir_tokens: Optional[int] = None
            try:
                text = manifest.read_text(encoding="utf-8")
                m = _tokens_re.search(text)
                if m:
                    dir_tokens = int(m.group(1))
                    tokens_total += dir_tokens
            except (OSError, UnicodeDecodeError):
                pass
            is_stale_dir = False
            try:
                manifest_mtime = manifest.stat().st_mtime
                is_stale_dir = any(
                    f.stat().st_mtime > manifest_mtime
                    for f in d.iterdir()
                    if f.is_file() and f.name != "CONTEXT.md"
                )
                if is_stale_dir:
                    dirs_stale += 1
            except OSError:
                pass
            if verbose:
                status = "stale" if is_stale_dir else "covered"
                dir_rows.append((rel, status, dir_tokens))

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


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def clean(path: str, yes: bool) -> None:
    """Remove all CONTEXT.md files from the directory tree."""
    root = Path(path).resolve()
    manifests = sorted(root.rglob("CONTEXT.md"))

    if not manifests:
        click.echo("No CONTEXT.md files found.")
        return

    if not yes:
        confirmed = click.confirm(
            f"Found {len(manifests)} CONTEXT.md file(s). Delete all?", default=False
        )
        if not confirmed:
            click.echo("Aborted.")
            return

    for m in manifests:
        m.unlink()

    click.echo(f"Removed {len(manifests)} CONTEXT.md file(s).")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host address for the server.")
@click.option("--port", type=int, default=8000, help="Port for the server.")
def serve(host: str, port: int) -> None:
    """Start the MCP server to expose CONTEXT.md manifests."""
    click.echo(f"Starting ctx MCP server on http://{host}:{port}")
    from ctx.server import start_server
    start_server(host=host, port=port)

