# AGENTS

This file is the canonical onboarding and workflow contract for agents contributing to `ctx`.

## Mission
Build and maintain `ctx`, a filesystem-native context layer that generates recursive `CONTEXT.md` summaries to help AI agents navigate large codebases.

## Current State
- **Core Engine**: Fully implemented with bottom-up traversal, incremental hashing, parallel processing, and persistent LLM disk cache.
- **LLM Clients**: Anthropic and OpenAI supported (including Ollama and LM Studio). **BitNet is deprecated** — `create_client("bitnet")` raises an informative error directing users to Ollama or LM Studio.
- **Language Parsers**: Python (`ast`-based), JavaScript/TypeScript (regex), Rust (regex). Wired into `generator._prepare_file_entry`; metadata is passed to the LLM prompt for richer summaries.
- **Test Coverage**: 127 tests across all modules (`cli`, `config`, `generator`, `hasher`, `ignore`, `llm`, `manifest`, `server`, `language_detector`, `python_parser`, `js_ts_parser`, `rust_parser`, integration).
- **Documentation**: `architecture.md`, `rules.md`, `state.md`, `RUNBOOK.md`, and `CONTRIBUTING.md` define the system.

> **Branch notice**: As of March 2026, Phases 1–6 are complete on `main`. Phase 7 is not yet scoped. New work should branch from `main`.

> **Manifest refresh rule**: Any commit that adds or modifies source files must include a `ctx update .` pass to regenerate stale `CONTEXT.md` files before pushing. The `CTX Manifest Check` CI job enforces this and will fail otherwise.

> **Dry-run note**: CLI paths that do not call an LLM must pass `require_api_key=False` to `load_config` to avoid `UsageError` in CI environments without API keys set.

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
3. file a reflection artifact,
4. implement feasible in-scope reflection suggestions or explicitly defer them,
5. update durable docs if the reflection changes standing guidance,
6. update the roadmap status,
7. deliver the end-of-gate report and wait for user disposition.

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

### Phase 7 — (Not Yet Scoped)

Candidates from Phase 6 reflection (no gate condition set yet):
- **Go parser** — export by capitalization; natural next language.
- **`ctx watch`** — file watcher for auto-regeneration (`watchdog`/`watchfiles`).
- **Cache model-awareness** — include model name in disk cache key to prevent stale summaries on model switch.

**Branch:** `feat/phase7-*` (branch from `main` after Phase 7 is scoped)
