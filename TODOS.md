# TODOS

## Run History Pruning

**What:** Add configurable retention policy to prune old run records from per-repo `run_stats.json`.

**Why:** The append-only ledger grows unbounded. A repo refreshed daily for a year accumulates ~365 records. While each record is small (~500 bytes), the file will eventually slow down `read_board()` and waste disk. More importantly, stale data from months ago has diminishing analytical value.

**Pros:**
- Prevents unbounded file growth
- Keeps `read_board()` fast regardless of repo age
- Reduces disk footprint for long-running repos

**Cons:**
- Adds complexity to the write path (prune after append)
- Needs a sensible default (e.g., 90 days or 500 runs) that works for most users
- Must not break global totals — global file tracks aggregates, not individual runs, so pruning per-repo is safe

**Context:** The current `record_run()` appends to a `runs` list with no cap. The pruning should happen inside `record_run()` after the append, trimming runs older than the retention window. The global file (`~/.ctx/run_stats.json`) stores only aggregated totals per repo, so it is unaffected by per-repo pruning. A reasonable default is 90 days or 500 records (whichever is more generous). The retention period could be configurable via `ctx.yaml` if needed, but a hardcoded default is fine for v1.

**Effort:** S (human: ~2 hours / CC: ~10 min)
**Priority:** P3 — not urgent, ledger is small per-record
**Depends on:** Nothing — can be done independently
