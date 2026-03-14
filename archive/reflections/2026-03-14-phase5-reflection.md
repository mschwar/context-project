# Phase 5 Reflection — Cost Control & Observability

**Date:** 2026-03-14
**Branch:** `feat/phase5-cost-control`
**PR:** #15 (merged)
**Status:** Complete

---

## Successes

- All three deliverables shipped cleanly on one branch with no scope creep.
- **Persistent disk cache** works exactly as designed: second run on an unchanged tree makes zero LLM calls, cache file appears in `.ctx-cache/llm_cache.json`, and the `.ctxignore.default` entry prevents it from influencing content hashes.
- **Token budget enforcement** was already partially wired in `_run_generation`; Phase 5 completed it by adding the `budget_exhausted` flag and surfacing a dedicated CLI warning instead of burying the budget-hit event in the error list.
- **`--dry-run`** required no new dependencies. `check_stale_dirs()` reuses `is_stale()` and `_should_regenerate_directory()` cleanly, and the implementation is a single pass — no LLM calls, no file writes.
- Gemini code review surfaced two legitimate issues (duplicated dry-run output logic, per-entry disk writes) that were caught and fixed before merge. Both fixes reduced code and improved performance.

## Friction

- The dry-run API-key failure in CI was a gap in local testing: the CI environment doesn't have `ANTHROPIC_API_KEY`, and `load_config` raised `UsageError` before any staleness logic ran. Fix was minimal (`require_api_key=False`), but the gap points to a pattern: CLI paths that don't need an LLM should not be gated by API-key validation.
- The fixture discovery issue (`sample_project` has pre-existing `CONTEXT.md` files) caused the dry-run test to pass locally but behave differently than expected. Tests that assume a "no manifests" state must explicitly clean up fixture CONTEXT.md files.
- Two pre-existing CI failures (CTX Manifest Check, PR Checks / Validate PR) create noise on every PR. These are infra-level issues unrelated to Phase 5 but should be fixed in a future chore.

## Observations

- The `CachingLLMClient` disk cache keys on file content hash only — not on model or provider. If a user switches models (e.g., haiku → sonnet), stale summaries will be served from cache. This is a known limitation; users can delete `.ctx-cache/` to reset. Worth documenting.
- `_resolve_cache_path` always defaults to disk caching even when not explicitly configured. This is the right default but should be mentioned in user-facing docs so users understand where the file appears.
- SonarCloud's 3% duplication threshold is aggressive for a codebase this size. The extracted `_echo_stale_dirs` helper was a genuine improvement, but future phases should keep an eye on this threshold.

## Suggestions

1. **Phase 6 candidate — `ctx watch`**: File watcher for auto-regeneration. High demand for active development workflows. Requires one new dependency (watchdog or watchfiles).
2. **Phase 6 candidate — Language parsers**: JS/TS/Rust/Go parsers would make summaries more informative for the most common open-source language mix.
3. **Chore: fix pre-existing CI failures** — CTX Manifest Check needs `.github/actions/ctx-check` to exist. PR Checks needs Python env in the workflow. These should be a separate chore branch.
4. **Chore: document cache invalidation** — Add a note to README/RUNBOOK about the `.ctx-cache/` directory, how to reset it, and that it's model-agnostic.
5. **Chore: add `require_api_key` pattern to AGENTS.md rules** — Note that CLI paths not requiring LLM calls should pass `require_api_key=False` to avoid CI failures.

## Implications for Phase 6

- Start from `main` (Phase 5 merged cleanly).
- `ctx watch` is the highest-value next feature but adds a new dependency. Decision: include it or scope a smaller "Language Expansion" phase first.
- The CI noise from pre-existing broken checks should be resolved in a chore PR before Phase 6 to keep the CI signal clean.
