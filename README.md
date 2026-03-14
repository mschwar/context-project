# ctx

Generates `CONTEXT.md` manifests for every directory in your project so AI agents can navigate large codebases without reading every file.

## Quick Start

```bash
pip install ctx-tool
export ANTHROPIC_API_KEY=sk-...
ctx init .
ctx status .
```

That's it. Every directory now has a `CONTEXT.md` that summarises its contents for any AI tool that reads it.

## What it does

`ctx` walks your project tree bottom-up, sends each directory's file contents to an LLM, and writes a structured `CONTEXT.md` summary. Subsequent runs only regenerate manifests whose source files have changed. The result is a persistent, always-fresh context layer that agents and humans can read at any depth.

## Commands

| Command | Description |
|---------|-------------|
| `ctx init .` | Generate manifests for all directories |
| `ctx update .` | Regenerate only stale manifests |
| `ctx smart-update .` | Regenerate only directories with git-changed files |
| `ctx status .` | Show how many manifests are stale or missing |
| `ctx watch .` | Auto-regenerate on file save |
| `ctx serve .` | Expose manifests via Model Context Protocol (MCP) |

## Configuration

Create `.ctxconfig` in your project root:

```yaml
provider: anthropic        # anthropic | openai | ollama | lmstudio
model: claude-haiku-4-5-20251001
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

## Links

- [Architecture](./architecture.md) — bottom-up context strategy
- [Contributing](./CONTRIBUTING.md) — agentic workflow
- [State](./state.md) — current roadmap
