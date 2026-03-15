# Phase 14 Reflection — CLI Completeness

**Date:** 2026-03-14
**Branch:** `feat/phase14-cli-completeness`
**Tests:** 237 passing (up from 213 at Phase 13 close)

---

## Successes

- All five deliverables landed in a single commit with no rework required.
- Unified diff vocabulary (`[mod]`/`[new]`/`[stale]`) gives users a clear mental model across both code paths (git and mtime) without adding extra flags.
- `ctx diff --format json` outputs clean, machine-readable JSON in both the git path (`{"modified":[…],"new":[…]}`) and the mtime fallback path (`{"stale":[…]}`). CI consumers can parse this without text scraping.
- `ctx export` is a one-command answer to "give me all context for this repo" — useful for passing full context to an LLM in a single prompt. The `# path/CONTEXT.md` header convention is unambiguous and easy to parse.
- `ctx stats` fills a meaningful gap: users could not previously see aggregate coverage at a glance. The five-field output (dirs, covered, missing, stale, tokens) is easy to read and script.
- Elixir parser follows the established project convention exactly: `def` (public only, `defp` excluded), `defmodule`, `defstruct`; wired for `.ex` and `.exs`. Struct association to the file's modules is a nice touch for files with one module per file (the idiomatic Elixir pattern).
- Test count growth from Phase 13 to Phase 14: 213 → 237 (+24). Healthy ratio consistent with prior phases.

## Friction Points

- `ctx stats` walks all directories unconditionally — there is no way to scope it to a subdirectory other than by passing a path argument. The output is flat (no per-directory breakdown), so for large monorepos the summary collapses too much detail.
- `ctx export` reads all `CONTEXT.md` files without any filtering. Users who only care about stale or uncovered manifests have to post-process the output.
- `ctx diff --format json` exits 0 regardless of whether there are changes. In CI pipelines where the goal is "fail if anything is stale", users currently need to parse the JSON and check array lengths. A `--quiet` / exit-code mode would close this gap.
- The Elixir `_DEF` regex matches `def` at any indentation level, which is correct for nested modules but could theoretically match `def` inside a string or heredoc. This is the same pragmatic trade-off made in all other regex-based parsers in the project.
- Elixir module-level attributes (`@type`, `@spec`, `@callback`) are not extracted. These are meaningful public API signals in library code.

## Observations

- Language parser count is now 9 (Python, JS/TS, Rust, Go, Java, C#, Kotlin, Ruby, Elixir). The regex + dict pattern remains consistent and readable.
- `ctx stats` and `ctx export` are purely read-only commands (no LLM calls, no file writes except for `export --output`). They do not need `require_api_key=False` because they never call `load_config`. This is a clean design — no accidental key requirement.
- The `ctx diff --format json` dual output schema (git path vs mtime path) means consumers must check which keys are present. This is a minor inconsistency; a future refactor could unify under `{"modified":[…],"new":[…],"stale":[…]}` with empty arrays for absent categories.

## Suggestions for Phase 15

1. **`ctx stats` per-directory breakdown** — add a `--verbose` flag that prints a row per directory (path, covered/missing/stale status, token count) in addition to the totals, making the command useful for monorepo auditing.
2. **`ctx export --filter stale`** — add a `--filter` option accepting `stale`, `missing`, or `all` (default) so users can export only the manifests that need attention.
3. **`ctx diff --format json` exit-code mode** — add a `--quiet` flag (or `--exit-code`) that suppresses output and exits 1 if any changes are found; enables zero-config CI gating without JSON parsing.
4. **Elixir `@type`/`@spec`/`@callback` extraction** — extend the Elixir parser to capture module-level attributes so library API surfaces are fully represented.
5. **`ctx clean` command** — add `ctx clean [path]` to remove all `CONTEXT.md` files under a directory tree, providing a quick "reset to zero" for users who want to regenerate from scratch with a different model or config.
6. **`ctx export --depth N`** — add a `--depth` option that limits the rglob to N levels of nesting, useful for exporting only top-level or mid-level manifests without the full tree.

## Disposition of Suggestions

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | `ctx stats` per-directory breakdown (`--verbose`) | Carry into Phase 15 |
| 2 | `ctx export --filter stale` | Carry into Phase 15 |
| 3 | `ctx diff --format json` exit-code mode (`--quiet`) | Carry into Phase 15 |
| 4 | Elixir `@type`/`@spec`/`@callback` extraction | Carry into Phase 15 |
| 5 | `ctx clean` command | Carry into Phase 15 |
| 6 | `ctx export --depth N` | Carry into Phase 15 |
