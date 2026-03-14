# Phase 6 Reflection — Language Expansion & CI Hygiene

**Date:** 2026-03-14
**Branch:** `feat/phase6-language-expansion`
**PR:** #17 (merged)
**Status:** Complete

---

## Successes

- All three deliverables shipped on one branch with no scope creep.
- **JS/TS parser** covers the most common export patterns cleanly with no new dependencies: named functions, async functions, arrow/const functions, classes (including abstract), interfaces, type aliases, and default exports. The regex approach is robust for the key identifiers without the complexity of a full AST parse.
- **Rust parser** handles the public-visibility spectrum correctly — `pub`, `pub(crate)`, `pub(super)` — using a single regex group. `mod` declarations (both public and private) are captured, which is useful since module structure is architecturally important in Rust.
- **CI hygiene (6.3)** resolved both pre-existing failures cleanly. `pr-checks.yml` was a stock GitHub template (Node/npm) that was never updated for a Python project. `ctx-check.yml` referenced a composite action that was never created. Both are now inline Python workflows using the same pattern as the working `tests.yml`. No new YAML abstractions were introduced.
- The CTX Manifest Check now validates itself: the check enforces that CONTEXT.md files are fresh, and the Phase 6 commit required regenerating 14 manifests before the check would pass. The loop is closed.
- Gemini code review caught two legitimate gaps: the `Dict[str, List[str]]` return type annotation was incorrect (the dict also contains a `bool`), and `test_missing_file` in both test files only asserted a subset of keys. Both were fixed promptly.

## Friction

- The `ctx-check.yml` failing on the Phase 6 PR was expected (stale manifests), but the regeneration step (`ctx update .`) must happen locally before pushing. This is a developer workflow expectation that is not currently documented anywhere visible. A developer new to the repo would be confused by a failing CI check until they understand the manifest lifecycle.
- The three Gemini auto-fix commits (`77ad67b`, `1bfaeda`, `8267a43`) landed directly on the feature branch via the GitHub UI before I pulled them. This means the branch diverged mid-review. The pattern works but requires a `git pull` before any further local commits.

## Observations

- The regex parsers are intentionally conservative: they only extract declarations at the start of a line (anchored with `^`). This prevents false positives from inline strings or comments at the cost of missing indented module-level declarations in unusual code styles. For `ctx`'s summarization use case, precision over recall is correct.
- The JS/TS parser does not distinguish between `.js` and `.ts` output keys — both return the same shape. The `language` field on the file entry already carries the distinction. This is the right design: the parser's job is extraction, not classification.
- There is no Go parser yet. Go is in `language_detector.py`'s `EXTENSION_MAP` but falls through to an empty `metadata = {}` in `generator._prepare_file_entry`. This is a natural Phase 7 candidate.
- `ctx watch` (file watcher for auto-regeneration) was deferred from Phase 6. It remains the highest-demand missing feature for active development workflows.

## Suggestions

1. **Document the manifest refresh requirement** — Add a note to `CONTRIBUTING.md` or `RUNBOOK.md` explaining that code changes which affect directory contents require running `ctx update .` locally before pushing, or the CTX Manifest Check will fail.
2. **Phase 7 candidate — Go parser** — `pub`-equivalent in Go is capitalization (`func Foo` vs `func foo`). Simple regex extraction of exported identifiers would complete the four most common open-source languages.
3. **Phase 7 candidate — `ctx watch`** — `watchdog` or `watchfiles` dependency. Auto-triggers `ctx update` on file save. High value for active development.
4. **Phase 7 candidate — cache model-awareness** — The disk cache keys on content hash only, not on model/provider. A `cache_key_version` config field or model suffix in the key would prevent stale summaries after model changes.

## Implications for Phase 7

- Start from `main` (Phase 6 merged cleanly, 127 tests, all CI green).
- The natural next phase groups around **depth of language support** (Go parser, richer metadata) and **developer ergonomics** (`ctx watch`, cache model-awareness).
- The CI is now fully green and self-validating. Any future phase that adds source files must include a `ctx update .` pass before committing.
