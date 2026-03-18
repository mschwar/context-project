# ctx

[![PyPI](https://img.shields.io/pypi/v/ctx-tool)](https://pypi.org/project/ctx-tool/)
[![Python Version](https://img.shields.io/pypi/pyversions/ctx-tool)](https://pypi.org/project/ctx-tool/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Generates persistent `CONTEXT.md` manifests for every directory in your project so AI agents can navigate large codebases without reading every file.

## Quick Start

```bash
pip install ctx-tool   # installs the 'ctx' command
ctx refresh . --setup  # auto-detects your LLM provider, writes .ctxconfig, refreshes manifests
ctx check .
ctx export . --depth 1
```

That's it. Every directory now has a `CONTEXT.md` that summarises its contents for any AI tool that reads it.

Legacy aliases like `ctx setup`, `ctx init`, `ctx update`, `ctx status`, and `ctx clean` still work, but they are hidden and deprecated in favor of the canonical agent surface.

## What it does

`ctx` walks your project tree bottom-up, sends each directory's file contents to an LLM, and writes a structured `CONTEXT.md` summary. Subsequent runs only regenerate manifests whose source files have changed. The result is a persistent, hierarchical context layer that agents and humans can read at any depth without a separate database.

## Commands

| Command | Description |
|---------|-------------|
| `ctx refresh .` | Refresh manifests using the best strategy automatically (full, smart, or incremental) |
| `ctx refresh . --force` | Regenerate all manifests unconditionally |
| `ctx refresh . --setup` | Auto-detect provider, write `.ctxconfig`, then refresh |
| `ctx refresh . --watch` | Refresh once, then watch for file changes |
| `ctx check .` | Show manifest health across the tree |
| `ctx check . --verify` | Validate frontmatter, freshness, and coverage |
| `ctx check . --stats` | Show coverage totals across the tree |
| `ctx check . --diff` | Show which manifests changed since the last git ref |
| `ctx export .` | Concatenate manifests (respects `.ctxignore`) |
| `ctx reset . --yes` | Remove all manifests under a tree |
| `ctx reset . --dry-run` | Preview which manifests would be deleted |
| `ctx serve [PATH]` | Serve manifests over HTTP (default: current directory) |

## Configuration

Create `.ctxconfig` in your project root:

```yaml
provider: anthropic        # anthropic | openai | ollama | lmstudio
model: claude-3-5-haiku-20241022
batch_size: 10             # files per LLM call (tune for local models)
token_budget: 100000       # stop after this many tokens
max_tokens_per_run: 100000 # hard token guardrail (not exposed as a CLI flag)
max_usd_per_run: 1.00      # hard spend guardrail (not exposed as a CLI flag)
cache_path: .ctx-cache/llm_cache.json
```

Every scalar config field also supports a `CTX_*` environment variable, including `CTX_BASE_URL`, `CTX_MAX_FILE_TOKENS`, `CTX_MAX_DEPTH`, `CTX_TOKEN_BUDGET`, `CTX_BATCH_SIZE`, `CTX_CACHE_PATH`, `CTX_MAX_CACHE_ENTRIES`, `CTX_WATCH_DEBOUNCE`, `CTX_MAX_TOKENS_PER_RUN`, `CTX_MAX_USD_PER_RUN`, and `CTX_EXTENSIONS`.

## Local LLMs

Works with Ollama and LM Studio — no API key required.

```yaml
provider: ollama
model: llama3.2
base_url: http://localhost:11434/v1
```

## Pre-commit hook

Keep manifests fresh automatically:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/mschwar/context-project
    rev: v0.8.0
    hooks:
      - id: ctx-check
```

Run `ctx refresh . --force` once before the hook will pass on a new repo.

## Links

- [Architecture](./architecture.md) — bottom-up context strategy
- [Contributing](./CONTRIBUTING.md) — agentic workflow
- [Phase 16 Handoff](./PHASE16_HANDOFF.md) — current gate order and small-model guardrails
- [State](./state.md) — current roadmap
