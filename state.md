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

## In Progress

### Prompt Engineering
- [ ] Refine system prompts for more consistent summary styles.
- [ ] Optimize batch sizes for different LLM context windows.

### Performance
- [ ] Implement parallel processing for directory summarization (currently sequential).
- [ ] Add caching for LLM responses to avoid redundant calls during debugging.

## Backlog

- [ ] **Fix BitNet subprocess path resolution:** `run_inference.py` is not found even when `--base-url` points to the correct directory. Absolute path resolution was attempted but did not solve it. Needs deeper debugging of Windows subprocess `cwd` + script path handling.
- [ ] **Add 400 context-length fallback for local providers:** When a local provider returns HTTP 400 due to `n_keep >= n_ctx`, catch `openai.BadRequestError` and fall back to per-file summarization with more aggressive truncation. Also handle directory-level prompt truncation when combined file summaries exceed the model's context window.

## Roadmap

### Future Enhancements
- [ ] **MCP Server Support:** Expose `ctx` manifests via the Model Context Protocol.
- [ ] **Git Integration:** Automatically detect changed files since last commit to trigger updates.
- [ ] **Language-Specific Heuristics:** Smarter summarization by recognizing common project structures (e.g., Python, Rust, Go).
- [ ] **Custom Prompts:** Allow users to define their own summarization styles via `.ctxconfig`.
- [ ] **CI/CD Action:** A GitHub Action that ensures `CONTEXT.md` files are never out of sync.
