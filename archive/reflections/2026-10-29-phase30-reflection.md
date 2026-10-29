# Phase 30 Reflection — High-Signal Architectural & Invariant Maps Pivot & Queue Drain

**Date:** 2026-10-29  
**Baseline:** `ctx` v1.1.0 (`ed34823`, 538 passing tests)

## Plan vs Actuals

| Planned Item | Actual Outcome | Notes |
|--------------|----------------|-------|
| **30.1** Surface `.ctx/hook_log.json` telemetry in MCP resources & `ctx check` | Completed | Added `ctx://.ctx/hook_log.json` to `RESOURCE_DEFINITIONS` in `src/ctx/mcp_server.py` (with empty-runs fallback when initialized) and `hook_runs`/`hook_failures` summary fields in `src/ctx/api.py` `check()`. |
| **30.2** Run history pruning in `stats_board.py` | Completed | Added `prune_runs()`, `DEFAULT_MAX_RUNS = 500`, and `DEFAULT_RETENTION_DAYS = 90` (whichever is more generous) wired into `record_run()`. |
| **30.3** Lightweight `ctx.sdk` module | Completed | Created `src/ctx/sdk.py` (`CtxProject.load(path)`, `get_context(depth)`, `metadata`, `hook_telemetry`, `is_stale()`) with zero external dependencies. |
| **30.4** Deterministic Structural Skeleton First (`src/ctx/skeleton.py`) | Completed | Built `extract_skeleton()`, `should_invoke_llm()`, and tiered renderers (`render_context_0`, `render_context_1`, `render_context_full`) across all 11 built-in language parsers with `structural_hash` and `boundary_doc_hash`. |
| **30.5** Root + Subsystem Architecture Synthesis (`ctx init --tier2`) | Completed | Added `tier2=True` to `init_project()`, `--tier2` flag to `ctx init`, and structural/boundary hash gating in `run_hook()` so git hooks skip rewrites when internal edits do not alter signatures or boundary docs. |
| **30.6** Fleet Ingestion Pre-Processor Capsule (`ctx export --capsule`) | Completed | Added `api.build_fleet_capsule()` and `ctx export --capsule` emitting a compact deterministic capsule for `project-ledger` and `gbrain` ingestion. |
| **30.7** Legacy command docs cleanup in `RUNBOOK.md` | Completed | Replaced remaining legacy `ctx update` / `ctx status` references in `RUNBOOK.md` with `ctx refresh` / `ctx check`. |

## Surprises & Root Causes

1. **Hook PID File Perturbing `structural_hash` During `run_hook`:**
   - *Symptom:* In `test_run_hook_tier2_updates_only_on_structural_or_boundary_change`, the first `run_hook` invocation rewrote `.ctx/CONTEXT-0.md` even though only a Python comment had changed.
   - *Root Cause:* `run_hook()` acquires `.ctx-hook.pid` in the repository root before running the refresh/skeleton check. Because `.ctx-hook.pid` was not present during `init_project()`, `extract_skeleton()` saw a new root file and computed a different `structural_hash`.
   - *Fix:* Excluded `.ctx-hook.pid`, `.ctx-lock`, `.ctxconfig`, `.ctxignore`, and `.gitignore` from `_walk()` in `src/ctx/skeleton.py`.

## Disposition Table

| Finding / Item | Disposition | Target Reference |
|----------------|-------------|------------------|
| Expose `ctx://.ctx/hook_log.json` & `ctx check` hook telemetry | **Fix now** (completed in `src/ctx/mcp_server.py` & `src/ctx/api.py`) | Phase 30 (`30.1`) |
| Prune `.ctx-cache/run_log.json` to 90d / 500 runs | **Fix now** (completed in `src/ctx/stats_board.py`) | Phase 30 (`30.2`) |
| Ship zero-dependency `ctx.sdk` for `.ctx/` consumers | **Fix now** (completed in `src/ctx/sdk.py`) | Phase 30 (`30.3`) |
| Deterministic structural skeleton & hash gating | **Fix now** (completed in `src/ctx/skeleton.py`) | Phase 30 (`30.4`) |
| `ctx init --tier2` root + subsystem synthesis | **Fix now** (completed in `src/ctx/init.py` & `src/ctx/cli.py`) | Phase 30 (`30.5`) |
| Fleet ingestion capsule (`ctx export --capsule`) | **Fix now** (completed in `src/ctx/api.py` & `src/ctx/cli.py`) | Phase 30 (`30.6`) |
| Legacy command cleanup in `RUNBOOK.md` | **Fix now** (completed in `RUNBOOK.md`) | Phase 30 (`30.7`) |
| Optional LLM prose enrichment layer on top of Tier 2 structural skeleton when `should_invoke_llm()` is True | **Carry into Phase 31** | `state.md` §Phase 31 |
