# AGENTS

## schema_version
1

## What ctx Is
`ctx` is a deterministic, zero-LLM static AST, import-graph, and blast-radius structural analyzer for AI agents.
It compiles gitignored `.ctx/` tiered maps (`CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`), structured fleet capsules (`ctx export --capsule`), and directed reverse-dependency impact graphs (`ctx impact <target>`) across 11 programming languages — with zero LLM calls, zero API keys, zero background git hooks, and zero per-directory `CONTEXT.md` clutter.

## Install
```bash
pip install ctx-tool
```

- Requires Python 3.10+
- CLI entrypoint: `ctx` (or `python -m ctx`)
- Machine-readable JSON envelope mode: set `CTX_OUTPUT=json` or pass `--output json`
- Optional HTTP server extras: `pip install ctx-tool[serve]`

## Configure
`ctx` works with zero configuration and requires no external credentials.

### `.ctxconfig` (optional)
```yaml
max_depth: 6
extensions:
  - .py
  - .ts
  - .go
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CTX_OUTPUT` | `human` | Output mode: `human` or `json` |
| `CTX_MAX_DEPTH` | unlimited | Directory traversal depth cap |
| `CTX_EXTENSIONS` | all text/code files | Comma-separated file extension allowlist |

## Commands
### `ctx init [path]`

Bootstrap deterministic `.ctx/` structural maps in a git repository without installing git hooks or writing per-directory sidecars.

What it does:
1. Extracts static AST/parser symbols, imports, entrypoints, operational surfaces, and governance docs (`ctx.skeleton.extract_skeleton`)
2. Creates `.ctx/` with `CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`, `metadata.json`, and `.ctx/.gitignore`
3. Adds `.ctx/` to root `.gitignore`
4. Cleans up any legacy `# >>> ctx-hook-start` git hook blocks if present

Common flags:
- `--force` — reinitialize even if `.ctx/` already exists
- `--output json` — emit JSON envelope

### `ctx uninit [path]`

Remove `.ctx/` infrastructure, strip `.ctx/` from root `.gitignore`, and remove any legacy ctx git hook blocks.

### `.ctx/` Directory Structure

| File | Purpose |
|------|---------|
| `CONTEXT-0.md` | 1-page repository architecture, authority boundaries, entrypoints, and subsystem overview |
| `CONTEXT-1.md` | Cross-directory dependency flows, exported symbols, and boundary contracts |
| `CONTEXT.md` | Full structural map including file-level public signatures |
| `metadata.json` | Deterministic metadata (`repo_id`, `structural_hash`, `boundary_doc_hash`, timestamps) |
| `.gitignore` | Ignores all `.ctx/` contents from git |

### `ctx refresh [path]`

Deterministically refresh `.ctx/` maps when `structural_hash` or `boundary_doc_hash` has drifted (skipping writes when unchanged).

Common flags:
- `--force` — rewrite `.ctx/` maps even if hashes match
- `--dry-run` — check whether `.ctx/` maps are stale without writing
- `--max-depth <n>` — limit directory traversal depth
- `--output json` — emit JSON envelope

```json
{
  "status": "success",
  "command": "refresh",
  "metadata": {
    "version": "1.1.0",
    "elapsed_ms": 38,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "dirs_processed": 3,
    "dirs_skipped": 0,
    "files_processed": 24,
    "tokens_used": 0,
    "errors": [],
    "budget_exhausted": false,
    "strategy": "tier2",
    "est_cost_usd": 0.0,
    "stale_directories": [],
    "warnings": []
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx check [path]`

Evaluate `.ctx/` structural freshness, frontmatter/export integrity, token footprint, or diff status.

Common flags:
- `--verify` — validate frontmatter, presence of all `.ctx/` tiers, and structural hash freshness
- `--stats` — emit aggregate coverage and estimated token statistics (`--verbose` for row breakdown)
- `--diff` — report whether `.ctx/CONTEXT.md` is stale (`--quiet` / `--stat`)
- `--check-exit` — exit `1` when maps are stale or missing
- `--output json` — emit JSON envelope

```json
{
  "status": "success",
  "command": "check",
  "metadata": {
    "version": "1.1.0",
    "elapsed_ms": 19,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "mode": "health",
    "directories": [
      {
        "path": ".",
        "status": "fresh"
      }
    ],
    "summary": {
      "total": 1,
      "fresh": 1,
      "stale": 0,
      "missing": 0,
      "check_exit": false,
      "tier2": true
    }
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx export [path]`

Export `.ctx/` structural maps (rendering deterministically on the fly even if `ctx init` has not been run) or emit a structured fleet capsule.

Common flags:
- `--depth 0|1` — select `CONTEXT-0.md` (`0`), `CONTEXT-1.md` (`1`), or full `CONTEXT.md` (omitted)
- `--filter all|stale|missing` — filter exported maps
- `--capsule` — emit a deterministic `FleetCapsuleResult` for `project-ledger` and `gbrain` ingestion
- `--out-file <file>` (or `-o <file>`) — write markdown or `.json` capsule to disk
- `--output json` — emit JSON envelope

```json
{
  "status": "success",
  "command": "export",
  "metadata": {
    "version": "1.1.0",
    "elapsed_ms": 24,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "manifests_exported": 1,
    "filter": "all",
    "depth": 0,
    "content": "# .ctx/CONTEXT-0.md\n\n---\ngenerated: \"2026-11-10T00:00:00Z\"\n"
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx impact <target> [path]`

Analyze directed reverse-dependency blast radius, coupled test suites, affected entrypoints/surfaces, cycles, and governing authority documents for a file path, subsystem directory, or symbol name.

Common flags:
- `--depth <n>` — cap reverse-dependency BFS hops (`>= 1`)
- `--output json` — emit JSON envelope

### `ctx reset [path]`

Remove legacy per-directory `CONTEXT.md` files from a source tree without touching `.ctx/`.

Common flags:
- `--yes` (`-y`) — required for non-interactive deletion
- `--dry-run` — list legacy `CONTEXT.md` files without deleting them
- `--output json` — emit JSON envelope

```json
{
  "status": "success",
  "command": "reset",
  "metadata": {
    "version": "1.1.0",
    "elapsed_ms": 6,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "manifests_removed": 0,
    "paths": []
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx benchmark [paths...]`

Run the reproducible Phase 27.1 deterministic static-oracle A/B/C navigation & blast-radius benchmark (`raw_grep` vs `tier1_manifests` vs `tier2_plus_impact`).

Common flags:
- `--out-file <file>` (`-o <file>`) — write Markdown or `.json` benchmark report
- `--output json` — emit JSON envelope

## Exit Codes
| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Validation failure, stale/missing `.ctx/` with `--check-exit`, or invalid arguments |

## Error Codes
| Code | Meaning | Recommended Action |
|------|---------|-------------------|
| `init_failed` | `ctx init` failed (e.g., not a git repo or already initialized) | Pass `--force` or run inside a git repository |
| `uninit_failed` | `ctx uninit` failed (e.g., `.ctx/` not present or locked) | Verify `.ctx/` exists and no write lock is active |
| `stale_manifests` | `.ctx/` maps are stale or missing under `--check-exit` | Run `ctx refresh .` or `ctx init .` |
| `invalid_manifests` | `.ctx/` verification found missing or malformed tier files | Run `ctx refresh . --force` |
| `invalid_target` | `ctx impact` target did not match any file, subsystem, or symbol | Pass a valid repo-relative path or symbol name |
| `confirmation_required` | `ctx reset` invoked non-interactively without `--yes` | Re-run with `--yes` |
| `lock_held` | Another `ctx` write operation owns the lock | Wait and retry |
| `invalid_usage` | Invalid CLI flag or argument | Check `ctx <cmd> --help` |
| `unknown_error` | Unclassified runtime failure | Inspect error message |

## Integration Patterns
### MCP Server

Project-local `.mcp.json`:

```json
{
  "mcpServers": {
    "ctx": {
      "command": "ctx",
      "args": ["serve", "--mcp"]
    }
  }
}
```

Available MCP tools (`ctx serve --mcp`):

| Tool | Description |
|------|-------------|
| `ctx_refresh` | Deterministically refresh `.ctx/` structural maps |
| `ctx_check` | Validate `.ctx/` freshness, structure, and token stats |
| `ctx_export` | Export `.ctx/` maps or structured `--capsule` payload |
| `ctx_reset` | Remove legacy per-directory `CONTEXT.md` files |
| `ctx_impact` | Compute reverse-dependency blast radius and coupled tests |

Available read-only MCP resources (`ctx serve --mcp` after `ctx init` or `ctx refresh`):

| Resource URI | MIME Type | Description |
|--------------|-----------|-------------|
| `ctx://.ctx/CONTEXT.md` | `text/markdown` | Full structural & signature map |
| `ctx://.ctx/CONTEXT-1.md` | `text/markdown` | Depth-1 module dependency & boundary map |
| `ctx://.ctx/CONTEXT-0.md` | `text/markdown` | Depth-0 1-page architecture, entrypoints & authority map |
| `ctx://.ctx/metadata.json` | `application/json` | Init metadata and structural/boundary SHA-256 hashes |

### Python Consumer SDK (`ctx.sdk`)

Zero-dependency reader for tools consuming `.ctx/` exports:

```python
from ctx.sdk import CtxProject

proj = CtxProject.load("/path/to/repo")
context_0 = proj.get_context(depth=0)
stale = proj.is_stale()
```

### Agent Orientation Workflow

```bash
ctx export . --depth 0                  # zero-setup 1-page architectural orientation
ctx impact src/pkg/module.py .          # inspect reverse dependents + coupled tests before editing
```

### Documentation Hygiene Gate

When editing human-facing guides (`README.md`, `CONTRIBUTING.md`, `RUNBOOK.md`, `architecture.md`, `rules.md`, `docs/benchmarks/*.md`), lead with concrete inputs and outputs, keep `README.md` open with a `1..60` word `## TL;DR` (and `<= 100` lines total), expand domain acronyms at first use, keep prose sentences `<= 45` words, avoid banned AI/corporate filler, and run `python3 -m unittest tests/test_doc_hygiene.py -v` (see [CONTRIBUTING.md](./CONTRIBUTING.md#documentation-hygiene)).

## Manifest Format
Generated `.ctx/CONTEXT-*.md` files begin with deterministic YAML frontmatter followed by structured Markdown sections:

```yaml
---
generated: "2026-11-10T00:00:00Z"
generator: ctx/1.1.0
mode: tier2
tier: CONTEXT-0
structural_hash: "sha256:..."
boundary_doc_hash: "sha256:..."
files: 24
subsystems: 3
---
```

## Security
- Zero network calls and zero third-party LLM transmissions during `init`, `refresh`, `check`, `export`, `impact`, or `benchmark`.
- `ctx serve` and `CtxMCPServer` confine all resolved paths to the explicit served root and reject absolute paths and `..` traversal.
- Write operations use kernel-fenced locks (`CtxLock`) and atomic file replacement (`os.replace`) to prevent concurrent corruption.
