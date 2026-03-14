# State of `ctx`

Current development status and upcoming milestones.

## Current Health (March 2026)
- **Status:** Stable Beta. Phases 1–7 complete. Phase 8 not yet scoped.
- **Core Engine:** Bottom-up traversal, incremental hashing, parallel depth-level processing, persistent model-aware LLM cache.
- **Test Coverage:** 143 tests passing across all modules.
- **LLM Support:** Anthropic (Claude), OpenAI, Ollama, LM Studio. BitNet removed.
- **Ecosystem:** MCP server, git-aware updates (`ctx smart-update`), file watcher (`ctx watch`), CI/CD GitHub Action, Python + JS/TS + Rust + Go language parsers, model-aware disk cache, token budget enforcement, `--dry-run` preview.

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

## Phase 8 — (Not Yet Scoped)

Candidates from Phase 7 reflection:
- **Java / C# parsers** — complete enterprise language coverage.
- **Accurate token counting** — replace character-based `_estimate_tokens` with `tiktoken` for budget accuracy.
- **`watch_debounce_seconds` config** — expose debounce window as a `.ctxconfig` key.

**Branch:** `feat/phase8-*` (branch from `main` after Phase 7 closeout)
