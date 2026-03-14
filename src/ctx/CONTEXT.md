---
generated: '2026-03-14T23:44:41Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:b5efea138408c5cd90e11413cd0d62b0da192f38d9a26cfb17f18bab8a9eb764
files: 14
dirs: 1
tokens_total: 12746
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and LLM-powered directory summarization with manifest generation and serving.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md manifests.
- **config.py** — Loads and resolves configuration from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests.
- **watcher.py** — Monitors directory tree for file changes and triggers incremental manifest regeneration via debounced events.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source code files.

## Notes

- The generator module orchestrates the full pipeline: configuration loading, directory traversal, LLM summarization, and manifest writing.
- Ignore patterns and git integration enable selective processing of changed or non-excluded files.
- Multiple LLM providers (Anthropic, OpenAI) are supported via pluggable client implementations.
- The watcher and server modules enable real-time manifest updates and programmatic access via MCP.