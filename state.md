# State of `ctx`

Current architecture, release state, and active capabilities of `ctx` (`ctx-tool` `v2.0.0`). Historical phase logs (Phases 1–34) live in [`archive/state-history-phases-1-34.md`](./archive/state-history-phases-1-34.md).

## Current Health (`v2.0.0`)

| Surface | Status | Details |
|---------|--------|---------|
| Runtime | Zero-LLM deterministic compiler | Pure static AST, import-graph, and blast-radius extraction (`click`, `pyyaml`, `pathspec` only) |
| Language coverage | 13 languages | Python, JavaScript, TypeScript, Go, Rust, Java, Kotlin, C#, Ruby, `PHP`, Swift, Elixir, C, and C++ |
| `.ctx/` artifacts | Tiered maps + fleet capsule | `CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`, `capsule.json`, and `metadata.json` |
| Cross-host identity | Canonical `repo_id` | Normalized `remote.origin.url` (`host/owner/repo`) with root-commit SHA fallback across clones and worktrees |
| Impact & diff gate | File, symbol, subsystem, and git diff | `ctx impact <target>`, `ctx impact --git-diff <rev>`, and `ctx impact --staged` compile proportional test plans |
| Monorepo edges | Workspace-aware | Resolves Python `packages/*/src/<pkg>`, JS/TS workspace `package.json`, and Rust `Cargo.toml` crate edges |
| Fleet integration | Live sensor | Consumed by `project-ledger` (`ledger/capsules.py`) via `.ctx/capsule.json` or `ctx export --capsule` |
| Release & CI gate | Local verification + `GitGuardian` | Hosted cloud-VM pull-request triggers retired (`publish.yml` is manual `workflow_dispatch`) |

## Core Primitives (`src/ctx/`)

1. **Skeleton & Surface Compiler (`skeleton.py`, `lang_parsers/`):** Walks git-filtered trees respecting `.ctxconfig` (`max_depth`, `extensions`) and `CTX_*` env vars, extracts symbols, imports, CLI/HTTP/MCP/env surfaces, and live governance docs, and ranks `key_symbols` by Python AST identifier references + inbound module centrality.
2. **Import Graph & Proportional Verification Compiler (`impact.py`):** Builds a 13-language directed internal dependency graph (with Tarjan cycle detection and topological layers) and compiles either single targets (`analyze_impact`) or git diffs (`analyze_diff_impact`) into unioned blast radius, coupled tests, and `verification_scope` (`none`, `docs_only`, `targeted_tests`, `broad_suite`).
3. **Atomic Persistence & Fleet Capsule (`init.py`, `api.py`, `lock.py`, `sdk.py`):** Writes `.ctx/CONTEXT-*.md`, `.ctx/capsule.json`, and `.ctx/metadata.json` atomically under `CtxLock` when `structural_hash` or `boundary_doc_hash` changes.
4. **Agent Delivery Surfaces (`cli.py`, `mcp_server.py`, `server.py`):** Exposes human/JSON CLI commands, stdio JSON-RPC 2.0 MCP tools (`ctx_refresh`, `ctx_check`, `ctx_export`, `ctx_reset`, `ctx_impact`) plus `ctx://.ctx/*` resources, and an optional read-only FastAPI HTTP server.

## Completed Roadmap Waves

- **Phases 1–29 (Archived):** Tier-1 LLM manifest era, security hardening, `OutputBroker`, unified `api.py`, `CtxLock`, MCP server/resources, and `ctx.sdk` (see [`archive/state-history-phases-1-34.md`](./archive/state-history-phases-1-34.md)).
- **Phases 30–33:** Tier-2 `.ctx/` root architecture synthesis, `FleetCapsuleResult`, directed reverse-dependency graph (`ctx impact`), and the [Phase 27.1 static-oracle benchmark](./docs/benchmarks/phase27-1-navigation-benchmark.md).
- **Wave 3A (`PR #83`):** Excised all LLM/API/Jev/background-hook machinery in favor of 100% deterministic local static compilation.
- **Waves A–D (`v2.0.0`):**
  - **Wave A:** Fixed `.ctxconfig` `max_depth` / `CTX_MAX_DEPTH` wiring, canonicalized cross-host `repo_id`, archived retired pre-Wave-3A design docs, retired tag-triggered cloud-VM CI, and converged control-plane docs.
  - **Wave B:** Shipped AST + inbound-hub `key_symbols` ranking and atomic `.ctx/capsule.json` persistence on `ctx init` and `ctx refresh`.
  - **Wave C:** Shipped `ctx impact --git-diff` and `ctx impact --staged` across CLI, Python API, and `ctx_impact` MCP tool for proportional verification compilation.
  - **Wave D:** Added C/C++ parser (`c_cpp_parser.py`) + `#include` graph edges (13-language parity) and Python/JS/TS/Rust monorepo workspace resolution.

## Forward Queue

Active follow-on work is tracked in [`TODOS.md`](./TODOS.md).
