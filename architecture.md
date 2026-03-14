# Architecture: `ctx`

`ctx` is a filesystem-native context layer designed to help AI agents navigate large codebases. It provides a "coarse-to-fine" view of a project by generating and maintaining `CONTEXT.md` files in every directory.

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
- **Cloud:** Anthropic (Claude), OpenAI (GPT-4o-mini).
- **Local:** Ollama, LM Studio (OpenAI-compatible), BitNet (subprocess-based inference).

## Component Breakdown

| Component | Responsibility |
|-----------|----------------|
| `cli.py` | Entry point using `Click`. Handles `init`, `update`, and `status`. |
| `generator.py` | The "Brain". Orchestrates tree walking, hashing, and LLM orchestration. |
| `llm.py` | Provider implementations. Handles structured prompting and token tracking. |
| `hasher.py` | Robust SHA-256 hashing logic with symlink loop detection. |
| `manifest.py` | Parsing and serializing `CONTEXT.md` (YAML + Markdown). |
| `config.py` | Hierarchical configuration resolution (Defaults -> `.ctxconfig` -> Env -> CLI). |
| `ignore.py` | `.gitignore`-style filtering using the `pathspec` library. |

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
