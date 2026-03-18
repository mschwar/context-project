# AFO Spec 02 — Unified API

> **Status:** Canonical
> **Stage:** 2 (Unified API)
> **Prerequisites:** Read 00-conventions.md, 01-output-broker.md, 04-concurrency.md

---

## 1. Overview

Collapse 12 CLI commands into 4 canonical commands (`refresh`, `check`, `export`, `reset`) backed by a new `api.py` module. The CLI becomes a thin adapter between Click and the API layer. Agents interact with 4 commands; humans can still use old names via hidden aliases.

---

## 2. New File: `src/ctx/api.py`

### 2.1 Module Structure

```python
"""Unified API layer for ctx.

Four public functions — one per canonical command.
Each returns a typed dataclass. No Click dependency, no stdout.
CLI and MCP server both call these functions.
"""
```

The API layer has **zero** dependency on Click. It never prints. It never calls `sys.exit`. It returns data or raises exceptions.

### 2.2 Result Dataclasses

```python
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

@dataclass
class CheckResult:
    """Result of a health check."""
    mode: str  # "health", "verify", "stats", "diff"
    directories: list[dict]  # varies by mode
    summary: dict            # aggregate counts

@dataclass
class ExportResult:
    """Result of an export operation."""
    manifests_exported: int
    filter: str    # "all", "stale", "missing"
    depth: int | None
    content: str

@dataclass
class ResetResult:
    """Result of a reset (clean) operation."""
    manifests_removed: int
    paths: list[str]
```

### 2.3 API Functions

#### `refresh()`

```python
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
```

**Strategy decision tree** (this is the critical logic):

```
Is --setup passed?
├── Yes: run auto-config first (detect_provider + write_default_config), then continue as normal refresh
│
Is --watch passed?
├── Yes: run one refresh cycle, then enter watch loop (never returns until Ctrl+C)
│
Is --dry-run passed?
├── Yes: run check_stale_dirs(), return result without LLM calls
│
Is --force passed?
├── Yes: strategy = "full" → call generate_tree() (regenerate everything)
│
Are there CONTEXT.md files in the tree?
├── No: strategy = "full" → call generate_tree() (first run, same as old `ctx init`)
│
Is git available and are there changed files?
├── Yes: strategy = "smart" → call update_tree(changed_files=...) (same as old `ctx smart-update`)
│
Default:
└── strategy = "incremental" → call update_tree() (same as old `ctx update`)
```

**Key rule**: `--setup` and `--watch` are mutually exclusive. If both are passed, raise `ValueError`.

**Functions to reuse from generator.py** (do NOT reimplement):
- `generate_tree()` — full regeneration
- `update_tree()` — incremental regeneration
- `check_stale_dirs()` — dry-run directory list
- `inspect_directory_health()` — health reporting

**Functions to reuse from cli.py** (move to api.py or shared location):
- `_build_generation_runtime()` — config loading + client creation
- `_estimate_cost()` — cost calculation (move to shared location, see 03-config-and-bootstrap.md)

#### `check()`

```python
def check(
    root: Path,
    *,
    verify: bool = False,
    stats: bool = False,
    diff: bool = False,
    verbose: bool = False,
    since: str | None = None,
    check_exit: bool = False,
) -> CheckResult:
```

**Mode selection**:
- Default (no flags): health check → `mode = "health"`
- `--verify`: full validation → `mode = "verify"`
- `--stats`: coverage summary → `mode = "stats"`
- `--diff`: changed manifests → `mode = "diff"`
- Only one mode flag at a time. If multiple are passed, raise `ValueError`.

**This function does not call any LLM**. It is always read-only.

#### `export_context()`

```python
def export_context(
    root: Path,
    *,
    output_file: str | None = None,
    filter_mode: str = "all",
    depth: int | None = None,
) -> ExportResult:
```

Named `export_context` to avoid shadowing Python's built-in `export`. Maps directly to the existing `export` command logic.

#### `reset()`

```python
def reset(
    root: Path,
    *,
    dry_run: bool = False,
    yes: bool = False,
) -> ResetResult:
```

**JSON mode interaction**: When called programmatically (from MCP or with `--output json`), `yes` defaults to `True` — agents never confirm interactively. The CLI layer sets `yes=True` when JSON mode is active. See 03-config-and-bootstrap.md for prompt elimination details.

---

## 3. Command Collapse Mapping

### Full Mapping Table

| Old Command | Old Flags | New Command | New Flags | Notes |
|-------------|-----------|-------------|-----------|-------|
| `ctx init .` | — | `ctx refresh .` | `--force` | Full regeneration |
| `ctx init . --no-overwrite` | `--no-overwrite` | `ctx refresh .` | — | Incremental (default) |
| `ctx init . --overwrite` | `--overwrite` (default) | `ctx refresh .` | `--force` | Explicit full regen |
| `ctx update .` | — | `ctx refresh .` | — | Incremental |
| `ctx update . --dry-run` | `--dry-run` | `ctx refresh .` | `--dry-run` | Preview mode |
| `ctx smart-update .` | — | `ctx refresh .` | — | Auto-detects git changes |
| `ctx smart-update . --dry-run` | `--dry-run` | `ctx refresh . --dry-run` | — | Preview with git scope |
| `ctx status .` | — | `ctx check .` | — | Default health mode |
| `ctx status . --check-exit-code` | `--check-exit-code` | `ctx check .` | `--check-exit` | Exit 1 on stale/missing |
| `ctx verify .` | — | `ctx check .` | `--verify` | Full validation |
| `ctx verify . --format json` | `--format json` | `ctx check . --verify --output json` | — | Wrapped in envelope |
| `ctx stats .` | — | `ctx check .` | `--stats` | Coverage summary |
| `ctx stats . --verbose` | `--verbose` | `ctx check . --stats --verbose` | — | Per-directory breakdown |
| `ctx stats . --format json` | `--format json` | `ctx check . --stats --output json` | — | Wrapped in envelope |
| `ctx diff .` | — | `ctx check .` | `--diff` | Changed manifests |
| `ctx diff . --since ref` | `--since` | `ctx check . --diff --since ref` | — | Git ref comparison |
| `ctx diff . --quiet` | `--quiet` | `ctx check . --diff --quiet` | — | Exit code only |
| `ctx diff . --stat` | `--stat` | `ctx check . --diff --stat` | — | Summary count only |
| `ctx diff . --format json` | `--format json` | `ctx check . --diff --output json` | — | Wrapped in envelope |
| `ctx export .` | — | `ctx export .` | — | Unchanged command name |
| `ctx export . --filter stale` | `--filter` | `ctx export . --filter stale` | — | Unchanged |
| `ctx export . --depth N` | `--depth` | `ctx export . --depth N` | — | Unchanged |
| `ctx clean .` | — | `ctx reset .` | — | Requires `--yes` or interactive confirm |
| `ctx clean . --yes` | `--yes` | `ctx reset . --yes` | — | Skip confirmation |
| `ctx clean . --dry-run` | `--dry-run` | `ctx reset . --dry-run` | — | Preview mode |
| `ctx setup` | — | `ctx refresh . --setup` | — | Auto-detect + write config |
| `ctx setup --check` | `--check` | `ctx refresh . --setup --dry-run` | — | Detect only, don't write |
| `ctx watch .` | — | `ctx refresh . --watch` | — | Watch mode |

### Flag Mutual Exclusivity

| Flag Combination | Behavior |
|-----------------|----------|
| `--force` + `--watch` | Allowed: first run is full regen, then watch |
| `--setup` + `--watch` | **Error**: cannot auto-config and watch simultaneously |
| `--setup` + `--force` | Allowed: auto-config then full regen |
| `--dry-run` + `--watch` | **Error**: dry-run and watch are incompatible |
| `--dry-run` + `--force` | Allowed: shows what full regen would touch |
| `--verify` + `--stats` | **Error**: pick one check mode |
| `--verify` + `--diff` | **Error**: pick one check mode |
| `--stats` + `--diff` | **Error**: pick one check mode |

---

## 4. New CLI Structure in `cli.py`

### 4.1 Canonical Commands

```python
@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--force", is_flag=True, help="Regenerate all manifests, even fresh ones.")
@click.option("--setup", is_flag=True, help="Auto-detect provider and write .ctxconfig first.")
@click.option("--watch", is_flag=True, help="After refresh, watch for changes and re-refresh.")
@click.option("--dry-run", is_flag=True, help="Preview what would be regenerated.")
@click.option("--provider", type=click.Choice(["anthropic", "openai", "ollama", "lmstudio"]), default=None)
@click.option("--model", default=None)
@click.option("--max-depth", type=int, default=None)
@click.option("--token-budget", type=int, default=None)
@click.option("--base-url", default=None)
@click.option("--cache-path", default=None)
@click.pass_context
def refresh(ctx, path, force, setup, watch, dry_run, ...):
    """Generate or update CONTEXT.md manifests."""
    json_mode = ctx.obj.get("json_mode", False)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        result = api.refresh(Path(path), force=force, setup=setup, ...)
        broker.set_data(asdict(result))  # or a dict comprehension
        broker.set_tokens(result.tokens_used, result.est_cost_usd)
        if result.errors:
            for error in result.errors:
                broker.add_error("partial_failure", error)
        if not json_mode:
            # Print human-readable output
            _echo_refresh_result(result)


@cli.command()
@click.argument("path", ...)
@click.option("--verify", is_flag=True)
@click.option("--stats", is_flag=True)
@click.option("--diff", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
@click.option("--since", default=None)
@click.option("--quiet", is_flag=True)
@click.option("--stat", is_flag=True)
@click.option("--check-exit", is_flag=True)
@click.pass_context
def check(ctx, path, verify, stats, diff, ...):
    """Check manifest health, coverage, or changes."""
    ...


@cli.command()
@click.argument("path", ...)
@click.option("--output-file", "-o", default=None)
@click.option("--filter", "filter_mode", ...)
@click.option("--depth", type=int, default=None)
@click.pass_context
def export(ctx, path, output_file, filter_mode, depth):
    """Export CONTEXT.md manifests to stdout or a file."""
    ...


@cli.command()
@click.argument("path", ...)
@click.option("--yes", "-y", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def reset(ctx, path, yes, dry_run):
    """Remove all CONTEXT.md files from the tree."""
    ...
```

### 4.2 The `serve` Command

`serve` stays as a separate top-level command (not collapsed). It gets `--mcp` flag in Stage 5 (see 05-mcp-server.md).

```python
@cli.command()
@click.argument("path", default=".", ...)
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8000)
@click.option("--mcp", is_flag=True, help="Launch stdio MCP server instead of HTTP.")
def serve(path, host, port, mcp):
    ...
```

### 4.3 Hidden Aliases

Each old command becomes a hidden Click command that delegates to the canonical one:

```python
@cli.command(hidden=True, deprecated=True)
@click.argument("path", ...)
@click.option("--overwrite/--no-overwrite", default=True)
@click.option("--provider", ...)
# ... all original flags ...
@click.pass_context
def init(ctx, path, overwrite, provider, model, ...):
    """Deprecated: use `ctx refresh` instead."""
    json_mode = ctx.obj.get("json_mode", False)
    if not json_mode:
        click.echo("Warning: 'ctx init' is deprecated. Use 'ctx refresh' instead.", err=True)
    # Delegate to refresh
    ctx.invoke(refresh, path=path, force=overwrite, provider=provider, model=model, ...)
```

**Important**: The alias preserves the **exact same flag interface** as the original command. Users' existing scripts continue to work.

---

## 5. CLI Size Reduction

### Current State

`cli.py` is ~1008 lines. The bulk is:
- `_build_generation_runtime` and helper functions (~200 lines)
- 12 command functions with inline logic (~700 lines)
- Pricing/cost functions (~50 lines)

### Target State

After Stage 2, `cli.py` should be ~400-500 lines:
- 4 canonical command functions (thin adapters to `api.py`) (~150 lines)
- Hidden aliases (thin delegators) (~150 lines)
- Click group + global options (~30 lines)
- Human-mode rendering helpers (~100 lines)

### What Moves Where

| Code | From | To |
|------|------|----|
| `_build_generation_runtime` | `cli.py` | `api.py` (internal) |
| `_estimate_cost`, `_PRICING_DATA` | `cli.py` | Shared location (see 03-config-and-bootstrap.md) |
| Strategy decision tree | N/A (new) | `api.py` → `refresh()` |
| Health check logic | `status`, `verify`, `stats`, `diff` commands | `api.py` → `check()` |
| Export logic | `export` command | `api.py` → `export_context()` |
| Clean logic | `clean` command | `api.py` → `reset()` |
| `_echo_*` helpers | `cli.py` | Stay in `cli.py` (human-mode rendering) |
| `ProgressState`, `_progress_callback` | `cli.py` | Stay in `cli.py` (human-mode concern) |

---

## 6. Files

### New

| File | Description |
|------|-------------|
| `src/ctx/api.py` | 4 API functions + result dataclasses |
| `tests/test_api.py` | Unit tests for all API functions |
| `tests/test_cli_compat.py` | Hidden alias regression tests |

### Modified

| File | Changes |
|------|---------|
| `src/ctx/cli.py` | Major restructure: 4 canonical commands, hidden aliases, delegates to `api.py` |

---

## 7. Test Cases

### `test_api.py`

1. **refresh — full strategy**: No existing manifests → strategy is `"full"`, calls `generate_tree`.
2. **refresh — incremental strategy**: Existing manifests → strategy is `"incremental"`, calls `update_tree`.
3. **refresh — smart strategy**: Git available + changed files → strategy is `"smart"`, calls `update_tree` with `changed_files`.
4. **refresh — force**: `force=True` → always `"full"`, even with existing manifests.
5. **refresh — setup**: `setup=True` → calls `detect_provider` + `write_default_config` before refresh.
6. **refresh — dry run**: `dry_run=True` → returns stale dir list, no LLM calls.
7. **refresh — setup + watch error**: Both flags → `ValueError`.
8. **check — health mode**: Returns directory list with statuses.
9. **check — verify mode**: Returns malformed/missing/stale/invalid.
10. **check — stats mode**: Returns aggregate counts.
11. **check — diff mode**: Returns modified/new/stale lists.
12. **check — mutual exclusivity**: `verify=True, stats=True` → `ValueError`.
13. **export — all**: Returns all manifests concatenated.
14. **export — filter stale**: Returns only stale manifests.
15. **export — depth**: Respects depth limit.
16. **reset — basic**: Removes manifests, returns count and paths.
17. **reset — dry run**: Lists but doesn't remove.

### `test_cli_compat.py`

1. **init → refresh --force**: `ctx init .` produces same result as `ctx refresh . --force`.
2. **init --no-overwrite → refresh**: `ctx init . --no-overwrite` same as `ctx refresh .`.
3. **update → refresh**: `ctx update .` same as `ctx refresh .`.
4. **smart-update → refresh**: `ctx smart-update .` same as `ctx refresh .` (with git).
5. **status → check**: `ctx status .` same as `ctx check .`.
6. **verify → check --verify**: `ctx verify .` same as `ctx check . --verify`.
7. **stats → check --stats**: `ctx stats .` same as `ctx check . --stats`.
8. **diff → check --diff**: `ctx diff .` same as `ctx check . --diff`.
9. **clean → reset**: `ctx clean . --yes` same as `ctx reset . --yes`.
10. **Deprecation warning in human mode**: Old command prints warning to stderr.
11. **No deprecation in JSON mode**: Old command with `--output json` has no warning in output.
12. **Flag passthrough**: All original flags on old commands are forwarded correctly.
