---
generated: '2026-03-14T23:33:59Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:90e0b86c8990397ed9a9134e61734ebc0d557973132153145e42e8dcebf832ba
files: 14
dirs: 1
tokens_total: 12744
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and LLM-powered directory summarization with manifest generation and incremental updates.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and check CONTEXT.md manifests.
- **config.py** — Loads and resolves configuration from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes CONTEXT.md manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests.
- **watcher.py** — Monitors directory tree for file changes and triggers incremental manifest regeneration via debounced events.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and declarations from source code files.

## Notes

- The module follows a bottom-up tree-walking pattern for efficient manifest generation and incremental updates.
- Configuration is resolved through a layered approach: environment variables, .ctxconfig files, and CLI flags.
- LLM integration is abstraction-based, supporting multiple providers (Anthropic, OpenAI) with pluggable implementations.