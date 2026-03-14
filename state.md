# State of `ctx`

Current development status and upcoming milestones.

## Current Health (March 2026)
- **Status:** Stable Alpha / Beta.
- **Core Engine:** Fully implemented with bottom-up traversal and incremental hashing.
- **Test Coverage:** High for core components (`generator`, `hasher`, `manifest`).
- **Binary Support:** Robust detection and metadata extraction.

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
- [x] `BitNetClient` for local inference using BitNet subprocesses.
- [x] Batch file summarization to reduce API calls.
- [x] Per-file fallback for Ollama when batch output is malformed or wrong count.

### Manifest Management
- [x] YAML frontmatter serialization.
- [x] Markdown body generation and child summary propagation.
- [x] Incremental updates (`ctx update`).
- [x] Manifest health status check (`ctx status`).

## Phase 1 — Hygiene & Merge Readiness

Repo cleanup and branch merge. Prerequisite for all subsequent work.

- [ ] Fix `pathspec` deprecation: change `"gitwildmatch"` → `"gitignore"` in `src/ctx/ignore.py`.
- [ ] Remove stale `pytest-cache-files-*/` directories.
- [ ] Update `.gitignore`: add `.tmp/`, `pytest-cache-files-*/`, `.worktrees/`.
- [ ] Merge `feat/local-providers-token-budget` → `main`.

## Phase 2 — Reliability & Performance ✓

Make local providers robust and unlock parallelism.

- [x] **400 context-length fallback:** `openai.BadRequestError` caught in `OpenAIClient.summarize_files` (falls back to per-file) and `summarize_directory` (truncates summaries to `_SUMMARY_TRUNCATE_CHARS` and retries once). Local providers only.
- [x] **Parallel directory processing:** `_run_generation` groups directories by depth and processes each level with `ThreadPoolExecutor` (max 4 workers). Bottom-up invariant preserved — level barrier via context manager `__exit__`. Token budget checked at level granularity.
- [x] **LLM response caching:** `CachingLLMClient` wraps any `LLMClient` and caches file summaries by SHA-256 content hash. Thread-safe. Applied automatically in `generate_tree` and `update_tree`.
- [x] **BitNet deprecated:** Removed `BitNetClient` class. `create_client("bitnet")` raises `click.UsageError` directing users to Ollama or LM Studio.
- [ ] Refine system prompts for more consistent summary styles.
- [ ] Optimize batch sizes for different LLM context windows.

## Phase 3 — Ecosystem Integration

Connect `ctx` to the broader development toolchain.

- [x] **MCP Server Support:** Expose `ctx` manifests via the Model Context Protocol.
- [x] **Git-Aware Updates:** Detect changed files since last commit to trigger selective regeneration.
- [x] **CI/CD Action:** GitHub Action that ensures `CONTEXT.md` files are never out of sync.
- [x] **Custom Prompts:** Allow users to define their own summarization styles via `.ctxconfig`.
- [x] **Language-Specific Heuristics:** Smarter summarization by recognizing common project structures (e.g., Python, Rust, Go).
