# Phase 16 Handoff

This file is the execution contract for the current Phase 16 work.

It exists to make the next set of changes small, explicit, and safe for narrower models such as `kimi2.5` and `qwen`.

## Findings To Close

The March 14, 2026 repo review surfaced four gaps that must be closed in addition to the carried-forward Phase 15 backlog:

1. Generated manifests previously surfaced low-signal workspace noise such as `.pytest_cache/` and `.worktrees/`. This was closed in the handoff-prep pass.
2. `ctx serve` relies on process `cwd` instead of an explicit served root.
3. `ctx export` does not yet respect `.ctxignore`, so export output can drift from generation/update output. **Closed in Gate 16D.**
4. Core docs had drifted from repo truth (provider support, command surface, current roadmap focus).

## Read Order

Read these files before starting any Phase 16 gate:

1. `AGENTS.md`
2. `state.md`
3. `architecture.md`
4. This file
5. The gate-specific code and test files listed below

## Global Guardrails

- One gate per branch and one gate per PR.
- Do not broaden scope beyond the gate's file list without updating `AGENTS.md`, `state.md`, and this file.
- Do not change hashing, manifest frontmatter, or prompt templates unless the gate explicitly requires it.
- Do not add new dependencies unless the gate explicitly requires it.
- Update touched docs in the same gate as the behavior change.
- If a gate exposes a durable workflow lesson, carry it into `AGENTS.md`, `RUNBOOK.md`, or `CONTRIBUTING.md` before closing the gate.
- End every gate with a short handoff note: what changed, what remains, what was not validated.

## Recommended Gate Order

| Gate | Recommended Branch | Primary Outcome |
|------|--------------------|-----------------|
| `16A` | `docs/phase16a-handoff` | Docs match repo truth and the handoff contract is published. ✓ |
| `16B` | `feat/phase16b-ignore-hygiene` | Completed in the handoff-prep pass; default ignore rules now skip obvious workspace noise. ✓ |
| `16C` | `feat/phase16c-clean-dry-run` | `ctx clean --dry-run` previews deletions without removing files. ✓ |
| `16D` | `feat/phase16d-export-ignore` | `ctx export` respects `.ctxignore` in every export mode. ✓ |
| `16E` | `feat/phase16e-verify` | `ctx verify` reports malformed or incomplete manifests. |
| `16F` | `feat/phase16f-serve-root` | `ctx serve` serves an explicit root instead of implicit `cwd`. |
| `16G` | `feat/phase16g-stats-json` | `ctx stats --format json` emits stable machine-readable output. |
| `16H` | `feat/phase16h-diff-stat` | `ctx diff --stat` prints one-line counts instead of file lists. |
| `16I` | `feat/phase16i-watch-status` | `ctx watch` prints a one-line coverage summary after each refresh. |
| `16Z` | `chore/phase16-closeout` | Manifests refreshed, docs synced, validation rerun, reflection filed. |

## Gate 16A - Docs Truth Sync And Handoff Prep

Status: seeded by this planning pass. Treat it as the baseline for later gates.

Files in scope:

- `README.md`
- `architecture.md`
- `rules.md`
- `RUNBOOK.md`
- `CONTRIBUTING.md`
- `AGENTS.md`
- `state.md`
- `PHASE16_HANDOFF.md`

Tasks:

1. Remove stale documentation claims.
2. Publish the Phase 16 execution order in a durable place.
3. Add small-model guardrails to the standing docs.
4. Link the handoff plan from contributor-facing docs.

Done when:

- The provider list matches current code.
- The command surface matches current code.
- Phase 16 has an explicit gate order.
- Contributors can discover this file from the main docs.

## Gate 16B - Ignore Hygiene

Goal: close the manifest-noise finding without changing ignore semantics beyond obvious workspace noise.

Status: completed in the handoff-prep pass.

Observed symptom in the current workspace: Windows can raise `PermissionError` while traversing `.pytest_cache`, so this gate improves both signal quality and traversal reliability.

Files in scope:

- `.ctxignore.default`
- `src/ctx/.ctxignore.default`
- `tests/test_ignore.py`
- Docs touched by the default ignore behavior

Tasks:

1. Add `.pytest_cache/` and `.worktrees/` to the default ignore set.
2. Add tests that assert those directories are ignored by default.
3. Document the new defaults where the ignore behavior is described.

Do not:

- Add broad new ignore classes unless they are clearly workspace noise.
- Change user `.ctxignore` merge behavior.
- Change traversal or hashing logic.

Validation:

- `python -m pytest tests/test_ignore.py`

Done when:

- Default ignore tests cover the new patterns.
- A refreshed root manifest no longer surfaces `.pytest_cache/` or `.worktrees/`.

## Gate 16C - `ctx clean --dry-run`

Goal: make destructive cleanup previewable before any files are removed.

Files in scope:

- `src/ctx/cli.py`
- `tests/test_cli.py`
- `README.md`
- `RUNBOOK.md`

Tasks:

1. Add a `--dry-run` flag to `ctx clean`.
2. Print the manifest count and the paths that would be deleted.
3. Ensure dry-run mode performs no deletions and requires no confirmation prompt.

Do not:

- Change actual delete semantics outside the dry-run path.
- Add unrelated clean filters.

Validation:

- `python -m pytest tests/test_cli.py -k "clean"`

Done when:

- `ctx clean --dry-run` prints a preview and exits `0`.
- Real deletes still require confirmation unless `--yes` is passed.

## Gate 16D - `ctx export` Respects `.ctxignore`

Goal: make export output use the same ignore boundary as generation and update.

Files in scope:

- `src/ctx/cli.py`
- `tests/test_cli.py`
- `README.md`
- `RUNBOOK.md`
- `rules.md`

Tasks:

1. Thread `load_ignore_patterns()` / `should_ignore()` through every export walk.
2. Make sure `all`, `stale`, `missing`, and `depth` modes all respect the same ignore boundary.
3. Keep output format unchanged except for the removed ignored paths.

Do not:

- Move export into a new module unless the current file becomes clearly unmanageable.
- Change generation/update ignore behavior.

Validation:

- `python -m pytest tests/test_cli.py -k "export"`

Done when:

- Ignored directories never appear in export output.
- Export behavior matches generation/update visibility rules.

## Gate 16E - `ctx verify`

Goal: add a read-only integrity check for manifest frontmatter.

Files in scope:

- `src/ctx/cli.py`
- `src/ctx/manifest.py` only if a small helper is needed
- `tests/test_cli.py`
- `tests/test_manifest.py`
- `README.md`
- `RUNBOOK.md`

Required command behavior:

- `ctx verify PATH`
- Output one line per invalid manifest.
- Report malformed frontmatter separately from missing required fields.
- Exit `0` when all manifests are valid.
- Exit `1` when any manifest is invalid.

Required fields:

- `generated`
- `generator`
- `model`
- `content_hash`
- `files`
- `dirs`
- `tokens_total`

Do not:

- Auto-fix manifests.
- Change manifest schema.

Validation:

- `python -m pytest tests/test_manifest.py tests/test_cli.py -k "verify or manifest"`

Done when:

- Invalid manifests are easy to identify from CLI output.
- Exit codes support CI use without extra flags.

## Gate 16F - Explicit `ctx serve` Root

Goal: close the serve-root finding and remove implicit `cwd` coupling.

Files in scope:

- `src/ctx/cli.py`
- `src/ctx/server.py`
- `tests/test_server.py`
- `tests/test_cli.py`
- `README.md`
- `architecture.md`
- `RUNBOOK.md`

Tasks:

1. Add an explicit path argument to `ctx serve`.
2. Thread that root path into the server startup path.
3. Make request paths resolve relative to the served root, not `Path.cwd()`.
4. Preserve traversal protection.
5. Update tests to use repo-relative requests instead of absolute filesystem paths.

Do not:

- Redesign the server protocol.
- Add authentication or multi-root serving.

Validation:

- `python -m pytest tests/test_server.py tests/test_cli.py -k "serve or mcp_context"`

Done when:

- The served tree is explicit in CLI usage.
- The same tree can be served from any working directory.
- Traversal outside the served root is still blocked.

## Gate 16G - `ctx stats --format json`

Goal: add a stable machine-readable stats surface.

Files in scope:

- `src/ctx/cli.py`
- `tests/test_cli.py`
- `README.md`
- `RUNBOOK.md`

Tasks:

1. Add `--format json` to `ctx stats`.
2. Keep the text output unchanged when `--format` is not passed.
3. Make verbose JSON include both aggregate totals and per-directory rows.

Do not:

- Change the meaning of existing text fields.
- Add extra output around the JSON payload.

Validation:

- `python -m pytest tests/test_cli.py -k "stats"`

Done when:

- JSON output is valid and deterministic.
- Aggregate values match the text-mode totals.

## Gate 16H - `ctx diff --stat`

Goal: add a one-line diff summary for CI and operator use.

Files in scope:

- `src/ctx/cli.py`
- `tests/test_cli.py`
- `README.md`
- `RUNBOOK.md`

Required behavior:

- Git mode prints `N modified, N new`.
- Mtime fallback prints `N stale`.
- `--stat` is text-only and should not be combined with `--format json`.

Do not:

- Change existing `--quiet` semantics.
- Expand this gate into a broader diff rewrite.

Validation:

- `python -m pytest tests/test_cli.py -k "diff"`

Done when:

- Summary counts are available without listing file paths.
- Existing diff modes still behave as before.

## Gate 16I - `ctx watch` Coverage Line

Goal: give users immediate coverage feedback after each debounced refresh.

Files in scope:

- `src/ctx/watcher.py`
- `src/ctx/generator.py` only if a small shared status helper is required
- `tests/test_watcher.py`
- `README.md`
- `RUNBOOK.md`

Tasks:

1. After each debounced `update_tree()` call, print a one-line coverage summary.
2. Reuse existing status logic instead of re-implementing stale detection if possible.
3. Keep existing change-detected and refreshed/error lines intact.

Do not:

- Change debounce behavior.
- Add background threads beyond the existing watcher flow.

Validation:

- `python -m pytest tests/test_watcher.py`

Done when:

- Each successful watch cycle prints a compact coverage line.
- Ignored and `CONTEXT.md` events still do not trigger refreshes.

## Gate 16Z - Closeout

This gate happens only after `16B` through `16I` land.

Files in scope:

- Touched source files
- Touched docs
- Regenerated `CONTEXT.md` files
- Reflection artifact in `archive/reflections/`

Tasks:

1. Run the targeted tests from every landed gate.
2. Run the full test suite.
3. Run `ctx update .` and confirm `ctx status .` is clean.
4. File the Phase 16 reflection artifact using `GATE_CLOSEOUT.md`.
5. Carry any deferred work into the next phase before marking Phase 16 complete.

Stop and report if:

- The environment cannot run tests.
- No LLM provider is available for the manifest refresh.
- Any canonical rule conflicts with the closeout work.
