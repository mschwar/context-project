# ctx

## TL;DR

**Point `ctx` at a source repository to map its code structure and edit blast radius for coding agents.** It parses syntax trees, module imports, entrypoints, and rule files locally. Out come gitignored `.ctx/` Markdown maps, JSON capsules, and coupled test lists — with zero API keys or language model calls.

## Why Static Maps Beat Sidecars

In the [Phase 27.1 navigation benchmark](./docs/benchmarks/phase27-1-navigation-benchmark.md), per-directory LLM `CONTEXT.md` files lost to `raw_grep` by `-11.5` percentage points in mean recall (`-70.1` points on operational surfaces) while burning roughly `8.6k` tokens per commit.

`ctx` replaces per-directory sidecars and git hooks with deterministic Abstract Syntax Tree (AST) and import-graph extraction. Combining `.ctx/` maps with `ctx impact` beat `raw_grep` by `+12.4` percentage points in mean recall (`100%` blast-radius recall, `88.2%` fewer context tokens) at **$0.00 and 0 tokens**.

## Quick Start

```bash
pip install ctx-tool

ctx init .                              # create gitignored .ctx/ structural maps (~50 ms)
ctx refresh .                           # refresh .ctx/ maps when code signatures change
ctx export . --depth 0                  # print 1-page architecture and entrypoint map
ctx export . --capsule                  # emit JSON fleet capsule for project-ledger / gbrain
ctx impact src/ctx/skeleton.py .        # trace reverse dependents and coupled test files
```

## Agents and Model Context Protocol (MCP) Clients

Read [AGENTS.md](./AGENTS.md) for the command contract, JSON output envelopes, error codes, and Python SDK (`ctx.sdk.CtxProject`).

For MCP clients, copy [`mcp.json`](./mcp.json) into `.mcp.json` or run `ctx serve --mcp`. The server exposes `ctx_refresh`, `ctx_check`, `ctx_export`, `ctx_reset`, `ctx_impact`, and read-only `ctx://.ctx/*` resources.

## Commands

| Command | Purpose |
|---------|---------|
| `ctx init [path]` | Create gitignored `.ctx/` tiered maps (`CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`) |
| `ctx uninit [path]` | Remove `.ctx/` and strip legacy `ctx` git hook blocks |
| `ctx refresh [path]` | Update `.ctx/` maps when structural or boundary hashes change |
| `ctx check [path]` | Check `.ctx/` freshness, `--verify` frontmatter, `--stats`, or `--diff` |
| `ctx export [path]` | Print `.ctx/` maps on demand or emit a `--capsule` JSON payload |
| `ctx impact <target>` | Trace reverse-dependency blast radius, coupled tests, and governing docs |
| `ctx benchmark [paths]` | Run the Phase 27.1 static-oracle A/B/C navigation benchmark |
| `ctx reset [path]` | Delete legacy per-directory `CONTEXT.md` files (`--yes`, `--dry-run`) |
| `ctx serve [path]` | Run the stdio MCP server (`--mcp`) or optional FastAPI HTTP server |

## Optional Configuration

`ctx` runs with zero configuration. Add an optional `.ctxconfig` YAML file or environment variables (`CTX_OUTPUT`, `CTX_MAX_DEPTH`, `CTX_EXTENSIONS`; see [AGENTS.md](./AGENTS.md#configure)) to customize traversal:

```yaml
max_depth: 6
extensions: [".py", ".ts", ".go", ".rs"]
```

## Documentation

| Guide | Audience |
|-------|----------|
| [AGENTS.md](./AGENTS.md) | Agents — command contract, JSON schemas, MCP, and Python SDK |
| [architecture.md](./architecture.md) | Developers — AST parser, import graph, and `.ctx/` layout |
| [RUNBOOK.md](./RUNBOOK.md) | Operators — CLI operations, validation, and PyPI release steps |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contributors — local verification, merge gates, and prose rules |
| [rules.md](./rules.md) | Contributors — Python typing, path safety, and test standards |
| [docs/benchmarks/phase27-1-navigation-benchmark.md](./docs/benchmarks/phase27-1-navigation-benchmark.md) | Researchers — A/B/C recall, token, and blast-radius results |

## License

MIT
