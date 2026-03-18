# State of `ctx`

Current development status and upcoming milestones.

## Current Health (March 2026)
- **Status:** Stable. Phases 1–21 complete; AFO Stages 1–6 implemented.
- **Core Engine:** Bottom-up traversal, incremental hashing, parallel depth-level processing, persistent model-aware LLM cache.
- **Test Coverage:** 406 tests passing across all modules.
- **LLM Support:** Anthropic (Claude), OpenAI, Ollama, LM Studio. BitNet removed.
- **Agent Surface:** canonical `ctx refresh`, `ctx check`, `ctx export`, and `ctx reset` commands backed by `src/ctx/api.py`, with hidden legacy aliases preserved for compatibility.
- **Configuration:** full `CTX_*` env-var parity for scalar config fields, shared cost estimation, zero-config refresh bootstrap for env/local providers, and hard `max_tokens_per_run` / `max_usd_per_run` guardrails.
- **Documentation:** `AGENTS.md` is now the machine-readable onboarding contract, `README.md` is demoted to a short human-facing pitch, and generated manifests append a source footer.
- **MCP Integration:** `ctx serve --mcp` now exposes a stdio JSON-RPC server backed by `api.py`; HTTP serving remains available via the optional `[serve]` extra.

## Completed Milestones

### Foundation
- [x] CLI entry point with `Click`.
- [x] Config system with `.ctxconfig` and env var support.
- [x] Robust `.ctxignore` handling via `pathspec`.
- [x] Content-based change detection (SHA-256).
- [x] Canonical agent workflow defined in `AGENTS.md` (inspired by Ledger repo).
- [x] Operational runbook defined in `RUNBOOK.md`.
- [x] Git pre-commit hooks for automated quality checks.

### LLM Integration
- [x] `AnthropicClient` for Claude (preferred).
- [x] `OpenAIClient` with support for OpenAI, Ollama, and LM Studio.
- [x] Batch file summarization to reduce API calls.
- [x] Per-file fallback for local providers when batch output is malformed or wrong count.
- [x] Custom prompts via `.ctxconfig` `prompts:` key.
- [x] Language detection and Python structural metadata (classes, functions).

### Manifest Management
- [x] YAML frontmatter serialization.
- [x] Markdown body generation and child summary propagation.
- [x] Incremental updates (`ctx update`).
- [x] Manifest health status check (`ctx status`).

## Phase 1 — Hygiene & Merge Readiness ✓

Repo cleanup and branch merge.

- [x] Fix `pathspec` deprecation: changed `"gitwildmatch"` → `"gitignore"` in `src/ctx/ignore.py`.
- [x] Remove stale `pytest-cache-files-*/` directories.
- [x] Update `.gitignore`: added `.pytest_cache/`, `.tmp/`, `pytest-cache-files-*/`, `.worktrees/`.
- [x] Merge `feat/local-providers-token-budget` → `main`.

## Phase 2 — Reliability & Performance ✓

Make local providers robust and unlock parallelism.

- [x] **400 context-length fallback:** `openai.BadRequestError` caught in `OpenAIClient.summarize_files` (falls back to per-file) and `summarize_directory` (truncates summaries and retries once). Local providers only.
- [x] **Parallel directory processing:** `_run_generation` groups directories by depth and processes each level with `ThreadPoolExecutor` (max 4 workers). Bottom-up invariant preserved.
- [x] **LLM response caching:** `CachingLLMClient` wraps any `LLMClient` and caches file summaries by content hash. Thread-safe with Future-based stampede prevention.
- [x] **BitNet deprecated:** Removed `BitNetClient` class. `create_client("bitnet")` raises `click.UsageError` directing users to Ollama or LM Studio.

## Phase 3 — Ecosystem Integration ✓

Connect `ctx` to the broader development toolchain.

- [x] **MCP Server Support:** Expose `ctx` manifests via the Model Context Protocol (`ctx serve`).
- [x] **Git-Aware Updates:** `ctx smart-update` detects changed files (staged + unstaged) to trigger selective regeneration.
- [x] **CI/CD Action:** GitHub Action that ensures `CONTEXT.md` files are never out of sync (`--check-exit-code`).
- [x] **Custom Prompts:** Allow users to define their own summarization styles via `.ctxconfig`.
- [x] **Language-Specific Heuristics:** Smarter summarization by recognizing common project structures (e.g., Python, Rust, Go).

## Phase 4 — Prompt Quality & Batch Control ✓

Improve output consistency and give users control over LLM call granularity.

- [x] **Refined system prompts:** All six `DEFAULT_PROMPT_TEMPLATES` rewritten with explicit rules — 20-word sentence cap, purpose-over-implementation guidance, exact markdown structure for directory summaries, consistent prompt-injection defence phrasing.
- [x] **`batch_size` config:** New `.ctxconfig` key and `Config.batch_size` field. When set, `summarize_files` splits the file list into chunks of that size and makes one LLM call per chunk. Lets users tune call granularity for small-context local models without hitting 400 errors.
- [x] **Remove `bitnet` from CLI choices:** `--provider bitnet` no longer appears in `--help`. Users who set it via env/config still get the informative deprecation error from `create_client`.

## Phase 5 — Cost Control & Observability ✓

Close the gaps between wired-up config fields and actual runtime behaviour; add a dry-run preview before spending tokens.

- [x] **5.1 Persistent LLM Cache:** `CachingLLMClient` loads/saves summaries to `.ctx-cache/llm_cache.json`. New `cache_path` config key and `--cache-path` CLI flag. Repeated runs on unchanged trees cost zero tokens. Disable with `cache_path: ""`.
- [x] **5.2 Token Budget Enforcement:** `_run_generation` stops LLM calls when `stats.tokens_used >= token_budget`. `GenerateStats.budget_exhausted` flag added; CLI prints a dedicated warning.
- [x] **5.3 `--dry-run` Flag:** `ctx update --dry-run` and `ctx smart-update --dry-run` list stale directories without LLM calls or file writes. Backed by new `check_stale_dirs()` function.

## Phase 6 — Language Expansion & CI Hygiene ✓

Richer summaries for the most common open-source language mix; fix pre-existing CI noise.

- [x] **6.1 JS/TS parser:** `js_ts_parser.py` — regex extraction of exported functions (named + arrow), classes, interfaces, type aliases, default export. Wired into `generator._prepare_file_entry` for `.js`, `.ts`, `.jsx`, `.tsx`. 8 tests.
- [x] **6.2 Rust parser:** `rust_parser.py` — extracts `pub fn`, `pub struct`, `pub enum`, `pub trait`, `mod` (all visibility modifiers). Wired in for `.rs` files. 7 tests.
- [x] **6.3 CI hygiene:** `ctx-check.yml` rewritten inline (removed missing composite-action reference). `pr-checks.yml` replaced Node/npm template with Python `pytest`. Both checks now pass.

## Phase 7 — Go Parser, ctx watch, Cache Model-Awareness ✓

- [x] **Go parser:** `go_parser.py` — exported functions (including receiver methods), types, constants (including iota-style), variables. 6 tests.
- [x] **`ctx watch`:** `watcher.py` — OS-native file watcher via `watchdog`. CONTEXT.md writes excluded (infinite-loop prevention). 0.5 s per-file debounce. Hooks into `update_tree`. 8 tests.
- [x] **Cache model-awareness:** `CachingLLMClient` now keys on `sha256(model + ":" + file_json)`. Switching models always produces cache misses. Existing cache files are invalidated on first run (one-time regeneration cost).

## Phase 8 — Ship It

Make `ctx` installable via `pip install`, with automated releases and a README that gets someone from zero to working in 60 seconds.

- [x] **8.1 PyPI-ready packaging:** `ctx-tool` on PyPI; classifiers, project URLs; `__version__` bumped to `"0.8.0"`; `setuptools-scm` removed from build deps.
- [x] **8.2 Publish workflow:** `.github/workflows/publish.yml` — tag `v*` → run tests → build + publish via OIDC trusted publishing (no API token secrets needed).
- [x] **8.3 README rewrite:** quick-start in 4 commands, commands table, `.ctxconfig` example, local LLM notes.

**Branch:** `feat/phase8-distribution`

## Phase 9 — Automate It

Zero-friction first run and automatic manifest freshness without user effort.

- [x] **9.1 `ctx setup` command:** auto-detect provider (env vars → Ollama probe → LM Studio probe), write `.ctxconfig`, print next step.
- [x] **9.2 Pre-commit hook:** `.pre-commit-hooks.yaml` for standard `pre-commit` framework; runs `ctx status . --check-exit-code`.
- [x] **9.3 Graceful failure:** `ctx init`/`ctx update` missing-API-key errors print actionable hint pointing to `ctx setup`.

**Branch:** `feat/phase9-onboarding-automation` (branch from `main` after Phase 8 merges)

## Phase 10 — Trust It

Fix the three reliability gaps that erode confidence at scale.

- [x] **10.1 Accurate token estimation:** replace `len(text) / 4` heuristic with `tiktoken` (`cl100k_base`, lazy-loaded, falls back gracefully). New dep: `tiktoken>=0.7`.
- [x] **10.2 Cache eviction:** cap `.ctx-cache/llm_cache.json` at 10,000 entries (trim oldest on write); `max_cache_entries` config key.
- [x] **10.3 Transient error transparency:** prefix `[transient, retries exhausted]` on known transient failures; CLI footer suggests retry.

**Branch:** `feat/phase10-trust` (branch from `main` after Phase 9 merges)

## Phase 11 — Completeness ✓

Close all outstanding suggestions accumulated across Phases 4–10 reflections.

- [x] **11.1 Prompt regression tests** — 11 tests covering all six `DEFAULT_PROMPT_TEMPLATES`; structural markers, injection-defence language, `{json_payload}` placeholder, rendering.
- [x] **11.2 `watch_debounce_seconds` config** — `Config` field (default 0.5s); wired from `.ctxconfig`; passed to `_DebounceHandler` replacing hardcoded constant.
- [x] **11.3 `ctx setup` UX** — live probing messages via `_probe_callback`; `--check` flag for non-destructive detection.
- [x] **11.4 Java parser** — `public class/interface/enum/record` + public methods + public static nested classes. 8 tests.
- [x] **11.5 C# parser** — `public class/interface/enum/struct/record` + public methods (async, override, static). 7 tests.

**Branch:** `feat/phase11-completeness`

## Phase 12 — Language Depth & CLI Ergonomics ✓

Close all suggestions from the Phase 11 reflection. Expand language coverage and improve CLI discoverability.

- [x] **12.1 Kotlin parser** — `fun`, `data class`, `object`, `interface`, `enum class`; wired for `.kt`; 6 tests.
- [x] **12.2 Ruby parser** — `def`/`self.method`, `class`, `module`; wired for `.rb`; 6 tests.
- [x] **12.3 `ctx diff` command** — lists `[mod]`/`[new]` CONTEXT.md files via `git diff HEAD` + `git ls-files`; 2 tests.
- [x] **12.4 C# property parsing** — `properties` key added, separate from `methods`; 1 new test.
- [x] **12.5 Annotation-aware Java method matching** — strips `@Annotation` lines before method regex; 1 new test.
- [x] **12.6 `ctx init --overwrite/--no-overwrite`** — default regenerates all; `--no-overwrite` delegates to `update_tree`; 2 tests.

**Branch:** `feat/phase12-language-depth`

## Phase 13 — Extended Language Support & CLI Polish ✓

Close all suggestions from the Phase 12 reflection.

- [x] **13.1 PHP parser** — `public function`, `class`, `interface`, `trait`, `enum`. Wired for `.php` files.
- [x] **13.2 Swift parser** — `func`, `class`, `struct`, `protocol`, `enum`. Wired for `.swift` files.
- [x] **13.3 `ctx diff --since <ref>`** — accept a git ref (branch, commit, tag) to show changes since a specific point, not just since `HEAD`.
- [x] **13.4 Non-git fallback for `ctx diff`** — when outside a git repo, compare `CONTEXT.md` mtimes against source file mtimes.
- [x] **13.5 `ctx init` idempotency docs** — clarify in README that `ctx init` regenerates unconditionally; promote `ctx init --no-overwrite` for incremental use.

**Branch:** `feat/phase13-extended-language-support`

## Phase 14 — CLI Completeness ✓

Close all suggestions from the Phase 13 reflection. Deliver unified diff vocabulary, JSON output, export, stats, and Elixir parser.

- [x] **14.1 Unified diff vocabulary** — `[mod]`/`[new]` (git path) and `[stale]` (mtime fallback path) labels standardised across `ctx diff` output.
- [x] **14.2 `ctx diff --format json`** — git path emits `{"modified":[…],"new":[…]}`; mtime path emits `{"stale":[…]}`.
- [x] **14.3 `ctx export`** — walks `rglob("CONTEXT.md")`, concatenates with `# path/CONTEXT.md` headers to stdout or `--output` file.
- [x] **14.4 `ctx stats`** — prints dirs/covered/missing/stale/tokens aggregate coverage table.
- [x] **14.5 Elixir parser** — `def` (public), `defmodule`, `defstruct`; wired for `.ex`/`.exs`. 24 new tests (213 → 237).

**Branch:** `feat/phase14-cli-completeness`

## Phase 15 — CLI Power-User Features ✓

Close all suggestions from the Phase 14 reflection.

- [x] **15.1 `ctx stats --verbose`** — per-directory breakdown table (path, covered/missing/stale status, token count) in addition to aggregate totals.
- [x] **15.2 `ctx export --filter stale`** — `--filter` option accepting `stale`, `missing`, or `all` (default) to export only manifests that need attention.
- [x] **15.3 `ctx diff --quiet` exit-code mode** — suppress output and exit 1 if any changes are found; enables zero-config CI gating without JSON parsing.
- [x] **15.4 Elixir `@type`/`@spec`/`@callback` extraction** — extend the Elixir parser to capture module-level attributes for full library API surface coverage.
- [x] **15.5 `ctx clean` command** — remove all `CONTEXT.md` files under a directory tree; provides a quick "reset to zero" before regenerating.
- [x] **15.6 `ctx export --depth N`** — limit the rglob to N nesting levels; useful for exporting only top-level or mid-level manifests.

**Branch:** `feat/phase15-cli-power-user`

## Phase 16 — Observability & Consistency

Close all suggestions from the Phase 15 reflection and the March 14, 2026 repo findings review.

Execution order: one gate per branch/PR. See `PHASE16_HANDOFF.md` for file lists, tests, and acceptance criteria.

- [x] **Gate 16A — docs truth sync and handoff prep** — align standing docs with repo truth and publish the Phase 16 execution contract.
- [x] **Gate 16B — default ignore hygiene** — default ignore rules now skip `.pytest_cache/`, `.worktrees/`, and `.tmp/` so manifests stay high-signal and local traversal avoids unreadable workspace noise.
- [x] **Gate 16C — `ctx clean --dry-run`** — preview which `CONTEXT.md` files would be deleted without removing them; mirrors the `ctx update --dry-run` pattern.
- [x] **Gate 16D — `ctx export` respects `.ctxignore`** — thread the `pathspec`-based ignore logic through the export walk so ignored directories never appear in exported manifests.
- [x] **Gate 16E — `ctx verify` command** — check each `CONTEXT.md` frontmatter for required fields (`generated`, `generator`, `model`, `content_hash`, `files`, `dirs`, `tokens_total`) and report manifests with missing or malformed fields.
- [x] **Gate 16F — explicit `ctx serve` root scoping** — stop relying on process `cwd`; serve a chosen tree explicitly and keep traversal protection intact.
- [x] **Gate 16G — `ctx stats --format json`** — add `--format json` flag (aggregate and `--verbose` modes) for machine-readable coverage reports; enables dashboards and CI scripts without parsing table text.
- [x] **Gate 16H — `ctx diff --stat`** — print a one-line summary count (`N modified, N new, N stale`) rather than the full file list; mirrors `git diff --stat` semantics.
- [x] **Gate 16I — `ctx watch` stale count on update** — after each debounced `update_tree` call, print a one-line stats summary (stale/covered counts) so users get continuous coverage feedback without running a separate command.
- [x] **Gate 16Z — manifest refresh and closeout** — targeted validation, full-suite validation, manifest refresh, reflection, and carry-forward are complete. Refresh initially failed due to shell proxy state, then succeeded after clearing proxy env vars before rerunning `ctx update`.

## Phase 17 — Closeout Reliability & Refresh Resilience

Carry-forward items from the Phase 16 reflection.

- [x] **17.1 Non-zero exit on refresh errors** — make `ctx update` / `ctx init` fail the process when any directory regeneration errors out, including transient retry exhaustion, so CI and gate closeout cannot misread a failed refresh as success.
- [x] **17.2 Refresh readiness and proxy guidance** — add a closeout-grade request-readiness check and operator guidance so `ctx setup --check` / closeout validation can distinguish "env var present" from "provider calls succeed", including broken proxy env cases.
- [x] **Gate 17Z — Manifest refresh and closeout** — `ctx setup --check` confirmed `Connectivity: OK`; `ctx update .` refreshed 4 directories, exited 0; 18 fresh, 0 stale, 0 missing; 281 tests passing.

## Phase 18 — Pre-flight Connectivity & Error Guidance

Carry-forward items from the Phase 17 reflection.

- [x] **18.1 Pre-flight connectivity check** — run `probe_provider_connectivity` before starting the full refresh in `ctx update`/`ctx init` so the operator gets an early, actionable failure rather than per-directory errors after tokens are already spent.
- [x] **18.2 Proxy guidance in transient error tip** — when `_echo_generation_errors` prints the transient retry tip, also check and name active proxy env vars in-line so guidance appears without needing to run `ctx setup --check`.
- [x] **Gate 18Z — Manifest refresh and closeout** — 308 tests passing; reflection artifact created; carry-forward suggestions (probe timeout, session caching) added to backlog.

## Phase 19 — Real-World UX ✓

Theme: Quality-of-life improvements for live end-user testing on real repos.

- [x] **19.1 Cross-repo smoke test** — Verified `ctx init` works end-to-end on a fresh repo with progress reporting and cost summary features.
- [x] **19.2 Progress reporting** — Shows directory count, running token total, and elapsed time during generation (e.g., `[3/18] Processing src — 1,240 tokens, 4.2s`). Implemented via `ProgressState` dataclass and updated progress callback signature.
- [x] **19.3 Run cost summary** — After `ctx init`/`ctx update`, prints estimated cost in USD based on tokens used and provider pricing (supports Anthropic and OpenAI models; local providers show $0.00).

## Phase 20 — Agent Integration & Daily Workflow ✓

Theme: Make ctx useful as part of a real AI-assisted development workflow.

- [x] **20.1 `ctx watch` session test** — Added comprehensive integration tests validating stability, debounce (0.1s fast debounce for testing), ignore patterns, and coverage feedback during simulated watch sessions.
- [x] **20.2 Agent handoff test** — Validated `ctx export --depth 1` and `ctx serve` as context sources for agents. Added 6 new tests covering export depth filtering, structure validation, serve endpoint testing, stale filtering, and end-to-end agent navigation workflow.
- [x] **20.3 Summary quality audit** — Reviewed generated manifests, identified improvements for boilerplate file handling (`__init__.py`, `config.py`, `test_*.py`). Implemented prompt tuning with concrete examples and improved Notes section guidance in `DEFAULT_PROMPT_TEMPLATES`.

## Phase 21 — Health Truth & Diagnostics ✓

Theme: make health-reporting and troubleshooting surfaces agree after real-world smoke testing.

- [x] **21.1 Shared stale-truth engine** — unify hash-based freshness detection across `ctx stats`, `ctx export --filter stale`, watch coverage summaries, and any future health/coverage surfaces so parent-directory staleness is reported consistently.
- [x] **21.2 Stronger `ctx verify`** — extend `ctx verify` with stale/missing coverage checks and machine-readable output so CI and gate closeout can validate both manifest shape and manifest freshness.
- [x] **21.3 Unborn-HEAD git UX** — treat empty repos / unborn `HEAD` as a first-class git state in `ctx diff` and related git-aware flows instead of falling back with misleading "git unavailable" warnings.
- [x] **21.Z Gate closeout** — reflection filed at `archive/reflections/2026-03-17-phase21-reflection.md`; closeout validation passed with `321` tests, `ctx update .`, `ctx status .`, `ctx verify . --format json`, and empty-repo `ctx diff` smoke coverage.

**Branch:** `feat/phase21-health-truth`

## Phases 22–23 — Superseded by Agent-First Overhaul

Phases 22 (First-Run Operator UX) and 23 (External Repo Validation) were planned but superseded by the Agent-First Overhaul (AFO). Their goals (zero-config bootstrap, better diagnostics, external validation) are addressed across AFO stages below.

---

## Agent-First Overhaul (AFO)

Theme: pivot ctx from a human-operated CLI to agent-first infrastructure. Core engine untouched; surface layer rebuilt. Specs in `docs/afo/` (00–07). One PR per stage.

### AFO Stage 1 — Structured Output ✓

- [x] **1.1 OutputBroker** — `src/ctx/output.py` context manager captures stdout/stderr in JSON mode, emits single JSON envelope per command.
- [x] **1.2 CtxLock** — `src/ctx/lock.py` cross-platform PID-file lock for write operations (.ctx-cache/lock, 30s stale timeout, Windows ctypes support).
- [x] **1.3 `--output json` group flag** — CLI group-level option + `CTX_OUTPUT=json` env var detection. All commands wrapped in OutputBroker.
- [x] **1.4 Atomic manifest writes** — `manifest.py` writes via `tempfile.mkstemp` + `os.replace` (safe on Windows and POSIX).
- [x] **1.5 `check` command surface** — early alias of `status` for agent-first naming (full command collapse is Stage 2).
- [x] **1.6 Progress suppression** — `_progress_callback` silent in JSON mode.
- [x] **1.Z Review fixes** — clean `reset` requires `--yes` in JSON mode (no auto-delete); `serve` unwrapped from OutputBroker; stale hint references corrected.

**Branch:** `feat/afo-stage1` → merged via `chore/phase21-closeout` (PR #54), fixes on `fix/afo-stage1-review`

### AFO Stage 2 — Unified API

- [x] **2.1 `api.py` module** — 4 public functions (`refresh`, `check`, `export_context`, `reset`) returning typed dataclasses. Zero Click dependency.
- [x] **2.2 Command collapse** — canonical `refresh` / `check` / `export` / `reset` commands now front the agent surface, with `serve` left standalone.
- [x] **2.3 Hidden aliases** — legacy command names remain hidden, still work, and emit deprecation warnings in human mode only.
- [x] **2.4 Refresh strategy tree** — `refresh` auto-selects full/smart/incremental based on manifest state and git availability.

**Branch:** `feat/afo-stage2` (verified complete; available on `main`)

### AFO Stage 3 — Non-Interactive Config

- [x] **3.1 Env var parity** — scalar `.ctxconfig` fields now map to `CTX_*` env vars, including base URL, depth, token/file limits, cache controls, debounce, extensions, and hard guardrails.
- [x] **3.2 Budget guardrails** — `max_tokens_per_run` and `max_usd_per_run` are on `Config`, enforced in `api.refresh()`, and remain intentionally unavailable as CLI flags.
- [x] **3.3 `estimate_cost` shared** — pricing logic now lives in `config.py` and is reused by the CLI and unified API.
- [x] **3.4 Zero-config refresh bootstrap** — `ctx refresh` now infers env-only OpenAI setups, auto-detects local providers on unconfigured repos, writes `.ctxconfig` when needed, and lets dry-run/check-style refresh paths load config without API keys.

**Branch:** `feat/afo-stage3`

### AFO Stage 4 — Agent Docs

- [x] **4.1 AGENTS.md rewrite** — machine-readable 9-section onboarding contract with `schema_version: 1`.
- [x] **4.2 README.md demotion** — README is reduced to a short human-facing pitch that points agents to `AGENTS.md`.
- [x] **4.3 Manifest footer** — `<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->` is appended to every generated `CONTEXT.md` and stripped from `read_manifest()` bodies.

**Branch:** `feat/afo-stage4`

### AFO Stage 5 — MCP Server (parallel with Stage 4)

- [x] **5.1 `mcp_server.py`** — hand-rolled JSON-RPC 2.0 stdio server, 4 tools mapping to `api.py`.
- [x] **5.2 `ctx serve --mcp`** — launches the stdio MCP server; HTTP serving stays on the default path and FastAPI/uvicorn move to the optional `[serve]` extra.

**Branch:** `feat/afo-stage5`

### AFO Stage 6 — Workflow Patterns

- [x] **6.1 Pre-commit hook** — `.pre-commit-hooks.yaml` now uses `ctx check . --check-exit`.
- [x] **6.2 CI workflow** — `.github/workflows/ctx-check.yml` now uses `python -m ctx check . --check-exit` with `CTX_OUTPUT=json`.

**Branch:** `feat/afo-stage6`

### AFO Version Bump — 1.0.0

After all 6 stages land: bump `__version__` from `0.8.0` to `1.0.0`.

---

## Post-AFO Backlog

- [ ] **Legacy command docs cleanup in ancillary specs** — sweep remaining AFO reference docs/examples that still show legacy command names where the canonical `refresh` / `check` surface should be primary.
