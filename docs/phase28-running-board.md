# Phase 28 — Running Board

> **Status:** Complete
> **Sprint:** 2 (Dogfooding, Analytics, Adoption)
> **Prerequisites:** Phase 29 (Preflight) merged. Main branch clean.
> **Tracking:** `state.md` under "Sprint 2 — Phase 28"

---

## 1. Overview

A persistent, append-only stats ledger that records every `ctx refresh` run.
Two storage layers: per-repo (`.ctx-cache/run_stats.json`) and global
(`~/.ctx/run_stats.json`). Serves as personal analytics and as proof-of-value
data for adoption and the future public leaderboard.

The board is **read-only from the user's perspective** — records are written
automatically by `ctx refresh` and read by `ctx stats --board`.

---

## 2. What gets recorded

One record per `ctx refresh` invocation (including `--until-complete` loops,
which write one record per cycle). Dry-run refreshes are **not** recorded.

### Run record schema (v1)

```json
{
  "ts": "2026-03-20T21:00:00.000Z",
  "dirs_processed": 18,
  "dirs_skipped": 4,
  "files_processed": 132,
  "tokens_used": 45000,
  "tokens_saved": 23000,
  "est_cost_usd": 0.036,
  "cost_saved_usd": 0.018,
  "cache_hits": 89,
  "cache_misses": 43,
  "strategy": "incremental",
  "errors": 0,
  "budget_exhausted": false,
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

| Field | Source | Notes |
|---|---|---|
| `ts` | `datetime.utcnow().isoformat() + "Z"` | Written at run completion |
| `dirs_processed` | `RefreshResult.dirs_processed` | |
| `dirs_skipped` | `RefreshResult.dirs_skipped` | |
| `files_processed` | `RefreshResult.files_processed` | |
| `tokens_used` | `RefreshResult.tokens_used` | Tokens that reached the LLM |
| `tokens_saved` | `CachingLLMClient.cache_hits * avg_tokens_per_file` | See section 3.1 |
| `est_cost_usd` | `RefreshResult.est_cost_usd` | |
| `cost_saved_usd` | `tokens_saved` run through `estimate_cost()` | |
| `cache_hits` | `CachingLLMClient.cache_hits` | New counter — see section 3.2 |
| `cache_misses` | `CachingLLMClient.cache_misses` | New counter — see section 3.2 |
| `strategy` | `RefreshResult.strategy` | "full", "incremental", "smart" |
| `errors` | `len(RefreshResult.errors)` | Count, not full list |
| `budget_exhausted` | `RefreshResult.budget_exhausted` | |
| `provider` | `config.provider` | From resolved config |
| `model` | `config.resolved_model()` | From resolved config |

---

## 3. Required instrumentation

### 3.1 Cache savings estimation

`tokens_saved` is estimated as:
```python
avg_tokens_per_miss = tokens_used / cache_misses if cache_misses > 0 else 0
tokens_saved = round(avg_tokens_per_miss * cache_hits)
```

This is an estimate, not an exact measurement — the cache returns zero-token
`LLMResult` objects so we don't know the exact token cost of the original calls.
The estimate is labelled as such in the board display.

### 3.2 Cache hit/miss counters in `CachingLLMClient`

Add two thread-safe counters to `CachingLLMClient` (in `src/ctx/llm.py`):

```python
# In __init__:
self.cache_hits: int = 0
self.cache_misses: int = 0
```

In `summarize_files`, inside the lock after the cache lookup:

```python
with self._lock:
    for i, _ in enumerate(files):
        if keys[i] in self._cache:
            file_futures.append(self._cache[keys[i]])
            self.cache_hits += 1        # NEW
        else:
            ...
            to_fetch.append(i)
            self.cache_misses += 1      # NEW
```

These counters accumulate across all `summarize_files` calls in a single
refresh run. They are reset to zero when a new `CachingLLMClient` is
instantiated (i.e., per-run).

Expose them via a read-only property:
```python
@property
def hit_miss_counts(self) -> tuple[int, int]:
    """Returns (cache_hits, cache_misses) for this run."""
    return self.cache_hits, self.cache_misses
```

### 3.3 Surface counters through `api.py`

Add two fields to `RefreshResult`:

```python
@dataclass
class RefreshResult:
    ...
    cache_hits: int = 0
    cache_misses: int = 0
```

In `refresh()`, after the generation loop, extract from the client:

```python
cache_hits, cache_misses = (
    client.hit_miss_counts
    if hasattr(client, "hit_miss_counts")
    else (0, 0)
)

return RefreshResult(
    ...
    cache_hits=cache_hits,
    cache_misses=cache_misses,
)
```

---

## 4. Storage layout

### 4.1 Per-repo: `.ctx-cache/run_stats.json`

```json
{
  "schema_version": 1,
  "runs": [
    { ...run record... },
    { ...run record... }
  ]
}
```

- Located at `{cache_path_dir}/run_stats.json` (sibling to `llm_cache.json`).
- `cache_path_dir` is the directory of `config.cache_path` resolved at runtime.
  Default: `.ctx-cache/run_stats.json` relative to the refresh root.
- Written atomically via `tempfile.mkstemp` + `os.replace` (Windows-safe).
- No size limit. Entries are never pruned — the ledger is append-only.
- If the file does not exist, it is created on the first run.
- If the file is malformed (corrupt JSON), it is **overwritten** with a fresh
  ledger containing only the current run. Corruption is logged as a warning to
  stderr in human mode.

### 4.2 Global: `~/.ctx/run_stats.json`

```json
{
  "schema_version": 1,
  "repos": {
    "/abs/path/to/repo": {
      "last_run": "2026-03-20T21:00:00.000Z",
      "run_count": 7,
      "total_dirs_processed": 126,
      "total_tokens_used": 315000,
      "total_tokens_saved": 189000,
      "total_cost_usd": 0.252,
      "total_cost_saved_usd": 0.151
    }
  },
  "totals": {
    "repos_touched": 3,
    "total_runs": 14,
    "total_dirs_processed": 287,
    "total_tokens_used": 720000,
    "total_tokens_saved": 432000,
    "total_cost_usd": 0.576,
    "total_cost_saved_usd": 0.346
  }
}
```

- Located at `Path.home() / ".ctx" / "run_stats.json"`.
- `~/.ctx/` directory is created if it does not exist (mode 0o700).
- Global file stores **pre-aggregated totals only** — not individual run records.
  Per-run detail lives in the per-repo file.
- Updated atomically on every refresh run (same write pattern as per-repo).
- If malformed, overwritten with fresh aggregates derived from the current run.
- The repo key is the **resolved absolute path** of the refresh root. This makes
  the key stable across working directory changes.

---

## 5. Write path

After every non-dry-run `ctx refresh` completes (whether via CLI or `api.refresh()`),
call `record_run(root, result, config)`:

```python
def record_run(root: Path, result: RefreshResult, config: Config) -> None:
    """Append run stats to per-repo and global ledgers.

    Never raises — stats recording is best-effort. All errors are
    silently swallowed to avoid breaking the refresh exit path.
    """
```

This function lives in a new module: `src/ctx/stats_board.py`.

**Call site in `api.py`:**

```python
# At the end of refresh(), after building RefreshResult, before returning:
from ctx.stats_board import record_run
if not dry_run:
    record_run(root, result, config)
return result
```

**Why `api.py` not `cli.py`:** The API module is the single exit point for
refresh regardless of whether it was called from the CLI, MCP, or directly.
Recording in `api.py` ensures every refresh path (including `--until-complete`
loops, which call `api.refresh()` multiple times) writes a record.

---

## 6. CLI surface

### 6.1 `ctx stats --board`

Add `--board` flag to the existing `stats` command (hidden legacy alias in
`cli.py`). **Do not add to `ctx check`** — the board is a distinct concept
from health checking.

```
ctx stats --board [PATH] [--global] [--format text|json]
```

**Default (human mode, per-repo):**

```
ctx running board — /path/to/repo

Runs:                47
Directories:        843  total processed
Tokens used:    1.24M    across all runs
Tokens saved:     890K   (est. via cache)
Cost:             $0.99
Cost saved:       $0.71  (est. via cache)
Cache hit rate:    72%

Recent runs (last 5):
  2026-03-20 21:00  incremental   18 dirs    45K tokens   $0.036   72% cache
  2026-03-19 14:22  full         132 dirs   280K tokens   $0.224   0% cache
  ...
```

**`--global` flag (human mode):**

```
ctx running board — global

Repos tracked:        3
Total runs:          47
Total directories:  843
Total tokens:      1.24M
Total cost:         $0.99
Total tokens saved:  890K  (est.)
Total cost saved:    $0.71 (est.)

Per-repo breakdown:
  /path/to/repo-a      23 runs   520 dirs   $0.41
  /path/to/repo-b      18 runs   201 dirs   $0.38
  /path/to/repo-c       6 runs   122 dirs   $0.20
```

**`--format json` (per-repo):**

```json
{
  "schema_version": 1,
  "repo": "/abs/path",
  "aggregate": {
    "run_count": 47,
    "total_dirs_processed": 843,
    "total_tokens_used": 1240000,
    "total_tokens_saved": 890000,
    "total_cost_usd": 0.992,
    "total_cost_saved_usd": 0.712,
    "cache_hit_rate": 0.72
  },
  "recent_runs": [
    {
      "ts": "2026-03-20T21:00:00.000Z",
      "dirs_processed": 18,
      "tokens_used": 45000,
      "tokens_saved": 23000,
      "est_cost_usd": 0.036,
      "cost_saved_usd": 0.018,
      "cache_hits": 89,
      "cache_misses": 43,
      "strategy": "incremental",
      "provider": "anthropic",
      "model": "claude-haiku-4-5-20251001"
    }
  ]
}
```

**`--format json --global`:**

```json
{
  "schema_version": 1,
  "totals": { ...global totals object... },
  "repos": { ...per-repo summary dict... }
}
```

### 6.2 No changes to `ctx refresh` output

The running board records silently in the background. The refresh output is
unchanged. Do not print "stats recorded" or similar.

---

## 7. Implementation plan

### 7.1 New module: `src/ctx/stats_board.py`

```python
"""Persistent run-stats ledger for ctx.

Per-repo: {cache_dir}/run_stats.json   (full run history)
Global:   ~/.ctx/run_stats.json        (aggregated totals only)
"""
```

Public API:

```python
def record_run(root: Path, result: "RefreshResult", config: "Config") -> None:
    """Append run stats to per-repo and global ledgers. Never raises."""

def read_board(root: Path, config: "Config") -> dict:
    """Return the per-repo board data as a dict ready for display/export."""

def read_global_board() -> dict:
    """Return the global board data as a dict ready for display/export."""
```

Internal helpers:

```python
def _run_stats_path(root: Path, config: "Config") -> Path:
    """Resolve the per-repo run_stats.json path."""

def _global_stats_path() -> Path:
    """Return ~/.ctx/run_stats.json, creating ~/.ctx/ if needed."""

def _load_json_safe(path: Path, default: dict) -> dict:
    """Load JSON from path; return default if missing or malformed."""

def _save_json_atomic(path: Path, data: dict) -> None:
    """Write data as JSON atomically via tempfile + os.replace."""

def _build_run_record(result: "RefreshResult", config: "Config") -> dict:
    """Convert a RefreshResult + Config into a run record dict."""

def _update_global(global_path: Path, repo_key: str, record: dict) -> None:
    """Load global file, update repo totals and grand totals, save atomically."""
```

### 7.2 Modify `src/ctx/llm.py` — `CachingLLMClient`

- Add `self.cache_hits: int = 0` and `self.cache_misses: int = 0` to `__init__`.
- Increment in `summarize_files` inside the lock (see section 3.2).
- Add `hit_miss_counts` property.
- These are the **only** changes to `llm.py`.

### 7.3 Modify `src/ctx/api.py` — `RefreshResult` and `refresh()`

- Add `cache_hits: int = 0` and `cache_misses: int = 0` to `RefreshResult`.
- Extract from `client` at return site.
- Call `record_run(root, result, config)` after building `RefreshResult`,
  before returning, guarded by `if not dry_run`.

### 7.4 Modify `src/ctx/cli.py` — `stats` command

Add `--board` and `--global` flags to the existing hidden `stats` command.
When `--board` is present, call `read_board()` or `read_global_board()` and
render per the display format in section 6.1. The existing `stats` behavior
(coverage table) is unaffected when `--board` is absent.

---

## 8. Test plan

All tests go in `tests/test_stats_board.py` (new file). No real filesystem
side-effects — use `tmp_path` fixtures throughout.

### 8.1 `stats_board.py` unit tests

- `test_record_run_creates_per_repo_file` — after `record_run()`, `.ctx-cache/run_stats.json` exists with one entry.
- `test_record_run_appends_on_second_call` — two calls → two records in the `runs` array.
- `test_record_run_updates_global_file` — global `~/.ctx/run_stats.json` (temp dir) updated with repo entry and totals.
- `test_record_run_never_raises_on_corrupt_file` — corrupt `run_stats.json` → overwritten, no exception.
- `test_record_run_never_raises_on_unwritable_dir` — unwritable cache dir → silent, no exception.
- `test_record_run_skips_on_dry_run` — `dirs_processed=0, stale_directories=[...]` skipped (dry-run guard is in `api.py`, not `stats_board.py` — test the full path via `api.py` mock).
- `test_read_board_empty` — no `run_stats.json` → returns empty aggregate with zeros.
- `test_read_board_aggregate` — 3 run records → correct totals, correct cache hit rate.
- `test_read_global_board_multi_repo` — two repos with entries → per-repo breakdown and grand totals correct.
- `test_run_record_fields` — `_build_run_record()` populates all expected keys from `RefreshResult`.
- `test_tokens_saved_estimation` — correct formula: `(hits / (hits + misses)) * tokens_used` rounded.
- `test_atomic_write_is_safe` — verify temp file is cleaned up and final file is valid JSON.

### 8.2 `CachingLLMClient` unit tests (in `tests/test_llm.py`)

- `test_cache_hit_counter_increments` — second call with same file → `cache_hits == 1`, `cache_misses == 1`.
- `test_cache_miss_counter_increments` — first call → `cache_hits == 0`, `cache_misses == 1`.
- `test_hit_miss_counts_property` — returns tuple `(hits, misses)`.

### 8.3 `RefreshResult` tests (in `tests/test_api.py`)

- `test_refresh_result_includes_cache_fields` — `cache_hits` and `cache_misses` default to 0.

### 8.4 CLI board tests (in `tests/test_cli.py`)

- `test_stats_board_human_mode` — invoke `ctx stats --board {path}`, mock `read_board()`. Verify output contains "Runs:", "Tokens used:", "Cost:".
- `test_stats_board_global_mode` — invoke `ctx stats --board --global`, mock `read_global_board()`. Verify output contains "Repos tracked:".
- `test_stats_board_json_mode` — invoke `ctx stats --board --output json`. Parse JSON, verify `aggregate.run_count`.
- `test_stats_board_empty_state` — no `run_stats.json` in tmp_path → displays "No runs recorded yet."

**Total: 20 new tests** (12 board unit + 3 LLM + 1 API + 4 CLI).

---

## 9. File change summary

| File | Change |
|---|---|
| `src/ctx/stats_board.py` | **New.** `record_run()`, `read_board()`, `read_global_board()`, internal helpers. |
| `src/ctx/llm.py` | Add `cache_hits`, `cache_misses` counters and `hit_miss_counts` property to `CachingLLMClient`. |
| `src/ctx/api.py` | Add `cache_hits`, `cache_misses` to `RefreshResult`. Extract from client. Call `record_run()`. |
| `src/ctx/cli.py` | Add `--board` and `--global` flags to `stats` command. |
| `tests/test_stats_board.py` | **New.** 12 unit tests. |
| `tests/test_llm.py` | +3 tests for hit/miss counters. |
| `tests/test_api.py` | +1 test for new `RefreshResult` fields. |
| `tests/test_cli.py` | +4 board CLI tests. |
| `state.md` | Mark Phase 28 deliverables complete. |

---

## 10. Boundaries

### In scope
- `stats_board.py` module with record, read, and global functions.
- `CachingLLMClient` hit/miss counters (minimal change).
- `RefreshResult` new fields (`cache_hits`, `cache_misses`).
- `ctx stats --board` and `ctx stats --board --global` CLI surface.
- JSON export (`--format json`).
- All 20 tests.

### Out of scope
- Public leaderboard webpage — this spec produces the JSON export that feeds it; the web page is a separate future project.
- Modifying `ctx refresh` output (board records silently).
- Pruning or migrating run history.
- Per-run breakdown in the global file (global stores aggregates only).
- Any changes to `generator.py` or language parsers.

### Shipped beyond spec
- `--since` filter — time-window filter for board runs (e.g. `7d`, `4w`, `2026-03-01`).
- `--trend` sparklines — ASCII sparklines for cost and cache-hit trends.
- `--format csv` — CSV export of recent runs.
- Per-model breakdown — `ctx stats --board` now shows a per-model cost/token table.
- MCP tools — `ctx_board` and `ctx_global_board` expose the running board via the MCP server (previously out of scope).

---

## 11. Acceptance criteria

1. Every non-dry-run `ctx refresh` writes a record to `.ctx-cache/run_stats.json`.
2. Every non-dry-run `ctx refresh` updates `~/.ctx/run_stats.json` totals.
3. `ctx stats --board .` displays aggregate totals and last 5 runs.
4. `ctx stats --board --global` displays cross-repo aggregate and per-repo breakdown.
5. `ctx stats --board --format json` produces the JSON structure in section 6.1.
6. `record_run()` never raises — all errors are silently swallowed.
7. `cache_hits` and `cache_misses` are non-zero after a refresh that uses a warm cache.
8. All 20 tests pass.
9. 452 → 472 tests (net +20).
10. No changes to `generator.py` or language parsers.
