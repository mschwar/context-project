# AFO Spec 01 — Output Broker

> **Status:** Canonical
> **Stage:** 1 (Structured Output)
> **Prerequisites:** Read 00-conventions.md first
> **Also read:** 04-concurrency.md (atomic writes needed here)

---

## 1. Overview

The OutputBroker is a context manager that intercepts all stdout/stderr output when JSON mode is active. It collects structured data from command execution and emits a single JSON envelope on exit. When JSON mode is not active, it does nothing — existing human-readable output flows unmodified.

---

## 2. New File: `src/ctx/output.py`

### 2.1 OutputBroker Class

```python
@dataclass
class OutputBroker:
    """Context manager that captures command output and emits a JSON envelope.

    Usage:
        with OutputBroker(command="refresh", json_mode=True) as broker:
            broker.set_data({"dirs_processed": 5, ...})
            broker.add_error("partial_failure", "2 directories failed", hint="Retry")
            # Any click.echo / print calls inside this block are suppressed
        # On __exit__, broker emits the JSON envelope to real stdout
    """
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | `str` | required | Canonical command name for the envelope. |
| `json_mode` | `bool` | `False` | When `False`, broker is a no-op passthrough. |

#### Public Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `set_data` | `(data: dict) -> None` | Set the `data` field of the envelope. Can be called multiple times; last call wins. |
| `add_error` | `(code: str, message: str, *, hint: str \| None = None, path: str \| None = None) -> None` | Append an error to the `errors` list. |
| `set_recommended_next` | `(command: str \| None) -> None` | Set the `recommended_next` field. |
| `set_tokens` | `(tokens: int, cost: float) -> None` | Set `metadata.tokens_used` and `metadata.est_cost_usd`. |

#### Internal Behavior

1. **`__enter__`**:
   - Record `start_time = time.time()`.
   - If `json_mode` is `True`:
     - Replace `sys.stdout` with a `StringIO` sink (captures and discards all writes).
     - Replace `sys.stderr` with a `StringIO` sink.
     - Store original `sys.stdout` and `sys.stderr` for later restoration.
   - Return `self`.

2. **`__exit__`**:
   - Compute `elapsed_ms = int((time.time() - start_time) * 1000)`.
   - If `json_mode` is `True`:
     - Restore original `sys.stdout` and `sys.stderr`.
     - Determine `status` from errors:
       - No errors → `"success"`
       - All errors → `"error"`
       - Has both data and errors → `"partial"`
     - Build the envelope dict per 00-conventions.md.
     - Write `json.dumps(envelope)` + `"\n"` to the **real** stdout.
   - If an unhandled exception reached `__exit__` (via `exc_type` parameter):
     - Classify the exception into an error code (see Section 2.2).
     - Add it to `errors`.
     - Set `status` to `"error"`.
     - **Suppress the exception** (return `True`) — the envelope is the only output.
   - Return `True` if json_mode and exception was handled; `False` otherwise.

### 2.2 Exception-to-Error-Code Mapping

```python
def _classify_exception(exc: BaseException) -> tuple[str, str, str | None]:
    """Map an exception to (error_code, message, hint)."""
```

| Exception Type | Error Code | Hint |
|----------------|------------|------|
| `click.UsageError` with "No LLM provider" | `provider_not_configured` | `"Run ctx refresh --setup"` |
| `click.UsageError` with "Missing required environment variable" | `provider_not_configured` | `"Set ANTHROPIC_API_KEY or OPENAI_API_KEY"` |
| `MissingApiKeyError` | `provider_not_configured` | `"Run ctx refresh --setup"` |
| `ConnectionError`, `TimeoutError` | `provider_unreachable` | `"Check network or run ctx setup --check"` |
| `RuntimeError` with `TRANSIENT_ERROR_PREFIX` | `provider_unreachable` | `"Retry the command"` |
| `click.UsageError` (other) | `unknown_error` | `None` |
| Any other `Exception` | `unknown_error` | `None` |

### 2.3 Status Determination Logic

```python
def _determine_status(data: dict, errors: list[dict]) -> str:
    if not errors:
        return "success"
    if not data or data == {}:
        return "error"
    # Has meaningful data AND errors → partial
    return "partial"
```

---

## 3. JSON Mode Detection

### 3.1 Click Group Modification

Add `--output` as a **group-level option** on the Click group in `cli.py`:

```python
@click.group()
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
    """ctx - Filesystem-native context layer for AI agents."""
    ctx.ensure_object(dict)
    # CLI flag > env var > default
    if output_mode is None:
        output_mode = os.environ.get("CTX_OUTPUT", "human").strip().lower()
    ctx.obj["json_mode"] = output_mode == "json"
```

### 3.2 Environment Variable

`CTX_OUTPUT=json` activates JSON mode without the CLI flag. This is the primary agent integration path — agents set the env var once rather than adding `--output json` to every command.

### 3.3 Priority

```
--output json (CLI flag)  >  CTX_OUTPUT=json (env var)  >  default (human)
```

---

## 4. Global Exception Handler

Wrap the Click group's `invoke` method so that **any** unhandled exception in JSON mode is caught and emitted as a valid envelope:

```python
class CtxGroup(click.Group):
    def invoke(self, ctx: click.Context) -> None:
        try:
            super().invoke(ctx)
        except Exception as exc:
            if ctx.obj and ctx.obj.get("json_mode"):
                code, message, hint = _classify_exception(exc)
                envelope = {
                    "status": "error",
                    "command": ctx.invoked_subcommand or "unknown",
                    "metadata": {
                        "version": __version__,
                        "elapsed_ms": 0,
                        "tokens_used": 0,
                        "est_cost_usd": 0.0,
                    },
                    "data": {},
                    "errors": [{"code": code, "message": message, "hint": hint, "path": None}],
                    "recommended_next": None,
                }
                click.echo(json.dumps(envelope))
                ctx.exit(1)
            else:
                raise
```

Replace `@click.group()` with `@click.group(cls=CtxGroup)` in cli.py.

---

## 5. Per-Command `data` Schemas

Each command defines what goes in the `data` field when `--output json` is active. These schemas are the contract agents parse.

### 5.1 `refresh` (replaces init, update, smart-update)

```json
{
  "data": {
    "dirs_processed": 12,
    "dirs_skipped": 6,
    "files_processed": 48,
    "tokens_used": 4800,
    "errors_count": 0,
    "budget_exhausted": false,
    "strategy": "incremental"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `dirs_processed` | `int` | Directories that were regenerated. |
| `dirs_skipped` | `int` | Directories skipped (fresh or budget-limited). |
| `files_processed` | `int` | Total files processed across all directories. |
| `tokens_used` | `int` | Total LLM tokens consumed. |
| `errors_count` | `int` | Number of per-directory errors. |
| `budget_exhausted` | `bool` | Whether the token/USD budget was hit. |
| `strategy` | `string` | `"full"`, `"incremental"`, or `"smart"` (git-scoped). |

### 5.2 `check` (replaces status, verify, stats, diff)

The `data` schema varies based on which check mode is active. A `mode` field disambiguates.

#### Default mode (health check)

```json
{
  "data": {
    "mode": "health",
    "directories": [
      {"path": ".", "status": "fresh"},
      {"path": "src", "status": "stale"},
      {"path": "tests", "status": "missing"}
    ],
    "summary": {
      "total": 18,
      "fresh": 15,
      "stale": 2,
      "missing": 1
    }
  }
}
```

#### `--verify` mode

```json
{
  "data": {
    "mode": "verify",
    "aggregate": {
      "dirs": 18,
      "fresh": 15,
      "stale": 2,
      "missing": 1,
      "invalid": 0
    },
    "malformed": [],
    "missing_fields": [],
    "stale": ["src/ctx"],
    "missing": ["tests/fixtures"]
  }
}
```

#### `--stats` mode

```json
{
  "data": {
    "mode": "stats",
    "aggregate": {
      "dirs": 18,
      "covered": 17,
      "missing": 1,
      "stale": 2,
      "tokens": 48000
    },
    "directories": []
  }
}
```

The `directories` array is populated when `--verbose` is also passed.

#### `--diff` mode

```json
{
  "data": {
    "mode": "diff",
    "modified": ["src/ctx/CONTEXT.md"],
    "new": ["src/ctx/new_module/CONTEXT.md"],
    "stale": []
  }
}
```

`stale` is populated only in the mtime fallback path (no git).

### 5.3 `export`

```json
{
  "data": {
    "manifests_exported": 12,
    "filter": "all",
    "depth": null,
    "content": "# CONTEXT.md\n\n---\n..."
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `manifests_exported` | `int` | Count of manifests included. |
| `filter` | `string` | `"all"`, `"stale"`, or `"missing"`. |
| `depth` | `int \| null` | Depth limit applied, or null for unlimited. |
| `content` | `string` | The concatenated manifest text. |

### 5.4 `reset` (replaces clean)

```json
{
  "data": {
    "manifests_removed": 8,
    "paths": [
      "CONTEXT.md",
      "src/CONTEXT.md",
      "src/ctx/CONTEXT.md"
    ]
  }
}
```

---

## 6. Reconciling `--format json` with `--output json`

Three commands currently have `--format json`: `diff`, `stats`, `verify`.

### Current Behavior (preserved in human mode)

```bash
ctx diff . --format json
# Emits bare JSON: {"modified": [...], "new": [...]}
```

### New Behavior with `--output json`

```bash
ctx check . --diff --output json
# Emits full envelope with data.mode = "diff"
```

### Precedence Rules

1. When `--output json` is active, `--format json` is ignored. The envelope wraps everything.
2. When `--output json` is NOT active, `--format json` works as before (bare JSON, no envelope).
3. `--format json` becomes a hidden flag on the aliased old commands. It is not exposed on the new `check` command.
4. No command ever emits both a bare JSON blob AND an envelope.

---

## 7. OutputBroker Integration Points in `cli.py`

Every command function wraps its body in a `with OutputBroker(...)` block:

```python
@cli.command()
@click.pass_context
def refresh(ctx, path, ...):
    json_mode = ctx.obj.get("json_mode", False)
    with OutputBroker(command="refresh", json_mode=json_mode) as broker:
        # ... existing logic ...
        # At the end:
        broker.set_data({
            "dirs_processed": stats.dirs_processed,
            "dirs_skipped": stats.dirs_skipped,
            # ...
        })
        broker.set_tokens(stats.tokens_used, cost)
```

### Progress Callback Suppression

The `_progress_callback` function in cli.py must check for JSON mode:

```python
def _progress_callback(state: ProgressState, json_mode: bool = False):
    def callback(current_dir, done, total, tokens_used):
        if json_mode:
            # Still accumulate state, just don't print
            state.tokens_accumulated = tokens_used
            return
        # ... existing echo logic ...
    return callback
```

### Enumeration of Output Paths to Intercept

These are all the `click.echo` calls in cli.py that must be suppressed in JSON mode (the OutputBroker's stdout replacement handles this automatically, but this list exists for verification):

| Line(s) | Command | Output |
|---------|---------|--------|
| 310 | `init` | `"ctx init: generating manifests for..."` |
| 312-314 | `init` | Mode and budget messages |
| 319-323 | `init` | Stats lines |
| 347, 363-371 | `update` | Progress and stats |
| 399-407 | `status` | Health table |
| 454-466 | `smart_update` | Progress and stats |
| 499-534 | `setup` | Provider detection output |
| 582-685 | `diff` | Diff results |
| 754-756 | `export` | Export confirmation |
| 815-827 | `stats` | Stats table |
| 849-866 | `clean` | Clean confirmation and results |
| 960-987 | `verify` | Verification results |
| 1005-1007 | `serve` | Server startup messages |

The OutputBroker's `sys.stdout` replacement captures all of these. No per-line changes needed — the broker handles it at the stream level.

---

## 8. Files

### New

| File | Description |
|------|-------------|
| `src/ctx/output.py` | `OutputBroker` class, `_classify_exception`, `_determine_status` |
| `tests/test_output.py` | Unit tests for OutputBroker |

### Modified

| File | Changes |
|------|---------|
| `src/ctx/cli.py` | Add `--output` group option, `CtxGroup` class, wrap each command in `OutputBroker`, modify `_progress_callback` |

---

## 9. Test Cases for `test_output.py`

1. **Passthrough in human mode**: `OutputBroker(json_mode=False)` does not intercept stdout.
2. **Captures stdout in JSON mode**: `click.echo("hello")` inside broker does not appear in real stdout.
3. **Emits valid envelope**: After exit, real stdout contains one line of valid JSON matching the envelope schema.
4. **Success status when no errors**: Empty error list → `status: "success"`.
5. **Error status when errors present and no data**: Error added, no data set → `status: "error"`.
6. **Partial status**: Both data and errors present → `status: "partial"`.
7. **Exception handling**: Unhandled `click.UsageError` → envelope with `provider_not_configured`, exception suppressed.
8. **Exception handling — generic**: Unhandled `RuntimeError` → envelope with `unknown_error`.
9. **Metadata fields**: `elapsed_ms` > 0, `version` matches `__version__`.
10. **set_tokens**: `tokens_used` and `est_cost_usd` appear in metadata.
11. **Multiple errors**: Two `add_error` calls → two entries in `errors` array.
12. **recommended_next**: `set_recommended_next("ctx check .")` → field appears in envelope.
