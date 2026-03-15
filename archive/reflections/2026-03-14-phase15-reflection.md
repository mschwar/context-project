# Phase 15 Reflection — CLI Power-User Features

**Date:** 2026-03-14
**Branch:** `feat/phase15-cli-power-user`
**Tests:** 249 passing (up from 237 at Phase 14 close)

---

## Successes

- All six deliverables landed cleanly with no rework required.
- `ctx stats --verbose` transforms the command from a blunt coverage number into a genuine monorepo audit tool. The per-directory breakdown table gives users an actionable view of exactly which directories need attention without having to walk the tree manually.
- `ctx export --filter all/stale/missing` closes a real usability gap: users piping export output to an LLM now pay only for the manifests that matter rather than dumping the entire tree.
- `ctx diff --quiet` completes the CI story. The chain `ctx diff --quiet || ctx update . && ctx diff --quiet` is now a valid, zero-config pipeline step — no JSON parsing, no shell gymnastics.
- Elixir `@type`/`@spec`/`@callback` extraction rounds out the Elixir parser to full library-API coverage. This is the first parser in the project that captures type-system annotations, which is meaningful for Elixir library code where specs double as documentation.
- `ctx clean [--yes]` is a natural complement to `ctx update`. The pattern of --yes to skip confirmation is consistent with existing destructive flags in other tools (e.g., `rm`, `pip uninstall`), so it requires no learning.
- `ctx export --depth N` is a low-cost implementation (simple path-component count check on each match) with high value for large monorepos: users can get a "top-level overview" export without pulling in thousands of leaf manifests.
- Gemini review added genuine value: the `import os` placement fix follows Python convention, and extracting `_missing_dir_labels()` and `_filter_stale_manifests()` makes the export logic testable in isolation.
- Test count growth: 237 → 249 (+12). Steady and proportionate to the deliverable count.

## Friction

- **Rebase conflict from remote Gemini review commit.** The Gemini review was applied as a remote commit on `main` after the Phase 15 branch had already diverged. Rebasing the branch onto the updated `main` produced a conflict in `export.py` that required manual resolution. This is a workflow hazard when a review pass lands asynchronously: the branch author has to reconcile two sets of changes to the same file. A mitigation is to apply Gemini review suggestions in a short-lived commit on the feature branch before the review is merged to main, so both sets of changes coexist locally and the rebase is trivial.
- `ctx export` still uses an unconstrained `rglob("CONTEXT.md")` as its base scan. The `--filter` option filters the *results* but the walk itself ignores `.ctxignore`. A directory that the user has explicitly excluded from `ctx update` will still appear in export output unless `--filter missing` happens to exclude it by coincidence. This inconsistency is a latent confusion point.
- `ctx clean` deletes files without a `--dry-run` preview. The `--yes` flag prevents the interactive prompt, but there is no way to see what *would* be deleted without actually deleting it. Users operating in large trees have no safety net short of running `ctx export --filter all` to inventory manifests beforehand.
- The `ctx stats --verbose` breakdown table and the `ctx stats` aggregate table are rendered as separate blocks. For terminals narrower than ~80 characters the table columns can wrap. No width-awareness or truncation logic exists yet.

## Suggestions for Phase 16

1. **`ctx stats --format json`** — add a `--format json` flag to `ctx stats` (both aggregate and `--verbose` modes) that emits machine-readable JSON. This enables coverage dashboards, badge generators, and CI scripts to consume stats without parsing table text.
2. **`ctx clean --dry-run`** — add a `--dry-run` flag that lists the `CONTEXT.md` files that *would* be deleted without removing them. Closes the safety gap noted in Friction; mirrors the `ctx update --dry-run` pattern already in the project.
3. **`ctx export` respects `.ctxignore`** — thread the existing `pathspec`-based ignore logic through the `rglob` walk in `export.py` so that directories excluded from `ctx update` are also excluded from `ctx export`. Eliminates the silent inconsistency between the two commands.
4. **`ctx watch` integration: show stale count on each update** — after each debounced `update_tree` call, print the output of `ctx stats` (single-line summary) or emit the stale count so users get continuous coverage feedback without running a separate command.
5. **`ctx verify` command** — add a `ctx verify [path]` command that reads each `CONTEXT.md` frontmatter, confirms all required fields are present (`generated`, `generator`, `model`, `content_hash`, `files`, `dirs`, `tokens_total`), and reports any manifests with missing or malformed fields. Useful after manual edits or cross-repo copies.
6. **`ctx diff --stat`** — add a `--stat` flag that prints a one-line summary count (`3 modified, 1 new, 0 stale`) rather than the full file list. Mirrors `git diff --stat` semantics and is more readable in CI log output.

## Disposition of Suggestions

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | `ctx stats --format json` | Carry into Phase 16 |
| 2 | `ctx clean --dry-run` | Carry into Phase 16 |
| 3 | `ctx export` respects `.ctxignore` | Carry into Phase 16 |
| 4 | `ctx watch` integration: show stale count on each update | Carry into Phase 16 |
| 5 | `ctx verify` command | Carry into Phase 16 |
| 6 | `ctx diff --stat` | Carry into Phase 16 |
