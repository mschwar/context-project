# State of `ctx`

Current development status and upcoming milestones.

## Current Health (March 2026)
- **Status:** Stable Beta. Phases 1–5 complete. Phase 6 scoped and ready to begin.
- **Core Engine:** Bottom-up traversal, incremental hashing, parallel depth-level processing, persistent LLM cache.
- **Test Coverage:** 112 tests passing across all modules.
- **LLM Support:** Anthropic (Claude), OpenAI, Ollama, LM Studio. BitNet removed.
- **Ecosystem:** MCP server, git-aware updates (`ctx smart-update`), CI/CD GitHub Action, language heuristics, disk cache, token budget enforcement, `--dry-run` preview.

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

## Phase 6 — Language Expansion & CI Hygiene

Richer summaries for the most common open-source language mix; fix pre-existing CI noise.

**Gate condition:** Phase 5 gate closeout (reflection + PR merge) must complete before work begins.

**Deliverables:**

#### 6.1 — JavaScript / TypeScript Parser
- Add `src/ctx/lang_parsers/js_ts_parser.py` using `tree-sitter` or regex-based AST extraction.
- Extract: exported functions, classes, interfaces, type aliases, default export.
- Wire into `generator.py` alongside the existing Python parser path.
- Files: `src/ctx/lang_parsers/js_ts_parser.py`, `src/ctx/generator.py`, `tests/test_js_ts_parser.py`.

#### 6.2 — Rust Parser
- Add `src/ctx/lang_parsers/rust_parser.py`.
- Extract: `pub fn`, `pub struct`, `pub enum`, `pub trait`, `mod` declarations.
- Files: `src/ctx/lang_parsers/rust_parser.py`, `src/ctx/generator.py`, `tests/test_rust_parser.py`.

#### 6.3 — Fix Pre-existing CI Failures (chore)
- Fix CTX Manifest Check: create `.github/actions/ctx-check/action.yml` or update the workflow to use `ctx status --check-exit-code` inline.
- Fix PR Checks / Validate PR: update workflow to use Python's `pytest` instead of `npm run test`.
- Files: `.github/workflows/pr-checks.yml`, `.github/workflows/ctx-manifest-check.yml`.

**Branch:** `feat/phase6-language-expansion` (branch from `main` after Phase 5 closeout)
