# Architecture: `ctx`

`ctx` is a filesystem-native context layer designed to help AI agents navigate large codebases. It provides a coarse-to-fine view of a project by generating and maintaining `CONTEXT.md` files in every directory.

The manifests are the navigation primitive. The durable product value is the generator that keeps them fresh with one command and without external infrastructure.

## Core Design Principles

### 1. Bottom-Up Generation
The generator traverses the directory tree from leaves to root. This ensures that a directory's children are summarized *before* the directory itself. This allows parent summaries to include high-level information from their children's `CONTEXT.md` files, creating a recursive summary structure.

### 2. Content-Based Staleness Detection
Every `CONTEXT.md` contains a `content_hash` in its frontmatter.
- **File Hash:** SHA-256 of the file's binary content.
- **Directory Hash:** SHA-256 of a sorted list of its children's names and hashes.
This recursive hashing ensures that any change in a leaf file propagates up the tree, marking all parent manifests as "stale" for incremental updates.

### 3. Decoupled LLM Strategy
The `LLMClient` protocol abstracts the summarization logic. Supported providers include:
- **Cloud:** Anthropic (Claude), OpenAI.
- **Local:** Ollama and LM Studio (via the OpenAI-compatible client).

BitNet is deprecated in this repo. Attempting to use it raises an informative error directing users to Ollama or LM Studio.

## Component Breakdown

| Component | Responsibility |
|-----------|----------------|
| `api.py` | Unified programmatic API — `refresh`, `check`, `export_context`, `reset`. Zero Click dependency. |
| `cli.py` | Entry point using `Click`. Thin wrapper over `api.py` with human/JSON output modes. |
| `generator.py` | The "Brain". Orchestrates tree walking, hashing, and LLM calls with depth-level parallelism. |
| `llm.py` | Provider implementations. Handles structured prompting, retries, and token tracking. |
| `config.py` | Hierarchical configuration resolution (Defaults -> `.ctxconfig` -> Env -> CLI). Budget guardrails and cost estimation. |
| `hasher.py` | Robust SHA-256 hashing logic with symlink loop detection. |
| `manifest.py` | Parsing and serializing `CONTEXT.md` (YAML + Markdown). Atomic writes via temp file + `os.replace`. |
| `output.py` | `OutputBroker` context manager for JSON envelope output mode. |
| `stats_board.py` | Persistent run-stats ledger. Records every `ctx refresh` invocation; exposes per-repo and global aggregates for `ctx stats --board`. |
| `mcp_server.py` | Stdio JSON-RPC 2.0 MCP server exposing `api.py` functions as tools. |
| `ignore.py` | `.gitignore`-style filtering using the `pathspec` library. |
| `git.py` | Git-aware changed-file detection for selective refresh. |
| `watcher.py` | File watching and debounced incremental refresh. |
| `server.py` | HTTP server for reading generated manifests remotely (optional `[serve]` extra). |

## Data Flow

1. **Scan:** Walk tree (filtered by `.ctxignore` and `max_depth`).
2. **Sort:** Order directories by depth descending (bottom-up).
3. **Hash:** Compute current `content_hash` for the directory.
4. **Compare:** If `update` mode, skip if the hash matches the existing manifest.
5. **Summarize Files:** Batch text files, send to LLM for one-line summaries. Detect binary files and extract metadata.
6. **Summarize Directory:** Send file summaries + existing child summaries to LLM to generate the directory's purpose and full markdown body.
7. **Write:** Save `CONTEXT.md` with updated frontmatter and body.

## Manifest Format (`CONTEXT.md`)

```markdown
---
generated: ISO-8601-Timestamp
generator: ctx/version
model: model-id
content_hash: sha256:hex-digest
files: count
dirs: count
tokens_total: aggregate-count
---
# /absolute/path

One-line purpose of this directory.

## Files
- **filename.py** — One-line summary.
- **data.bin** — [binary: ext, size]

## Subdirectories
- **subdir/** — One-line purpose (from its own CONTEXT.md).

## Notes
- Optional AI-generated or manual hints.
```
