# Phase 29 & MCP Resources Reflection — Preflight Onboarding and `.ctx/` Resource Surface

**Date:** 2026-10-29
**Branch:** `main`
**Tests:** 538 passing

## Successes

- **Comprehensive preflight gate (`ctx setup --check`).** `src/ctx/preflight.py` executes 7 ordered readiness checks (provider detection, config resolution, live provider connectivity including local `/v1/models` validation, sample single-file model summary quality, target directory writability, git repo detection, and `.ctxignore` presence) with actionable `Fix:` guidance and full human + JSON OutputBroker support.
- **Google Drive shortcut ignore rules.** Added `.gdoc`, `.gsheet`, `.gslides`, `.gdraw`, `.gform`, `.gmap`, and `.gsite` to both `src/ctx/.ctxignore.default` and repo-root `.ctxignore.default` with automated parity verification.
- **Read-only MCP resources for `.ctx/` exports.** Extended `src/ctx/mcp_server.py` with `resources/list` and `resources/read` handlers exposing `ctx://.ctx/CONTEXT.md`, `ctx://.ctx/CONTEXT-1.md`, `ctx://.ctx/CONTEXT-0.md`, and `ctx://.ctx/metadata.json`, with structured errors when `.ctx/` is uninitialized or when an unknown/traversal URI is requested.

## Friction Points

- **Ambient parent `.ctxconfig` bleed in tests.** Because `tests/conftest.py` places `tmp_path` inside `<repo>/.tmp/test-work/<uuid>`, `load_config()` walking `start_dir.parents` all the way to `/` picked up an ancestor `/central/repos/active/.ctxconfig` file outside the repository, causing 6 config/setup tests to fail and probe a live local Ollama port.
- **Dual `.ctxignore.default` drift.** Repo-root `.ctxignore.default` and `src/ctx/.ctxignore.default` were maintained as separate files without a test asserting they stay identical.
- **Mock-only coverage of preflight helpers.** Existing `run_preflight` tests mocked `probe_model_quality()` and `_probe_local_models()` without direct unit tests exercising those helpers' internal branches.

## Observations

- Extracting `_iter_config_dirs()` in `src/ctx/config.py` (and reusing it in `src/ctx/preflight.py`) allowed `tests/conftest.py` to cleanly bound config discovery to the per-test sandbox without changing production semantics.
- Supporting both canonical `ctx://.ctx/<name>` URIs and relative `.ctx/<name>` shorthands in `resources/read` makes the MCP resource layer resilient to varying client URI conventions while preserving a strict allowlist.

## Suggestions

1. **Isolate upward `.ctxconfig` parent traversal via `_iter_config_dirs()`** — Prevent ambient `.ctxconfig` files above the repository or test sandbox from polluting test runs.
2. **Enforce parity between root `.ctxignore.default` and `src/ctx/.ctxignore.default`** — Add a regression test ensuring both default ignore files remain identical.
3. **Add direct unit tests for `probe_model_quality()` and `_probe_local_models()`** — Cover valid, empty/short, timeout, exception, and empty-model-list branches directly in `tests/test_preflight.py`.
4. **Surface `.ctx/hook_log.json` telemetry in MCP resources or `ctx check`** — Once `ctx init` background hooks accumulate real dogfooding runs, expose hook telemetry so agents and operators can spot background refresh failures without inspecting `.ctx/hook_log.json` manually.

## Implications For The Next Phase

- Onboarding preflight and passive MCP resource discovery are now in place for live Sprint 2 dogfooding (Phase 27) and `ctx-sdk` extraction.

## Disposition Table

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | Isolate upward `.ctxconfig` parent traversal via `_iter_config_dirs()` | Implemented this gate |
| 2 | Enforce parity between root `.ctxignore.default` and `src/ctx/.ctxignore.default` | Implemented this gate |
| 3 | Add direct unit tests for `probe_model_quality()` and `_probe_local_models()` | Implemented this gate |
| 4 | Surface `.ctx/hook_log.json` telemetry in MCP resources or `ctx check` | Carry into Phase 30 |
