# Phase 13 Reflection — Extended Language Support & CLI Polish

**Date:** 2026-03-14
**Branch:** `feat/phase13-extended-language-support`
**Tests:** 225 passing (up from 213 at Phase 12 close)

---

## Successes

- All five deliverables landed cleanly.
- PHP parser correctly handles both `public function` class methods and global/free functions (implicitly public in PHP). The alternation regex approach proved more correct than the negative-lookahead alternative attempted in a competing remote commit.
- Swift parser correctly restricts to `public`/`open`/`internal`/unqualified declarations — consistent with the project-wide convention established by other parsers. Gemini flagged this inconsistency promptly; fixed same cycle.
- `ctx diff --since <ref>` is a natural extension of the existing diff command with zero new architecture.
- Non-git mtime fallback makes `ctx diff` useful outside of git repos without breaking the primary git flow. The warning on stderr prevents silent unexpected behaviour.
- README idempotency note closes a long-standing documentation gap (`ctx init` unconditional vs. `ctx init --no-overwrite` incremental).
- Gemini code review caught two real issues this cycle: Swift `private` leak and PHP `public function` miss in remote attempt. Both fixed before merge.

## Friction Points

- The PHP regex merge conflict revealed that two concurrent fix approaches were applied to the same line (our alternation vs. remote negative-lookahead). Resolved by keeping ours (which correctly matches `public function foo()`), but the conflict required manual resolution.
- PHP parser captures all `class` names regardless of visibility (no `public` modifier on class declarations in PHP — classes are public by default). This is correct behaviour but differs visually from Java/C# patterns.
- Swift `fileprivate` and `private` exclusion is a deliberate tradeoff; private methods won't appear in context. For frameworks with lots of internal extension methods, this may under-represent the file's surface.

## Observations

- Language parser count: 10 (Python, JS/TS, Rust, Go, Java, C#, Kotlin, Ruby, PHP, Swift). The parser surface is now broad enough to cover the majority of real-world projects encountered in the wild.
- The `ctx diff` command now has two paths (git and mtime) and three output modes (`[mod]`, `[new]`, `[stale]`). A future refactor could unify the output format.
- Test count 213 → 225 (+12). Twelve tests for five deliverables is a healthy ratio.

## Suggestions for Phase 14

### Carry-forward (must include)
*(None — all Phase 13 items from the Phase 12 reflection were addressed.)*

### New suggestions
1. **Unified `ctx diff` output format** — use consistent prefixes across git and mtime paths (e.g., `[changed]` / `[new]` / `[stale]` → always one of `mod`, `new`, `stale`). Currently `[mod]`/`[new]` (git) vs. `[stale]` (mtime) are inconsistent.
2. **`ctx diff --format json`** — machine-readable output for CI pipelines and scripting.
3. **`ctx export` command** — concatenate all `CONTEXT.md` files into a single output (stdout or file) for feeding into a one-shot LLM prompt. Common pattern in practice.
4. **`ctx stats` command** — summary of manifest coverage: total dirs, covered, missing, stale, total tokens across all manifests (read from frontmatter).
5. **Elixir parser** — `def`/`defp`, `defmodule`, `defstruct`. Becoming common in backend systems.
6. **`--version` in `.ctxconfig`** — allow pinning a minimum `ctx` version to catch configuration drift when upgrading.

## Disposition of Suggestions

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | Unified `ctx diff` output format | Carry into Phase 14 |
| 2 | `ctx diff --format json` | Carry into Phase 14 |
| 3 | `ctx export` command | Carry into Phase 14 |
| 4 | `ctx stats` command | Carry into Phase 14 |
| 5 | Elixir parser | Carry into Phase 14 |
| 6 | `--version` in `.ctxconfig` | Defer — low usage value relative to config complexity |
