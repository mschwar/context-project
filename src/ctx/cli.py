"""Click CLI entry point for ctx (deterministic zero-LLM structural & blast-radius analyzer).

Commands:
    ctx init [path]       Bootstrap deterministic .ctx/ structural maps.
    ctx uninit [path]     Remove .ctx/ infrastructure and legacy git hooks.
    ctx refresh [path]    Deterministically update .ctx/ structural maps.
    ctx check [path]      Validate .ctx/ freshness, structure, and coverage.
    ctx export [path]     Export .ctx/ maps or fleet capsules for agent ingestion.
    ctx impact <target>   Analyze reverse-dependency blast radius and coupled tests.
    ctx benchmark [paths] Run Phase 27.1 A/B/C agent navigation benchmark.
    ctx reset [path]      Remove legacy per-directory CONTEXT.md files.
    ctx serve [path]      Serve .ctx/ over MCP stdio (--mcp) or HTTP.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time
from typing import Optional

import click

from ctx import __version__, api
from ctx.output import OutputBroker, _classify_exception, build_envelope


def _display_status_path(path: str) -> str:
    return "." if path == "." else f"./{path}"


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
    if broker.handled_exception or broker.errors:
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
    """ctx — Deterministic static AST & import-graph context analyzer for AI agents."""
    ctx.ensure_object(dict)
    resolved_output_mode = output_mode
    if resolved_output_mode is None:
        resolved_output_mode = os.environ.get("CTX_OUTPUT", "human").strip().lower()
    ctx.obj["json_mode"] = resolved_output_mode == "json"


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--force", is_flag=True, help="Reinitialize even if .ctx/ already exists.")
@click.option(
    "--tier2",
    is_flag=True,
    help="Compatibility flag (deterministic .ctx/ structural synthesis is now default).",
)
@_subcommand_output_option
@click.pass_context
def init(
    ctx: click.Context,
    path: str,
    force: bool,
    tier2: bool = False,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Bootstrap deterministic .ctx/ structural maps in a git repository."""
    from ctx.init import InitError, init_project

    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="init", json_mode=json_mode) as broker:
        try:
            result = init_project(Path(path), force=force, tier2=tier2 or True)
        except InitError as exc:
            if json_mode:
                broker.add_error("init_failed", str(exc))
            else:
                click.echo(f"Error: {exc}", err=True)
                sys.exit(1)
        else:
            broker.set_data(result)
            if not json_mode:
                click.echo(f"Initialized ctx in {result['root']}")
                click.echo(f"  .ctx/ created with {len(result['exports'])} exports")
                click.echo(f"  Subsystems mapped: {result['manifests_refreshed']}")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@_subcommand_output_option
@click.pass_context
def uninit(ctx: click.Context, path: str, sub_output_mode: Optional[str] = None) -> None:
    """Remove .ctx/ infrastructure and any legacy ctx git hooks."""
    from ctx.init import InitError, uninit_project

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
                if result["hooks_removed"]:
                    click.echo(f"  Legacy hooks removed: {', '.join(result['hooks_removed'])}")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--force", is_flag=True, help="Regenerate .ctx/ maps even when structural hashes match.")
@click.option("--dry-run", is_flag=True, help="Preview whether .ctx/ maps are stale without writing.")
@click.option("--max-depth", type=int, default=None, help="Maximum directory traversal depth.")
@_subcommand_output_option
@click.pass_context
def refresh(
    ctx: click.Context,
    path: str,
    force: bool,
    dry_run: bool,
    max_depth: Optional[int],
    sub_output_mode: Optional[str] = None,
) -> None:
    """Deterministically generate or update .ctx/ structural maps."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        result = api.refresh(
            Path(path),
            force=force,
            dry_run=dry_run,
            max_depth=max_depth,
        )
        broker.set_data(asdict(result))
        if not json_mode:
            if dry_run:
                if not result.stale_directories:
                    click.echo("All .ctx/ maps are fresh. Nothing to regenerate.")
                else:
                    click.echo(".ctx/ structural maps are stale and would be regenerated.")
                return
            click.echo(f"Subsystems refreshed: {result.dirs_processed}")
            click.echo(f"Subsystems skipped: {result.dirs_skipped}")
            click.echo(f"Files processed: {result.files_processed}")
    _exit_for_broker(broker, json_mode=json_mode)


@cli.command(name="check")
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True), default=".", required=False)
@click.option("--verify", "verify_mode", is_flag=True, help="Validate .ctx/ frontmatter, exports, and freshness.")
@click.option("--stats", "stats_mode", is_flag=True, help="Emit coverage and token summary.")
@click.option("--diff", "diff_mode", is_flag=True, help="Report whether .ctx/CONTEXT.md is stale.")
@click.option("--verbose", "-v", is_flag=True, help="Include per-entry details in --stats output.")
@click.option("--quiet", is_flag=True, help="Exit 1 silently when --diff finds stale maps.")
@click.option("--stat", is_flag=True, help="Summary count only for --diff.")
@click.option("--check-exit", is_flag=True, help="Exit 1 when maps are stale or missing.")
@_subcommand_output_option
@click.pass_context
def check(
    ctx: click.Context,
    path: str,
    verify_mode: bool,
    stats_mode: bool,
    diff_mode: bool,
    verbose: bool,
    quiet: bool,
    stat: bool,
    check_exit: bool,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Check deterministic .ctx/ freshness, coverage, validation, or diffs."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    with OutputBroker(command="check", json_mode=json_mode) as broker:
        result = api.check(
            Path(path),
            verify=verify_mode,
            stats=stats_mode,
            diff=diff_mode,
            verbose=verbose,
            check_exit=check_exit,
            quiet=quiet,
            stat=stat,
        )
        broker.set_data({"mode": result.mode, "directories": result.directories, "summary": result.summary})

        if json_mode:
            summary = result.summary
            if result.mode == "health" and check_exit and (summary.get("stale", 0) > 0 or summary.get("missing", 0) > 0):
                broker.add_error("stale_manifests", "Stale or missing .ctx/ maps detected.")
            if result.mode == "verify" and summary.get("invalid", 0) > 0:
                broker.add_error("invalid_manifests", ".ctx/ verification found invalid or stale maps.")
            if result.mode == "diff" and quiet and summary.get("stale", 0) > 0:
                broker.add_error("stale_manifests", ".ctx/ changes detected.")
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
            stale = sorted(entry["path"] for entry in result.directories if entry["status"] == "stale")
            if quiet:
                if stale:
                    sys.exit(1)
            elif stat:
                click.echo(f"{len(stale)} stale" if stale else "No .ctx/ maps stale.")
            elif stale:
                click.echo(f"{len(stale)} .ctx/ map(s) stale:")
                for file_path in stale:
                    click.echo(f"  [stale] {file_path}")
            else:
                click.echo("No .ctx/ maps stale.")
        else:
            invalid_entries = [entry for entry in result.directories if entry["status"] != "fresh"]
            if invalid_entries:
                for item in invalid_entries:
                    if item["status"] == "invalid_body":
                        click.echo(f"Invalid .ctx/ export ({item['path']}):")
                        for issue in item.get("issues", []):
                            click.echo(f"  - {issue}")
                    else:
                        click.echo(f"{item['status']}: {item['path']}")
                summary = result.summary
                click.echo(f"\nHealth summary: {summary['fresh']} fresh, {summary['stale']} stale, {summary['missing']} missing.")
                sys.exit(1)
            click.echo("All .ctx/ maps are valid, present, and fresh.")
    _exit_for_broker(broker, json_mode=json_mode)


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
    "--filter",
    "filter_mode",
    type=click.Choice(["all", "stale", "missing"]),
    default="all",
    help="Which maps to export: all (default), stale, or missing.",
)
@click.option("--depth", type=int, default=None, help="Export tier depth (0 = CONTEXT-0, 1 = CONTEXT-1, omit = full).")
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
    """Export deterministic .ctx/ structural maps or a fleet capsule."""
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
                    click.echo(f"Exported {n} map{'s' if n != 1 else ''} to {resolved_out_file}")
                elif exp_res.content:
                    click.echo(exp_res.content, nl=False)
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
    """Remove legacy per-directory CONTEXT.md files from the directory tree."""
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
    """Legacy alias for `ctx reset`."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    if not json_mode:
        click.echo("Warning: `ctx clean` is deprecated. Use `ctx reset` instead.", err=True)
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


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--host", default="127.0.0.1", help="Host address for the HTTP server.")
@click.option("--port", type=int, default=8000, help="Port for the HTTP server.")
@click.option("--mcp", is_flag=True, help="Launch stdio MCP server instead of HTTP.")
@click.pass_context
def serve(ctx: click.Context, path: str, host: str, port: int, mcp: bool) -> None:
    """Start the ctx server (HTTP or `--mcp` stdio)."""
    _ = ctx
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
@click.argument("target", required=False, default=None)
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--depth", type=int, default=None, help="Maximum reverse-dependency BFS depth (>= 1).")
@click.option(
    "--git-diff",
    "git_diff",
    default=None,
    help="Compile blast radius & minimal test plan across a git diff (e.g. HEAD, origin/main...HEAD, WORKTREE).",
)
@click.option("--staged", is_flag=True, help="Compile blast radius & minimal test plan across staged git changes.")
@_subcommand_output_option
@click.pass_context
def impact(
    ctx: click.Context,
    target: Optional[str],
    path: str,
    depth: Optional[int],
    git_diff: Optional[str] = None,
    staged: bool = False,
    sub_output_mode: Optional[str] = None,
) -> None:
    """Analyze reverse-dependency blast radius, coupled tests, and governing docs."""
    json_mode = _resolve_json_mode(ctx, sub_output_mode)
    diff_mode = git_diff is not None or staged

    if diff_mode and git_diff is not None and staged:
        raise click.UsageError("Pass either --git-diff or --staged, not both.")

    default_dot = str(Path(".").resolve())
    effective_path_str = path
    if diff_mode:
        if target is not None:
            if path != default_dot:
                raise click.UsageError("Cannot combine a positional <target> with --git-diff or --staged.")
            cand = Path(target)
            if not cand.exists() or not cand.is_dir():
                raise click.UsageError(f"Invalid repository directory path: {target}")
            effective_path_str = str(cand.resolve())
    elif target is None:
        raise click.UsageError("Missing argument 'TARGET' (or pass --git-diff / --staged).")

    with OutputBroker(command="impact", json_mode=json_mode) as broker:
        if diff_mode:
            try:
                diff_res = api.analyze_diff_impact(
                    Path(effective_path_str),
                    git_diff=git_diff,
                    staged=staged,
                    max_depth=depth,
                )
            except ValueError as exc:
                if json_mode:
                    broker.add_error("invalid_target", str(exc))
                else:
                    raise click.ClickException(str(exc)) from exc
                diff_res = None

            if diff_res is not None:
                broker.set_data(asdict(diff_res))
                if not json_mode:
                    click.echo(f"Diff spec: {diff_res.diff_spec}")
                    click.echo(
                        f"Changed files ({len(diff_res.changed_files)}): "
                        f"{', '.join(diff_res.changed_files) if diff_res.changed_files else 'none'}"
                    )
                    click.echo(f"Verification scope: {diff_res.verification_scope}")
                    if diff_res.escalation_reasons:
                        for reason in diff_res.escalation_reasons:
                            click.echo(f"  - escalation: {reason}")
                    if diff_res.recommended_checks:
                        click.echo("Recommended checks:")
                        for cmd_str in diff_res.recommended_checks:
                            click.echo(f"  $ {cmd_str}")
                    click.echo(f"Coupled tests ({len(diff_res.coupled_tests)}):")
                    for test_rec in diff_res.coupled_tests[:15]:
                        dist_part = f", d={test_rec['distance']}" if test_rec.get("distance") is not None else ""
                        click.echo(f"  - {test_rec['path']} ({test_rec['reason']}{dist_part})")
                    if len(diff_res.coupled_tests) > 15:
                        click.echo(f"  ... (+{len(diff_res.coupled_tests) - 15} more)")
                    if diff_res.affected_entrypoints:
                        click.echo(f"Affected entrypoints & surfaces ({len(diff_res.affected_entrypoints)}):")
                        for ep in diff_res.affected_entrypoints[:15]:
                            click.echo(f"  - {ep}")
                    if diff_res.governing_docs:
                        click.echo(f"Governing docs: {', '.join(diff_res.governing_docs)}")
        else:
            assert target is not None
            try:
                result = api.analyze_impact(Path(effective_path_str), target, max_depth=depth)
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
