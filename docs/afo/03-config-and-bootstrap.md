# AFO Spec 03 — Config & Bootstrap

> **Status:** Canonical
> **Stage:** 3 (Non-Interactive)
> **Prerequisites:** Read 00-conventions.md, 02-unified-api.md

---

## 1. Overview

Make ctx fully configurable without interactive prompts. Every config field gets an env var. Budget guardrails prevent runaway costs. Auto-config eliminates the `ctx setup` ceremony for agents.

---

## 2. Environment Variable Parity Table

Every `.ctxconfig` field must have a corresponding `CTX_*` environment variable. Agents set env vars; humans edit files. Both paths produce identical behavior.

### Complete Parity Table

| `.ctxconfig` Field | Env Var | Type | Default | Notes |
|--------------------|---------|------|---------|-------|
| `provider` | `CTX_PROVIDER` | `string` | `"anthropic"` | Already exists |
| `model` | `CTX_MODEL` | `string` | provider-specific | Already exists |
| `base_url` | `CTX_BASE_URL` | `string` | `null` | **New env var** |
| `max_file_tokens` | `CTX_MAX_FILE_TOKENS` | `int` | `8000` | **New env var** |
| `max_depth` | `CTX_MAX_DEPTH` | `int \| null` | `null` | **New env var** |
| `token_budget` | `CTX_TOKEN_BUDGET` | `int \| null` | `null` | **New env var** |
| `batch_size` | `CTX_BATCH_SIZE` | `int \| null` | `null` | **New env var** |
| `cache_path` | `CTX_CACHE_PATH` | `string` | `.ctx-cache/llm_cache.json` | **New env var** |
| `max_cache_entries` | `CTX_MAX_CACHE_ENTRIES` | `int` | `10000` | **New env var** |
| `watch_debounce_seconds` | `CTX_WATCH_DEBOUNCE` | `float` | `0.5` | **New env var** |
| `max_tokens_per_run` | `CTX_MAX_TOKENS_PER_RUN` | `int \| null` | `null` | **New field + env var** |
| `max_usd_per_run` | `CTX_MAX_USD_PER_RUN` | `float \| null` | `null` | **New field + env var** |
| `extensions` | `CTX_EXTENSIONS` | `string` (comma-separated) | `null` | **New env var** |

### Resolution Order (unchanged, now with more env vars)

```
CLI flag  >  Environment variable  >  .ctxconfig file  >  Built-in default
```

### Implementation in `config.py`

Add env var lookups **between** the `.ctxconfig` overlay and the CLI flag overlay in `load_config`:

```python
# After .ctxconfig loading, before CLI flag application:

# New env var lookups
env_base_url = os.getenv("CTX_BASE_URL")
if env_base_url:
    config.base_url = env_base_url.strip()

env_max_file_tokens = os.getenv("CTX_MAX_FILE_TOKENS")
if env_max_file_tokens:
    config.max_file_tokens = int(env_max_file_tokens)

env_max_depth = os.getenv("CTX_MAX_DEPTH")
if env_max_depth:
    config.max_depth = None if env_max_depth.strip().lower() == "none" else int(env_max_depth)

env_token_budget = os.getenv("CTX_TOKEN_BUDGET")
if env_token_budget:
    config.token_budget = None if env_token_budget.strip().lower() == "none" else int(env_token_budget)

env_batch_size = os.getenv("CTX_BATCH_SIZE")
if env_batch_size:
    config.batch_size = None if env_batch_size.strip().lower() == "none" else int(env_batch_size)

env_cache_path = os.getenv("CTX_CACHE_PATH")
if env_cache_path is not None:  # Note: empty string = disable cache
    config.cache_path = env_cache_path

env_max_cache = os.getenv("CTX_MAX_CACHE_ENTRIES")
if env_max_cache:
    config.max_cache_entries = int(env_max_cache)

env_debounce = os.getenv("CTX_WATCH_DEBOUNCE")
if env_debounce:
    config.watch_debounce_seconds = float(env_debounce)

env_max_tokens_run = os.getenv("CTX_MAX_TOKENS_PER_RUN")
if env_max_tokens_run:
    config.max_tokens_per_run = int(env_max_tokens_run)

env_max_usd_run = os.getenv("CTX_MAX_USD_PER_RUN")
if env_max_usd_run:
    config.max_usd_per_run = float(env_max_usd_run)

env_extensions = os.getenv("CTX_EXTENSIONS")
if env_extensions:
    config.extensions = [e.strip() for e in env_extensions.split(",") if e.strip()]
```

---

## 3. New Config Fields: Budget Guardrails

### 3.1 Fields on `Config` Dataclass

Add to `src/ctx/config.py`:

```python
@dataclass
class Config:
    # ... existing fields ...
    max_tokens_per_run: int | None = None   # None = unlimited
    max_usd_per_run: float | None = None    # None = unlimited
```

### 3.2 `.ctxconfig` Loading

Add parsing in the `.ctxconfig` overlay block:

```python
if "max_tokens_per_run" in data:
    config.max_tokens_per_run = None if data["max_tokens_per_run"] is None else int(data["max_tokens_per_run"])
if "max_usd_per_run" in data:
    config.max_usd_per_run = None if data["max_usd_per_run"] is None else float(data["max_usd_per_run"])
```

### 3.3 Budget Enforcement

Budget checks happen in `api.py` → `refresh()`, wrapping the calls to `generate_tree` / `update_tree`:

```python
def _check_budget(config: Config, stats: GenerateStats) -> None:
    """Raise BudgetExhaustedError if either budget limit is exceeded."""
    if config.max_tokens_per_run is not None and stats.tokens_used >= config.max_tokens_per_run:
        raise BudgetExhaustedError(
            f"Token budget exhausted: {stats.tokens_used:,} tokens used, "
            f"limit is {config.max_tokens_per_run:,}"
        )
    if config.max_usd_per_run is not None:
        cost = estimate_cost(stats.tokens_used, config.provider, config.resolved_model())
        if cost >= config.max_usd_per_run:
            raise BudgetExhaustedError(
                f"USD budget exhausted: ${cost:.4f} spent, "
                f"limit is ${config.max_usd_per_run:.4f}"
            )
```

**Critical rule**: Budget guardrails are **hard limits**. Agents cannot override them via CLI flags. The `max_tokens_per_run` and `max_usd_per_run` fields are NOT exposed as CLI options. They can only be set via `.ctxconfig` or env vars. This prevents a runaway agent from passing `--max-tokens 999999999`.

### 3.4 Interaction with Existing `token_budget`

The existing `token_budget` field in `Config` controls per-run budget at the generator level (checked between depth levels in `_run_generation`). The new `max_tokens_per_run` is an **additional** cap checked at the API layer. Both can be set independently:

- `token_budget` (existing): Checked inside `_run_generation`, skips remaining directories.
- `max_tokens_per_run` (new): Checked in `api.refresh()` after `generate_tree`/`update_tree` returns. If exceeded, the result includes `budget_exhausted=True`.
- `max_usd_per_run` (new): Same enforcement point as `max_tokens_per_run`, but based on cost estimate.

### 3.5 BudgetExhaustedError

```python
class BudgetExhaustedError(Exception):
    """Raised when a budget guardrail is hit."""
    pass
```

The OutputBroker maps this to error code `budget_exhausted`.

---

## 4. Auto-Config Flow

### 4.1 `--setup` Flag on `refresh`

When `ctx refresh . --setup` is invoked:

1. Run `detect_provider()` (from config.py).
2. If no provider detected, raise with `provider_not_configured`.
3. Check if `.ctxconfig` exists:
   - If yes and JSON mode: overwrite silently (agents don't prompt).
   - If yes and human mode: print existing config and ask `click.confirm("Overwrite?")`.
   - If no: proceed.
4. Call `write_default_config(root, provider, model, base_url)`.
5. Continue with normal refresh.

### 4.2 Zero-Config Agent Bootstrap

An agent can go from zero to working with:

```bash
export ANTHROPIC_API_KEY="sk-..."
export CTX_OUTPUT=json
ctx refresh .
```

No `--setup` needed — `refresh` auto-detects the provider from env vars via `load_config`. The `--setup` flag is only needed when:
- The agent wants to persist config to disk (`.ctxconfig`).
- No API key is in the env and a local provider needs auto-detection.

---

## 5. Interactive Prompt Elimination

### 5.1 Current Interactive Prompts

There are exactly **two** `click.confirm` calls in the codebase:

| Location | Context | Current Behavior |
|----------|---------|------------------|
| `cli.py` → `setup` (line 503) | `.ctxconfig` already exists | `click.confirm("Overwrite?")` |
| `cli.py` → `clean` (line 856) | Confirm deletion | `click.confirm("Delete all?")` |

### 5.2 JSON Mode Behavior

| Prompt | JSON Mode Behavior |
|--------|-------------------|
| Setup overwrite | Auto-proceed (overwrite silently). Agents expect idempotent commands. |
| Clean confirm | **Require `--yes` flag**. If `--yes` is not passed in JSON mode, return error code `unknown_error` with message `"--yes required in non-interactive mode"`. Never prompt. |

### 5.3 Implementation

In the `reset` command (new name for `clean`):

```python
@cli.command()
@click.pass_context
def reset(ctx, path, yes, dry_run):
    json_mode = ctx.obj.get("json_mode", False)
    if json_mode:
        yes = True  # Auto-confirm in JSON mode... wait, no:
        # Actually: reset is destructive. Require explicit --yes.
        if not yes:
            # In JSON mode without --yes, fail explicitly
            broker.add_error("unknown_error", "--yes flag required in non-interactive mode")
            return
```

**Correction to plan**: After reflection, in JSON mode `reset` should require `--yes`. This is a destructive operation. An agent must explicitly opt in. The pattern is:

```bash
ctx reset . --yes --output json
```

---

## 6. Cost Estimation — Shared Location

### 6.1 Move `_estimate_cost` and `_PRICING_DATA`

Currently in `cli.py` (lines 67-113). These are needed by both `cli.py` (human display) and `api.py` (budget enforcement). Move to a shared location.

**Option chosen**: Create a new function in `config.py` or keep in a small utility. The cleanest approach is to put it at the bottom of `config.py` since it's configuration-adjacent:

```python
# In src/ctx/config.py (append)

PRICING_DATA: dict[str, dict] = {
    "anthropic": {
        "models": [
            ("claude-3-opus", 15.0),
            ("claude-3-sonnet", 3.0),
            ("claude-3-haiku", 0.25),
        ],
        "default": 3.0,
    },
    "openai": {
        "models": [
            ("gpt-4o", 5.0),
            ("gpt-4-o", 5.0),
            ("gpt-4", 30.0),
            ("gpt-3.5-turbo", 0.5),
            ("gpt-3.5", 0.5),
        ],
        "default": 5.0,
    },
    "ollama": {"default": 0.0},
    "lmstudio": {"default": 0.0},
}
_DEFAULT_UNKNOWN_PROVIDER_PRICE = 3.0


def estimate_cost(tokens: int, provider: str, model: str) -> float:
    """Estimate cost in USD based on tokens and provider pricing."""
    # ... same logic as current _estimate_cost in cli.py ...
```

Update `cli.py` to import from `config.py`:

```python
from ctx.config import estimate_cost
```

Remove the old `_estimate_cost`, `_PRICING_DATA`, and `_DEFAULT_UNKNOWN_PROVIDER_PRICE` from `cli.py`.

---

## 7. Files

### Modified

| File | Changes |
|------|---------|
| `src/ctx/config.py` | New `Config` fields (`max_tokens_per_run`, `max_usd_per_run`), env var lookups for all fields, `estimate_cost` function moved here |
| `src/ctx/api.py` | Budget enforcement in `refresh()` |
| `src/ctx/cli.py` | Remove `_estimate_cost`/`_PRICING_DATA`, import from config; auto-confirm logic in `reset`; `--setup` handling in `refresh` |

---

## 8. Test Cases

### Config Env Var Tests (in `test_config.py` or existing test file)

1. **CTX_BASE_URL**: Set env var → config.base_url matches.
2. **CTX_MAX_FILE_TOKENS**: Set env var → config.max_file_tokens is int.
3. **CTX_MAX_DEPTH**: Set to "5" → 5. Set to "none" → None.
4. **CTX_TOKEN_BUDGET**: Set to "10000" → 10000.
5. **CTX_BATCH_SIZE**: Set to "4" → 4.
6. **CTX_CACHE_PATH**: Set to "" → empty string (cache disabled).
7. **CTX_MAX_CACHE_ENTRIES**: Set to "5000" → 5000.
8. **CTX_WATCH_DEBOUNCE**: Set to "1.5" → 1.5.
9. **CTX_MAX_TOKENS_PER_RUN**: Set to "50000" → 50000.
10. **CTX_MAX_USD_PER_RUN**: Set to "0.50" → 0.50.
11. **CTX_EXTENSIONS**: Set to ".py,.js,.ts" → [".py", ".js", ".ts"].
12. **Priority**: CLI flag overrides env var overrides .ctxconfig.
13. **CTX_OUTPUT**: Set to "json" → json_mode active.

### Budget Tests (in `test_api.py`)

14. **Token budget hit**: `max_tokens_per_run=100` → result has `budget_exhausted=True`.
15. **USD budget hit**: `max_usd_per_run=0.001` → result has `budget_exhausted=True`.
16. **No budget set**: Both None → no enforcement, runs to completion.
17. **Budget not a CLI flag**: Verify `--max-tokens-per-run` is NOT in Click options.

### Interactive Prompt Tests

18. **Reset without --yes in JSON mode**: Returns error, does not delete.
19. **Reset with --yes in JSON mode**: Deletes manifests, returns success.
20. **Setup overwrite in JSON mode**: Overwrites silently, no prompt.
