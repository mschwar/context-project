# ctx

Filesystem-native context layer for AI agents.

`ctx` generates `CONTEXT.md` manifests for every directory in a project so AI agents can navigate with structured summaries instead of reading every file. One command refreshes the entire tree. Manifests are deterministic, verifiable, and cheap to maintain.

## Quick Start

```bash
pip install ctx-tool
export ANTHROPIC_API_KEY="sk-..."
ctx refresh .
```

That's it. Every directory now has a `CONTEXT.md` with a purpose summary, file descriptions, and subdirectory overviews.

## What It Costs

ctx uses lightweight LLM calls (Haiku-class models by default). Real-world benchmarks on personal document trees:

| Tree | Dirs | Files | Cost | Time |
|------|------|-------|------|------|
| 31 dirs | 31 | 566 | $0.11 | 7 min |
| 171 dirs | 171 | ~1,200 | ~$1.26 | ~15 min |

Runs are incremental — unchanged directories are skipped, so subsequent refreshes cost near zero.

## For Agents

Tell your agent: install `ctx-tool`, run `ctx refresh .`, then read [AGENTS.md](./AGENTS.md) for the full command contract, JSON output schemas, error codes, and integration patterns.

For MCP clients, copy the config from [`mcp.json`](./mcp.json) into your client's MCP config (`.mcp.json` for Claude Code, `.cursor/mcp.json` for Cursor) or run `ctx serve --mcp`.

## Commands

| Command | Purpose |
|---------|---------|
| `ctx refresh <path>` | Generate or update manifests |
| `ctx check <path>` | Validate manifest health, coverage, freshness |
| `ctx export <path>` | Concatenate manifests for agent ingestion |
| `ctx reset <path>` | Remove all generated manifests |
| `ctx serve --mcp` | Expose manifests via MCP (stdio JSON-RPC) |

Key flags: `--until-complete` (auto-retry large trees), `--output json` (machine-readable), `--force` (regenerate all), `--watch` (live refresh).

## Configuration

Works out of the box with `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. For local models:

```bash
ctx refresh . --setup   # auto-detects Ollama or LM Studio
```

Fine-tune with `.ctxconfig`:

```yaml
provider: anthropic
model: claude-haiku-4-5-20251001
max_usd_per_run: 1.00
```

Full config reference in [AGENTS.md](./AGENTS.md#configure).

## Docs

| Doc | Audience |
|-----|----------|
| [AGENTS.md](./AGENTS.md) | Agents — command contract, schemas, integration patterns |
| [architecture.md](./architecture.md) | Developers — engine design and data flow |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contributors — dev setup and workflow |
| [state.md](./state.md) | Maintainers — roadmap and phase history |

## License

MIT
