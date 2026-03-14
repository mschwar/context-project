# AGENTS

This file is the canonical onboarding and workflow contract for agents contributing to `ctx`.

## Mission
Build and maintain `ctx`, a filesystem-native context layer that generates recursive `CONTEXT.md` summaries to help AI agents navigate large codebases.

## Current State
- **Core Engine**: Fully implemented with bottom-up traversal and incremental hashing.
- **LLM Clients**: Anthropic and OpenAI supported (including Ollama and LM Studio). **BitNet is non-functional on Windows** — do not attempt to use or debug it without an explicit task scoped to that issue.
- **Test Coverage**: 76 tests across all modules (`cli`, `config`, `generator`, `hasher`, `ignore`, `llm`, `manifest`, integration).
- **Documentation**: `architecture.md`, `rules.md`, `state.md`, `RUNBOOK.md`, and `CONTRIBUTING.md` define the system.

> **Branch notice**: As of March 2026, active development lives on `feat/local-providers-token-budget`. This branch adds Ollama/LM Studio support and token budget controls, and is ahead of `main`. Branch from this branch, not `main`, until it is merged.

## Canonical Rules

1. **Context-First**: Every directory MUST have a `CONTEXT.md`.
2. **The Bottom-Up Rule**: Never update a parent directory's manifest until all children have fresh manifests.
3. **Hash Integrity**: All hashes MUST be SHA-256, hex-encoded, and prefixed with `sha256:`.
4. **Surgical Changes**: Make the smallest possible change that fulfills the requirement.
5. **No Logic Without Tests**: No logic changes without a corresponding test update.
6. **Strict Typing**: Python 3.10+ typing is mandatory.

## Required Behavior

### When working from a scoped prompt
1. Stay inside the stated scope.
2. Branch from `origin/main`.
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

## Development Phases

Active roadmap. See `state.md` for detailed status of each item.

### Phase 1 — Hygiene & Merge Readiness
Scope: repo cleanup and getting `feat/local-providers-token-budget` merged to `main`.
- Fix `pathspec` deprecation (`"gitwildmatch"` → `"gitignore"` in `ignore.py`).
- Remove stale build artifacts; update `.gitignore` for `.tmp/`, `pytest-cache-files-*/`, `.worktrees/`.
- Merge current feature branch to `main`.

### Phase 2 — Reliability & Performance
Scope: make local providers robust and unlock parallelism.
- Implement 400 context-length fallback for local providers (catch `openai.BadRequestError`, fall back to per-file with truncation).
- Add parallel directory processing (currently sequential in `_run_generation`).
- Add LLM response caching to avoid redundant calls during iteration.
- Resolve BitNet subprocess path issue on Windows or deprecate the provider.

### Phase 3 — Ecosystem Integration
Scope: connect `ctx` to the broader toolchain.
- MCP Server support (expose manifests via Model Context Protocol).
- Git-aware updates (detect changed files since last commit to trigger selective regeneration).
- CI/CD Action (GitHub Action that ensures `CONTEXT.md` files stay fresh).
- Custom prompt templates via `.ctxconfig`.
