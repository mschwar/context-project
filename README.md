# ctx

Filesystem-native context layer for AI agents.

`ctx` generates `CONTEXT.md` manifests (or zero-LLM `.ctx/` Tier 2 architectural & invariant maps) so AI agents can orient and navigate codebases without reading every file. Manifests use portable repo-relative headings, deterministic filesystem listings, and SHA-256 staleness verification.

## Quick Start

```bash
pip install ctx-tool
export ANTHROPIC_API_KEY="sk-..."
ctx refresh .
```

Or bootstrap self-maintaining `.ctx/` exports and background git hooks (with optional zero-LLM `--tier2` architectural synthesis):

```bash
ctx init . --tier2   # zero-LLM structural & boundary-doc map in .ctx/
ctx init .           # full per-directory CONTEXT.md tree + .ctx/ + git hooks
```

## What It Costs

ctx uses lightweight LLM calls (Haiku-class models by default, or zero-cost local Ollama / `--tier2`). Real-world benchmarks:

| Tree | Dirs | Files | Cost | Time |
|------|------|-------|------|------|
| 31 dirs | 31 | 566 | $0.11 | 7 min |
| 171 dirs | 171 | ~1,200 | ~$1.26 | ~15 min |

Runs are incremental and disk-cached — unchanged directories and files cost zero tokens.

## For Agents

Tell your agent: install `ctx-tool`, run `ctx refresh .`, then read [AGENTS.md](./AGENTS.md) for the full command contract, JSON output schemas, error codes, and integration patterns.

For MCP clients, copy [`mcp.json`](./mcp.json) into `.mcp.json` / `.cursor/mcp.json` or run `ctx serve --mcp` (exposes tools + read-only `ctx://.ctx/*` resources).

## Commands

| Command | Purpose |
|---------|---------|
| `ctx init [path]` | Bootstrap `.ctx/` tiered exports + git hooks (`--tier2` for zero-LLM map) |
| `ctx uninit [path]` | Remove `.ctx/` exports and ctx git hook blocks |
| `ctx refresh <path>` | Generate or update manifests (Tier 1 or Tier 2) |
| `ctx check <path>` | Validate manifest health, `--verify` bodies, `--stats`, or `--diff` |
| `ctx export <path>` | Concatenate manifests or emit `--capsule` structural payload |
| `ctx stats [path]` | Show coverage or `--board` refresh/cost telemetry (`--global`, `--trend`) |
| `ctx setup [path]` | Detect provider, write `.ctxconfig`, or run `--check` preflight gate |
| `ctx impact <target>` | Analyze reverse-dependency blast radius, coupled tests, and governing docs |
| `ctx jev <subcmd>` | List, execute (`decide`), or evaluate (`eval`) Type 1 Jev System-One heads |
| `ctx benchmark [paths]` | Run Phase 27.1 static-oracle A/B/C navigation & blast-radius benchmark |
| `ctx reset <path>` | Remove generated `CONTEXT.md` manifests |
| `ctx serve --mcp` | Expose tools and `.ctx/` resources via MCP (stdio JSON-RPC) |

Key flags: `--until-complete` (auto-retry large trees), `--output json` (machine-readable), `--force` (regenerate all), `--watch` (live refresh), `--verify --check-exit` (strict verification gate).

## Configuration

Works out of the box with `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. For local models:

```bash
ctx refresh . --setup   # auto-detects Ollama or LM Studio
ctx setup --check .     # 7-check preflight readiness gate
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
