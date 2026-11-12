# Architecture: `ctx`

`ctx` is a deterministic, zero-LLM static analyzer that turns a source tree into compact architecture maps and reverse-dependency graphs for coding agents. Given a repository root, it extracts symbols, imports, operational surfaces, and governance docs, then writes tiered Markdown and JSON artifacts under `.ctx/`.

## Core Design Principles

### 1. Tiered Resolution (`.ctx/`)
Instead of scattering `CONTEXT.md` sidecars across every source folder, `ctx` writes three resolution tiers into one gitignored `.ctx/` directory at the repository root:
- **`CONTEXT-0.md`:** One-page repository overview covering languages, entrypoints, operational surfaces, authority docs, and top-level subsystems.
- **`CONTEXT-1.md`:** Cross-subsystem dependency edges, exported symbols, and boundary contracts.
- **`CONTEXT.md`:** Full file-by-file structural map with public symbol signatures.

### 2. Hash-Gated Determinism
`skeleton.py` computes two SHA-256 digests across sorted repository paths:
- **`structural_hash`:** Captures extracted symbol signatures, imports, entrypoints, and operational surfaces.
- **`boundary_doc_hash`:** Captures governing authority and architecture documents (`AGENTS.md`, `README.md`, `architecture.md`, `rules.md`, `CONTRIBUTING.md`).

`ctx refresh` rewrites `.ctx/` maps only when either digest changes (or when `--force` is passed), keeping repeated runs idempotent and fast.

### 3. Static Import Graph and Blast Radius
`impact.py` builds a directed cross-file dependency graph across 11 languages, detects strongly connected cycles with Tarjan's algorithm, and condenses components into topological layers. Given a file, directory, or symbol, `ctx impact` traces transitive reverse dependents, coupled tests, affected surfaces, and governing docs.

## Component Breakdown

| Module | Responsibility |
|--------|----------------|
| `api.py` | Programmatic Python interface (`init_project`, `uninit_project`, `refresh`, `check`, `export_context`, `build_fleet_capsule`, `analyze_impact`, `reset`) with zero Click coupling. |
| `cli.py` | Click command-line entrypoint wrapping `api.py` in human or JSON output modes. |
| `skeleton.py` | Static Abstract Syntax Tree (AST) and lexical parser dispatcher, operational surface detector — CLI, HTTP, Model Context Protocol (MCP), and env vars — reference-ranked `key_symbols` scorer, and `.ctx/CONTEXT-*.md` renderer. |
| `impact.py` | Directed dependency graph builder, Tarjan cycle detector, reverse-dependency breadth-first search, coupled test matcher, and surface/doc impact analyzer. |
| `lang_parsers/` | Per-language symbol and import extractors for Python, JavaScript/TypeScript, Go, Rust, Java, Kotlin, C#, Ruby, `PHP`, Swift, and Elixir. |
| `language_detector.py` | File extension to language classifier feeding `skeleton.py` and `impact.py`. |
| `init.py` | Bootstrap and teardown logic for `.ctx/` files, `metadata.json`, `.gitignore` entries, and legacy git hook block removal. |
| `benchmark.py` | Reproducible Phase 27.1 static-oracle benchmark comparing `raw_grep`, `tier1_manifests`, and `tier2_plus_impact`. |
| `mcp_server.py` | Standard input/output JSON-RPC 2.0 MCP server exposing `ctx_*` tools and read-only `ctx://.ctx/*` resources. |
| `sdk.py` | Zero-dependency consumer reader (`CtxProject.load`) for loading `.ctx/` tiers and checking freshness. |
| `server.py` | Optional FastAPI HTTP server for read-only `.ctx/` inspection (`ctx-tool[serve]`). |
| `lock.py` | Cross-process `.ctx-cache/lock` mutex using kernel file locks (`fcntl.flock` / `msvcrt.locking`) and stale-owner recovery. |
| `ignore.py` | `pathspec` filter combining `.ctxignore.default`, ancestor/root/nested `.gitignore` files, and `.ctxignore` overrides. |
| `hasher.py` | Deterministic SHA-256 file and tree hashing with symlink loop protection. |
| `config.py` | Configuration loader merging defaults, `.ctxconfig` YAML, environment variables, and CLI flags. |
| `output.py` | `OutputBroker` context manager guaranteeing single-object JSON envelopes on standard output when `CTX_OUTPUT=json`. |

## Data Flow

1. **Filter:** `ignore.py` walks the repository up to `max_depth`, pruning gitignored paths, `.ctx/`, `.ctx-cache/`, and binary files.
2. **Parse:** `skeleton.py` dispatches each source file to `lang_parsers/` to collect classes, functions, types, imports, CLI commands, HTTP routes, MCP registrations, and environment variables.
3. **Rank & Hash:** `skeleton.py` scores symbols by cross-file reference frequency and computes `structural_hash` and `boundary_doc_hash`.
4. **Render & Write:** Under `CtxLock`, `init.py` / `api.py` writes `CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`, and `metadata.json` atomically via temporary files and `os.replace`.
5. **Query Impact:** When `ctx impact <target>` runs, `impact.py` resolves internal module edges and returns direct dependents, transitive dependents, coupled tests, and governing docs.

## `.ctx/` Frontmatter Format

Every generated `.ctx/CONTEXT-*.md` file begins with deterministic YAML frontmatter:

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
