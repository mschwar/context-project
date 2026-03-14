# Phase 7 Reflection — Go Parser, ctx watch, Cache Model-Awareness

**Date:** 2026-03-14
**Branch:** `feat/phase7-*` (three PRs: #19, #20, #21)
**Status:** Complete

---

## Successes

- **Go parser** shipped cleanly. The capitalisation-based export convention (uppercase = exported) maps naturally to a set of targeted regexes. The multi-step const parsing (single `const Name =` plus block scan with `[^)]*` instead of `re.DOTALL`) resolved the Gemini feedback and the SonarCloud ReDoS hotspot in one commit.
- **`ctx watch`** was the most complex deliverable and landed without major issues. The key design decisions — CONTEXT.md write exclusion (infinite-loop prevention), per-file debounce via `threading.Timer`, and delegating to the existing `update_tree` rather than re-implementing generation logic — kept the implementation compact.
- **Cache model-awareness** was a one-line change in the right place (`sha256(model_bytes + b":" + file_json)`) with immediate correctness. Existing cache files become model-segregated on the next run with no migration needed — old entries simply become permanent misses and are eventually overwritten.
- The Gemini code review on PR #21 caught a genuine logical flaw: the first version of `test_caching_client_different_models` used two separate in-memory caches that could never cross-hit, so the test passed for the wrong reason. The fix (shared disk cache) is the correct architecture for this test.

## Friction

- The Gemini auto-commits to the ctx-watch PR (#20) removed `_FakeEvent` from `watcher.py` and replaced the debounce test with a `@patch(threading.Timer)` approach that was broken (it indexed `call_args.args[2]` when `args=[path]` is a keyword argument). Both regressions were caught locally before pushing and fixed in the model-awareness PR commit.
- The `should_ignore(path, spec, root)` argument order was different from what I assumed — `(path, spec, target_root)` not `(path, root, spec)`. Caught immediately by the first test run.
- Phase 7 spanned three PRs rather than one. Each was small enough that this was appropriate, but the gate protocol is designed around single-branch phases. Worth noting: multi-PR phases work fine as long as each PR passes CI independently before merging.

## Observations

- `ctx watch` blocks on `observer.join()` which is the correct Unix-style pattern. On Windows the watchdog `Observer` uses `ReadDirectoryChangesW` natively, so the watcher is cross-platform without additional configuration.
- The debounce window (0.5 s) is a reasonable default but could become a config key (`watch_debounce`) if users request it. Not worth adding now.
- The cache model-awareness change is a breaking change for existing `.ctx-cache/llm_cache.json` files — all prior entries are now keyed without a model prefix and will never match again. On first run after upgrading, the full tree will be regenerated. This is the correct behaviour (stale summaries are worse than a one-time regeneration cost), but it should be mentioned in the RUNBOOK under cache management.
- The project now has parsers for Python, JavaScript, TypeScript, Rust, and Go — the five most common languages in open-source projects. Java and C# are the next obvious candidates but are significantly lower priority given the existing coverage.

## Suggestions

1. **Document cache migration behaviour** — add a note to `RUNBOOK.md` that upgrading from pre-model-aware cache versions triggers a one-time full regeneration.
2. **Phase 8 candidate — `ctx watch` debounce config** — expose `watch_debounce_seconds` as a `.ctxconfig` key if user demand emerges.
3. **Phase 8 candidate — Java/C# parsers** — complete coverage for enterprise language stacks.
4. **Phase 8 candidate — tiktoken token counting** — replace the character-based `_estimate_tokens` approximation with accurate per-model token counts. Would improve budget enforcement accuracy.

## Implications for Phase 8

- Start from `main` (143 tests, all CI green).
- No blocking gate conditions — Phase 8 can begin whenever scoped.
- The RUNBOOK cache migration note should be added in the Phase 7 closeout (small enough to do now).
