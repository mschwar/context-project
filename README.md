# ctx

Deterministic, zero-LLM static AST, import-graph, and blast-radius structural analyzer for AI agents.

`ctx` extracts multi-language symbol signatures, directed module dependencies, operational surfaces (CLI commands, HTTP routes, MCP tools/resources, env vars), and governance boundaries directly from source code — zero API keys, zero LLM tokens, zero per-directory `CONTEXT.md` sidecar litter, and zero background git hooks.

## Why Zero-LLM Static Maps?

Per the repository's [Phase 27.1 deterministic static-oracle benchmark](./docs/benchmarks/phase27-1-navigation-benchmark.md), per-directory LLM `CONTEXT.md` manifests were retired after losing to `raw_grep` by `-11.5 pp` mean recall (`-70.1 pp` on operational surfaces) while burning ~8.6k LLM tokens per implementation commit. Deterministic `.ctx/` structural maps + `ctx impact` deliver `+18.7 pp` higher recall than `raw_grep` (`100%` multi-hop blast-radius recall) at **$0.00 and 0 LLM tokens**.

## Quick Start

```bash
pip install ctx-tool

ctx init .                              # bootstrap gitignored .ctx/ structural maps (~50 ms)
ctx refresh .                           # deterministically refresh .ctx/ when signatures change
ctx export . --depth 0                  # 1-page architecture, entrypoints & authority map
ctx export . --capsule                  # structured fleet capsule for project-ledger / gbrain
ctx impact src/ctx/skeleton.py .        # reverse-dependency blast radius & coupled tests
```

## For Agents & MCP Clients

Read [AGENTS.md](./AGENTS.md) for the command contract, JSON output envelopes, error codes, and Python SDK (`ctx.sdk.CtxProject`).

For MCP clients, copy [`mcp.json`](./mcp.json) into `.mcp.json` or run `ctx serve --mcp` (exposes `ctx_refresh`, `ctx_check`, `ctx_export`, `ctx_reset`, `ctx_impact`, and read-only `ctx://.ctx/*` resources).

## Commands

| Command | Purpose |
|---------|---------|
| `ctx init [path]` | Create gitignored `.ctx/` tiered maps (`CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`) |
| `ctx uninit [path]` | Remove `.ctx/` directory and strip any legacy ctx git hook blocks |
| `ctx refresh [path]` | Deterministically update `.ctx/` maps when structural or boundary hashes change |
| `ctx check [path]` | Validate `.ctx/` freshness, `--verify` frontmatter/exports, `--stats`, or `--diff` |
| `ctx export [path]` | Export `.ctx/` maps (or render on-the-fly) or emit `--capsule` payload |
| `ctx impact <target>` | Compute directed reverse-dependency blast radius, coupled tests, and governing docs |
| `ctx benchmark [paths]` | Run reproducible Phase 27.1 static-oracle A/B/C navigation benchmark |
| `ctx reset [path]` | Clean up legacy per-directory `CONTEXT.md` files (`--yes`, `--dry-run`) |
| `ctx serve [path]` | Expose MCP tools & resources (`--mcp`) or optional FastAPI HTTP server |

## Configuration (Optional)

`ctx` requires zero configuration. Optional `.ctxconfig` (YAML) or environment variables:

```yaml
max_depth: 6
extensions: [".py", ".ts", ".go", ".rs"]
```

## Docs

| Doc | Audience |
|-----|----------|
| [AGENTS.md](./AGENTS.md) | Agents — command contract, JSON schemas, MCP & SDK integration |
| [architecture.md](./architecture.md) | Developers — static AST/import-graph engine and `.ctx/` layout |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contributors — dev setup and test workflow |
| [docs/benchmarks/phase27-1-navigation-benchmark.md](./docs/benchmarks/phase27-1-navigation-benchmark.md) | Empirical A/B/C navigation & blast-radius benchmark |

## License

MIT
