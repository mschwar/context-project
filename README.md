# ctx

[![PyPI](https://img.shields.io/pypi/v/ctx-tool)](https://pypi.org/project/ctx-tool/)
[![Python Version](https://img.shields.io/pypi/pyversions/ctx-tool)](https://pypi.org/project/ctx-tool/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Generates persistent `CONTEXT.md` manifests for every directory in your project so AI agents can navigate large codebases without reading every file.

## Quick Start

```bash
pip install ctx-tool   # installs the 'ctx' command
ctx setup              # auto-detects your LLM provider and writes .ctxconfig
ctx init .
ctx status .
```

That's it. Every directory now has a `CONTEXT.md` that summarises its contents for any AI tool that reads it.

## What it does

`ctx` walks your project tree bottom-up, sends each directory's file contents to an LLM, and writes a structured `CONTEXT.md` summary. Subsequent runs only regenerate manifests whose source files have changed. The result is a persistent, hierarchical context layer that agents and humans can read at any depth without a separate database.

## Commands

| Command | Description |
|---------|-------------|
| `ctx setup` | Auto-detect provider and write `.ctxconfig` |
| `ctx init .` | Generate manifests for **all** directories (unconditional) |
| `ctx init . --no-overwrite` | Generate only missing/stale manifests (incremental) |
| `ctx update .` | Regenerate only stale manifests |
| `ctx smart-update .` | Regenerate only directories with git-changed files |
| `ctx status .` | Show how many manifests are stale or missing |
| `ctx diff .` | Show which CONTEXT.md files changed since last commit |
| `ctx export .` | Concatenate manifests for downstream agent ingestion |
| `ctx stats .` | Show coverage totals across the tree |
| `ctx clean . --yes` | Remove all manifests under a tree |
| `ctx watch .` | Auto-regenerate on file save |
| `ctx serve` | Serve manifests over HTTP |

## Configuration

Create `.ctxconfig` in your project root:

```yaml
provider: anthropic        # anthropic | openai | ollama | lmstudio
model: claude-3-5-haiku-20241022
batch_size: 10             # files per LLM call (tune for local models)
token_budget: 100000       # stop after this many tokens
cache_path: .ctx-cache/llm_cache.json
```

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

Run `ctx init .` once before the hook will pass on a new repo.

## Links

- [Architecture](./architecture.md) — bottom-up context strategy
- [Contributing](./CONTRIBUTING.md) — agentic workflow
- [Phase 16 Handoff](./PHASE16_HANDOFF.md) — current gate order and small-model guardrails
- [State](./state.md) — current roadmap
