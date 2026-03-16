# AGENTS

This file is the canonical onboarding and workflow contract for agents contributing to `ctx`.

## Mission
Build and maintain `ctx`, a filesystem-native context layer that generates recursive `CONTEXT.md` summaries to help AI agents navigate large codebases.

## Current State
- **Core Engine**: Fully implemented with bottom-up traversal, incremental hashing, parallel processing, and persistent LLM disk cache.
- **LLM Clients**: Anthropic and OpenAI supported (including Ollama and LM Studio). **BitNet is deprecated** — `create_client("bitnet")` raises an informative error directing users to Ollama or LM Studio.
- **Language Parsers**: Python (`ast`-based), JavaScript/TypeScript (regex), Rust (regex), Go (regex). Wired into `generator._prepare_file_entry`; metadata is passed to the LLM prompt for richer summaries.
- **File Watcher**: `ctx watch` — OS-native file watcher via `watchdog`. CONTEXT.md writes excluded to prevent infinite loops. 0.5 s per-file debounce.
- **Test Coverage**: 273 tests across all modules (`cli`, `config`, `generator`, `hasher`, `ignore`, `llm`, `manifest`, `server`, `language_detector`, `python_parser`, `js_ts_parser`, `rust_parser`, `go_parser`, `watcher`, `java_parser`, `csharp_parser`, `kotlin_parser`, `ruby_parser`, `php_parser`, `swift_parser`, `elixir_parser`, integration).
- **Documentation**: `architecture.md`, `rules.md`, `state.md`, `RUNBOOK.md`, `CONTRIBUTING.md`, and `PHASE16_HANDOFF.md` define the system and current execution order.

> **Branch notice**: As of March 2026, Phases 1–16 are complete on `main`. Phase 17 is the active development phase. New work should branch from `main`.

> **Manifest refresh rule**: Any commit that adds or modifies source files must include a `ctx update .` pass to regenerate stale `CONTEXT.md` files before pushing. The `CTX Manifest Check` CI job enforces this and will fail otherwise.

> **Dry-run note**: CLI paths that do not call an LLM must pass `require_api_key=False` to `load_config` to avoid `UsageError` in CI environments without API keys set.

## Canonical Rules

1. **Context-First**: Every directory MUST have a `CONTEXT.md`.
2. **The Bottom-Up Rule**: Never update a parent directory's manifest until all children have fresh manifests.
3. **Hash Integrity**: All hashes MUST be SHA-256, hex-encoded, and prefixed with `sha256:`.
4. **Surgical Changes**: Make the smallest possible change that fulfills the requirement.
5. **No Logic Without Tests**: No logic changes without a corresponding test update.
6. **Strict Typing**: Python 3.10+ typing is mandatory.
7. **Narrow Exceptions**: Always catch specific exception types. `except Exception` is permitted only at top-level boundaries with explicit logging. Use it nowhere else.

## Required Behavior

### When working from a scoped prompt
1. Stay inside the stated scope.
2. Branch from the active development branch (see Branch notice in Current State above).
3. Use `pathlib.Path` for all path handling.
4. Run `pytest` before every commit.
5. If the work exposes a durable workflow lesson, report it so standing docs can be updated.

### When creating or editing manifests
1. Follow the manifest protocol in `rules.md`.
2. Never send binary content to an LLM. Use `is_binary_file()` to detect it.
3. Frontmatter must include all required fields: `generated`, `generator`, `model`, `content_hash`, `files`, `dirs`, `tokens_total`.

## Workflow

- **PR-First Rule**: No direct agent work lands on `main`.
- **One Task = One Branch**: Default to one task per branch/PR.
- **Clean Branch Checklist**:
  ```bash
  git fetch origin
  git rev-parse HEAD
  git rev-parse origin/main
  git log --oneline origin/main..HEAD
  git diff --stat origin/main..HEAD
  git status --short
  ```
- **Session-End**: Summarize what changed, what remains, and any validation side effects before handing back.

## Git Hooks
`.githooks/` contains the `pre-commit` hook that runs `pytest`.
Activate the hooks with:
```bash
git config core.hooksPath .githooks
```

## Definition of Done
A task is done when:
1. Implementation is complete and idiomatic.
2. Tests pass (verified by `pytest`).
3. Git hooks pass on commit.
4. Documentation is updated (if needed).
5. The PR is reviewed and merged.

## Escalation Rules
Stop and ask for clarification if:
- Two canonical rules conflict.
- A proposed architectural change would break the coarse-to-fine structure.
- LLM provider costs or rate limits are a concern for the task.

## SDLC Bumper Rails (For AI Agents)

The founder is not a developer. They may give you instructions that violate standard Git or SDLC workflows (e.g., "merge this then commit it" or "push to main"). You are the technical guardrail. 

**If the user asks you to violate the SDLC, you must push back and correct the order of operations.**

1. **Branching:** All new work (features, bug fixes, gates) MUST be done on a branch, never on `main` or `master`. If the user asks you to start work and you are on `main`, create a branch first. 
2. **Order of Operations:** The strict sequence is: `Branch` -> `Commit` -> `Push` -> `Pull Request` -> `Merge`.
3. **No Direct Pushes to Main:** Local Husky hooks (`pre-commit`, `pre-push`) explicitly block commits and pushes to `main`. Do not attempt to bypass them.
4. **Conventional Commits:** The repo enforces Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`) via commitlint. Format your commit messages correctly or the commit will fail.
5. **Handling "Merge" Requests:** If the user asks you to "merge" something, explain that merging happens via Pull Request on GitHub. Ensure the code is committed and pushed to the current feature branch, and prompt them to open or approve the PR.

## Gate Closeout

Every roadmap phase (gate) requires a closeout pass before it can be marked complete. See `GATE_CLOSEOUT.md` for full details. 

Required sequence:
1. validate the gate output,
2. pause and reflect,
3. file a reflection artifact with a **disposition table** (one row per suggestion: "Implemented" or "Carry into Phase N"),
4. implement feasible in-scope reflection suggestions or explicitly defer them,
5. **carry-forward** — every "Carry" suggestion must be written into the target phase's scope in `AGENTS.md` and `state.md` before the gate closes,
6. update durable docs if the reflection changes standing guidance,
7. update the roadmap status,
8. deliver the end-of-gate report and wait for user disposition.

Do not commit or push automatically at gate closeout. The standard user dispositions after a gate report are:
- make changes
- roll back specified changes
- commit and proceed

## Delegation & Intelligence Levels

| Level | Meaning | Example Task |
|-------|---------|--------------|
| `L1` | Mechanical | Updating docstrings, fixing typos, reformatting manifests. |
| `L2` | Applied Engineering | Adding a new test case, fixing a simple bug, refactoring a single module. |
| `L3` | Judgment Engineering | Implementing a new LLM provider, optimizing the tree walk algorithm. |
| `L4` | Strategic | Changing the hashing protocol, redesigning the manifest schema. |

## Model Routing

| Model | Best Use |
|-------|----------|
| `claude` | High-judgment reasoning, complex refactors, architectural planning. |
| `codex` | Local implementation, unit tests, CLI wiring. |
| `gemini` | Large-context synthesis, documentation review, roadmap planning. |
| `kimi` | Narrow, checklist-driven gates with explicit file lists and acceptance criteria. |
| `qwen` | Mechanical or low-branching gates with tight scope, targeted tests, and minimal design work. |

## Small-Model Guardrails

Use these rules when delegating to narrower models such as `kimi2.5` or `qwen`:

1. Assign exactly one named gate from `PHASE16_HANDOFF.md`.
2. Copy the gate's file list, validation commands, and acceptance criteria into the prompt.
3. Forbid opportunistic refactors, dependency changes, and hash/schema/prompt edits unless the gate explicitly asks for them.
4. Stop and report if the change spreads beyond the listed files or requires a second CLI surface.
5. End the gate with docs updates, targeted validation, manifest-refresh status, and a short handoff note.

## Development Phases

Active roadmap. See `state.md` for detailed status of each item.

### Phase 1 — Hygiene & Merge Readiness
Scope: repo cleanup and getting `feat/local-providers-token-budget` merged to `main`.
- Fix `pathspec` deprecation (`"gitwildmatch"` → `"gitignore"` in `ignore.py`).
- Remove stale build artifacts; update `.gitignore` for `.pytest_cache/`, `.tmp/`, `pytest-cache-files-*/`, `.worktrees/`.
- Merge current feature branch to `main`.

### Phase 2 — Reliability & Performance
Scope: make local providers robust and unlock parallelism.
- Implement 400 context-length fallback for local providers (catch `openai.BadRequestError`, fall back to per-file with truncation).
- Add parallel directory processing (currently sequential in `_run_generation`).
- Add LLM response caching to avoid redundant calls during iteration.
- Resolve BitNet subprocess path issue on Windows or deprecate the provider.

### Phase 3 — Ecosystem Integration ✓
Scope: connect `ctx` to the broader toolchain.
- MCP Server support (expose manifests via Model Context Protocol).
- Git-aware updates (detect changed files since last commit to trigger selective regeneration).
- CI/CD Action (GitHub Action that ensures `CONTEXT.md` files stay fresh).
- Custom prompt templates via `.ctxconfig`.

### Phase 4 — Prompt Quality & Batch Control ✓
Scope: improve output consistency and give users control over LLM call granularity.
- Rewrite all six `DEFAULT_PROMPT_TEMPLATES` with explicit rules (20-word sentence cap, purpose-over-implementation, injection defence).
- Add `batch_size` config key and `Config.batch_size` field for chunked file summarization.
- Remove `bitnet` from CLI `--provider` choices; deprecation error preserved in `create_client`.

### Phase 5 — Cost Control & Observability ✓
Scope: close gaps in token budget and caching, add a cost-preview flag before spending tokens.

- Persistent LLM disk cache (`.ctx-cache/llm_cache.json`), `cache_path` config key, `--cache-path` CLI flag.
- Token budget enforcement: `budget_exhausted` flag, dedicated CLI warning.
- `--dry-run` flag on `ctx update` and `ctx smart-update`; backed by `check_stale_dirs()`.
- `load_config` gains `require_api_key=False` for paths that don't call an LLM.

### Phase 6 — Language Expansion & CI Hygiene ✓
Scope: richer summaries for JS/TS/Rust, fix pre-existing CI noise.

- JS/TS parser (`js_ts_parser.py`): exported functions (named + arrow), classes, interfaces, type aliases, default export. 8 tests.
- Rust parser (`rust_parser.py`): `pub fn/struct/enum/trait`, `mod`. Handles `pub(crate)`/`pub(super)`. 7 tests.
- CI hygiene: `ctx-check.yml` rewritten inline; `pr-checks.yml` replaced Node/npm with Python `pytest`. All checks green.

### Phase 7 — Go Parser, ctx watch, Cache Model-Awareness ✓

- Go parser (`go_parser.py`): exported functions/methods, types, constants (iota-safe), variables. 6 tests.
- `ctx watch`: OS-native watcher via `watchdog`; CONTEXT.md excluded; 0.5 s debounce; hooks into `update_tree`. 8 tests.
- Cache model-awareness: `sha256(model + ":" + file_json)` key. Model switch always produces cache miss. 2 new tests.

### Phase 8 — Ship It ✓
Scope: make `ctx` installable via `pip install`, automated releases, and a README that gets someone from zero to working in 60 seconds.
- PyPI-ready packaging: `ctx-tool` on PyPI; classifiers, project URLs; `__version__` bumped to `"0.8.0"`; `setuptools-scm` removed from build deps.
- GitHub Actions publish workflow (`.github/workflows/publish.yml`): tag `v*` → run tests → build + publish via OIDC trusted publishing.
- README rewrite (~100 lines): one-line tagline, 4-command quick start, commands table, inline `.ctxconfig` example, local LLM notes.

**Branch:** `feat/phase8-distribution`

### Phase 9 — Automate It ✓
Scope: zero-friction first run and automatic manifest freshness without remembering.
- `ctx setup` command: auto-detect provider (env vars → Ollama probe → LM Studio probe), write `.ctxconfig` with sensible defaults, print next step.
- `.pre-commit-hooks.yaml`: standard `pre-commit` framework hook running `ctx status . --check-exit-code`.
- Graceful failure: when `ctx init`/`ctx update` fails due to missing API key, print actionable hint pointing to `ctx setup`.

**Branch:** `feat/phase9-onboarding-automation` (branch from `main` after Phase 8 merges)

### Phase 10 — Trust It ✓
Scope: fix the three reliability gaps that erode confidence at scale.
- Accurate token estimation: replace `len(text) / 4` heuristic in `generator._estimate_tokens()` with `tiktoken` (`cl100k_base`, lazy-loaded, falls back to heuristic if unavailable). New dep: `tiktoken>=0.7`.
- Cache eviction: cap `.ctx-cache/llm_cache.json` at 10,000 entries (trim oldest on write); `max_cache_entries` config key.
- Transient error transparency: prefix `[transient, retries exhausted]` on known transient failures; CLI footer suggests retry.

**Branch:** `feat/phase10-trust` (branch from `main` after Phase 9 merges)

### Phase 11 — Completeness ✓
Scope: close all open suggestions accumulated across Phases 4–10 reflections.
- Prompt regression tests for all six `DEFAULT_PROMPT_TEMPLATES` (Phase 4 backlog).
- `watch_debounce_seconds` config key (Phase 7 backlog).
- `ctx setup` UX: probing messages + `--check` flag (Phases 9–10 backlog).
- Java parser: `public class/interface/enum/record`, `public` methods, public static nested classes. 8 tests.
- C# parser: `public class/interface/enum/struct/record`, `public` methods. 7 tests.

**Branch:** `feat/phase11-completeness`

### Phase 12 — Language Depth & CLI Ergonomics ✓
Scope: close all suggestions from the Phase 11 reflection; expand language coverage and improve CLI discoverability.
- Kotlin parser: `fun`, `data class`, `object`, `interface`, `enum class`. 6 tests.
- Ruby parser: `def`/`self.method`, `class`, `module`. 6 tests.
- `ctx diff` command: `[mod]`/`[new]` CONTEXT.md files via git. 2 tests.
- C# property parsing: separate `properties` key from `methods`. 1 new test.
- Annotation-aware Java method matching: strips `@Annotation` lines before regex. 1 new test.
- `ctx init --overwrite/--no-overwrite`: `--no-overwrite` delegates to `update_tree`. 2 tests.

**Branch:** `feat/phase12-language-depth`

### Phase 13 — Extended Language Support & CLI Polish ✓
Scope: close all suggestions from the Phase 12 reflection.
- PHP parser: `public function`, global functions, `class`, `interface`, `trait`, `enum`. 5 tests.
- Swift parser: `public`/`open`/`internal` `func`, `class`, `struct`, `protocol`, `enum`. 5 tests.
- `ctx diff --since <ref>`: custom git ref passed to `git diff`. 1 test.
- Non-git fallback: mtime comparison + `[stale]` prefix + stderr warning. 1 test.
- README: `ctx init` idempotency note, `--no-overwrite` and `ctx diff` in commands table.

**Branch:** `feat/phase13-extended-language-support`

### Phase 14 — CLI Completeness ✓
Scope: unified diff vocabulary, JSON output, export, stats, and Elixir parser.
- Unified diff vocabulary: `[mod]`/`[new]` (git path), `[stale]` (mtime fallback path).
- `ctx diff --format json`: git path → `{"modified":[…],"new":[…]}`; mtime path → `{"stale":[…]}`.
- `ctx export`: walks `rglob("CONTEXT.md")`, writes with `# path/CONTEXT.md` headers (respects `.ctxignore`).
- `ctx stats`: coverage table (dirs/covered/missing/stale/tokens).
- Elixir parser: `def` (public), `defmodule`, `defstruct`; wired for `.ex`/`.exs`. 24 new tests.

**Branch:** `feat/phase14-cli-completeness`

### Phase 15 — CLI Power-User Features ✓
Scope: close all suggestions from the Phase 14 reflection.
- `ctx stats --verbose`: per-directory breakdown table in addition to aggregate totals.
- `ctx export --filter stale`: export only manifests needing attention (`stale`, `missing`, or `all`).
- `ctx diff --quiet` exit-code mode: exit 1 if any changes found; enables zero-config CI gating.
- Elixir `@type`/`@spec`/`@callback` extraction: full library API surface in the Elixir parser.
- `ctx clean` command: remove all `CONTEXT.md` files under a directory tree (reset to zero).
- `ctx export --depth N`: limit rglob to N nesting levels.

**Branch:** `feat/phase15-cli-power-user`

### Phase 16 — Observability & Consistency
Scope: close all suggestions from the Phase 15 reflection and the March 2026 north-star findings review.

Finding-driven additions:
- Default ignore hygiene: exclude obvious workspace-noise directories (at minimum `.pytest_cache/` and `.worktrees/`) so manifests stay high-signal.
- Explicit serve-root scoping: `ctx serve` must stop relying on process `cwd` and serve a chosen tree explicitly.

Execution order: one gate per branch and one gate per PR.
See `PHASE16_HANDOFF.md` for the full contract.

- Gate 16A — Docs truth sync and handoff prep. ✓
- Gate 16B — Default ignore hygiene. ✓ Completed in the handoff-prep pass.
- Gate 16C — `ctx clean --dry-run`. ✓
- Gate 16D — `ctx export` respects `.ctxignore`. ✓
- Gate 16E — `ctx verify`. ✓
- Gate 16F — Explicit `ctx serve` root scoping. ✓
- Gate 16G — `ctx stats --format json`. ✓
- Gate 16H — `ctx diff --stat`. ✓
- Gate 16I — `ctx watch` coverage line. ✓
- Gate 16Z — Manifest refresh, validation, and phase closeout. ✓ Completed after clearing broken proxy env vars for the refresh shell.

### Phase 17 — Closeout Reliability & Refresh Resilience
Scope: harden the operator path around manifest refresh failures discovered during the Phase 16 closeout attempt.
- `ctx update` should exit non-zero when any directory fails regeneration, including transient retry exhaustion.
- Add a closeout-grade request-readiness check and operator guidance so gate closeout can detect broken proxy state instead of trusting env-var presence alone.

**Branch:** `feat/phase17-closeout-reliability`

#### Gates
- Gate 17.1 — `ctx init`/`ctx update` exit 1 on errors. ✓
- Gate 17.2 — `ctx setup --check` probes real connectivity and surfaces proxy guidance. ✓
- Gate 17Z — Manifest refresh, validation, and phase closeout. ✓ `ctx setup --check` confirmed `Connectivity: OK`; `ctx update .` refreshed 4 directories, exited 0; 18 fresh, 0 stale, 0 missing; 281 tests passing.

### Phase 18 — Pre-flight Connectivity & Error Guidance
Carry-forward items from the Phase 17 reflection.
- Pre-flight connectivity check in `ctx update`/`ctx init` — run `probe_provider_connectivity` before starting the full refresh so the operator gets an early, actionable failure rather than per-directory errors after tokens are already spent.
- Surface proxy env vars in the transient error tip — when `_echo_generation_errors` prints the transient retry tip, also check and name active proxy vars in-line so guidance appears without needing to run `ctx setup --check`.

**Branch:** `feat/phase18-preflight-connectivity`

#### Gates
- Gate 18.1 — Pre-flight connectivity check in `_build_generation_runtime`. ✓
- Gate 18.2 — Proxy guidance in `_echo_generation_errors` transient error tip. ✓

### Phase 19 — Real-World UX
Theme: Quality-of-life improvements for live end-user testing on real repos.
- **19.1 Cross-repo smoke test** — run `ctx setup && ctx init .` on a real non-ctx repo on this machine. Fix any failures, path issues, or ignore-pattern gaps that surface. Gate: it works end-to-end.
- **19.2 Progress reporting** — show directory count, running token total, and elapsed time during generation (e.g. `[3/18] Processing src — 1,240 tokens, 4.2s`).
- **19.3 Run cost summary** — after `ctx init`/`ctx update`, print an estimated cost line based on tokens used and known provider pricing.

**Branch:** `feat/phase19-real-world-ux`

### Phase 20 — Agent Integration & Daily Workflow
Theme: Make ctx useful as part of a real AI-assisted development workflow.
- **20.1 `ctx watch` session test** — run a timed `ctx watch` session during real edits. Validate stability, debounce, ignore patterns, and coverage feedback. Fix any issues.
- **20.2 Agent handoff test** — test `ctx export --depth 1` and `ctx serve` as context sources for Claude Code. Validate that exported context helps an agent navigate the target repo.
- **20.3 Summary quality audit** — read generated manifests on real repos. Flag anything vague, wrong, or unhelpful. Implement prompt tuning in `llm.py` based on findings.

**Branch:** `feat/phase20-agent-integration`
