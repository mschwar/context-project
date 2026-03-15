# Phase 12 Reflection — Language Depth & CLI Ergonomics

**Date:** 2026-03-14
**Branch:** `feat/phase12-language-depth`
**Tests:** 213 passing (up from 195 at Phase 11 close)

---

## Successes

- All six deliverables landed in a single commit with no rework required.
- Kotlin parser handled the full idiomatic surface: `fun`, `data class`, `sealed class`, `object`, `enum class`, `fun interface`. The modifier list is broad enough to cover most real-world Kotlin files.
- Ruby parser is intentionally maximalist (captures all `def`/`class`/`module` regardless of visibility) — correct for Ruby's public-by-default model.
- `ctx diff` provides genuinely useful diagnostic output with no configuration needed; the `[mod]`/`[new]` prefix makes the output actionable at a glance.
- C# property/method separation resolves the Phase 11 ambiguity cleanly: `{ get; set; }` and `=>` bodies go to `properties`; `(` bodies go to `methods`.
- Java annotation stripping (`_ANNOTATION_LINE.sub`) is a clean single-pass fix that handles arbitrarily stacked annotations (`@Override\n@Deprecated\npublic void foo()`).
- `ctx init --no-overwrite` reuses `update_tree` rather than duplicating logic — correct delegation.

## Friction Points

- `ctx diff` relies on `git` being in `$PATH` and the working directory being inside a git repo. The error message (`click.UsageError`) is clear, but there is no graceful degradation for non-git projects.
- The Kotlin `_OBJECT` regex matches named objects but not anonymous `companion object {}` (no name to capture). This is acceptable — companion objects are implementation detail, not API surface.
- `ctx diff` uses `git diff HEAD` which shows staged+unstaged changes against the last commit. If `CONTEXT.md` files were just written and staged but not committed, they will appear as modified. This is the intended behaviour but may surprise users running `ctx diff` immediately after `ctx init`.
- Ruby `_DEF` captures all `def` including private methods (e.g., inside a `private` block). Ruby's visibility model makes static analysis imperfect here; false positives are preferable to false negatives for context generation.

## Observations

- Language parser count is now 8 (Python, JS/TS, Rust, Go, Java, C#, Kotlin, Ruby). The pattern is highly repetitive — each parser is ~50 lines of regex + dict. A future refactor could extract a generic `RegexParser` base, but the current duplication is not yet painful.
- Test count growth from Phase 11 to Phase 12: 195 → 213 (+18). Healthy ratio.
- The `ctx diff` command is the first command that shells out to git. This is a soft architectural boundary crossed — worth noting for future contributors.

## Suggestions for Phase 13

### Carry-forward (must include)
*(None — all Phase 12 items from the Phase 11 reflection were addressed.)*

### New suggestions
1. **PHP parser** — `public function`, `class`, `interface`, `trait`, `enum`. Common in web projects; `.php` already in `EXTENSION_MAP`.
2. **Swift parser** — `func`, `class`, `struct`, `protocol`, `enum`. Already in `EXTENSION_MAP`.
3. **`ctx diff --since <ref>`** — extend `ctx diff` to accept a git ref (branch, commit, tag) so users can see what changed since a specific point, not just since `HEAD`.
4. **Non-git fallback for `ctx diff`** — when not in a git repo, fall back to comparing `CONTEXT.md` modification times against source file modification times.
5. **`ctx init` idempotency note in docs** — clarify in README that `ctx init` regenerates all manifests unconditionally (use `ctx update` or `ctx init --no-overwrite` for incremental runs).
6. **Kotlin `companion object` as a named entry** — emit `"companion"` or the enclosing class name as the object name when no name is present.

## Disposition of Suggestions

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | PHP parser | Carry into Phase 13 |
| 2 | Swift parser | Carry into Phase 13 |
| 3 | `ctx diff --since <ref>` | Carry into Phase 13 |
| 4 | Non-git fallback for `ctx diff` | Carry into Phase 13 |
| 5 | `ctx init` idempotency docs | Carry into Phase 13 |
| 6 | Kotlin `companion object` naming | Defer — low value, high complexity for edge case |
