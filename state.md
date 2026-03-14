# State of `ctx`

Current development status and upcoming milestones.

## Current Health (March 2026)
- **Status:** Stable. Phases 1–11 complete.
- **Core Engine:** Bottom-up traversal, incremental hashing, parallel depth-level processing, persistent model-aware LLM cache.
- **Test Coverage:** 195 tests passing across all modules.
- **LLM Support:** Anthropic (Claude), OpenAI, Ollama, LM Studio. BitNet removed.
- **Ecosystem:** MCP server, git-aware updates (`ctx smart-update`), file watcher (`ctx watch`), CI/CD GitHub Action, Python + JS/TS + Rust + Go + Java + C# language parsers, model-aware disk cache, token budget enforcement, `--dry-run` preview, `ctx setup` auto-detection.

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
- [x] Update `.gitignore`: added `.tmp/`, `pytest-cache-files-*/`, `.worktrees/`.
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

## Phase 12 — Language Depth & CLI Ergonomics

Close all suggestions from the Phase 11 reflection. Expand language coverage and improve CLI discoverability.

- [ ] **12.1 Kotlin parser** — `fun`, `data class`, `object`, `interface`, `enum class`. Wired in for `.kt` files.
- [ ] **12.2 Ruby parser** — top-level `def`, `class`, `module`. Public by default; parse all top-level definitions. Wired in for `.rb` files.
- [ ] **12.3 `ctx diff` command** — show which `CONTEXT.md` files changed since the last generation run (git diff on `CONTEXT.md` files). Low cost, high diagnostic value.
- [ ] **12.4 C# property parsing** — add `properties` key to `parse_csharp_file()`, separate from `methods`. `public int Foo { get; set; }` currently may match method regex.
- [ ] **12.5 Annotation-aware Java method matching** — handle `@Override\npublic void foo()` by stripping annotation lines before matching or relaxing line-anchor requirement.
- [ ] **12.6 `ctx init --overwrite` flag** — skip existing fresh manifests when `--overwrite=false` (default), matching `ctx update` behaviour.

**Branch:** `feat/phase12-language-depth`
