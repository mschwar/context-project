---
generated: '2026-03-15T04:39:05Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:e148050b5728a33083358b78d60b5d9fa79bd46c5b0a42e99e079e16f99ececb
files: 14
dirs: 1
tokens_total: 12764
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module providing filesystem-native context generation for AI agents through LLM-powered directory manifests and incremental updates.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md filesystem manifests.
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

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The module follows a layered architecture: configuration and detection (config, language_detector, ignore) feed into core generation (generator, llm, manifest), with utilities for git integration, hashing, and file watching supporting incremental workflows.
- LLM implementations are pluggable via the protocol in llm.py, allowing multiple provider backends.
- Manifests are stored as CONTEXT.md files with frontmatter metadata for tracking staleness and configuration.