---
generated: '2026-03-15T07:08:57Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:e01e522aeadb2db9b455b42e6bfdc35e9d24d951bacbc0f31f0beee2b0eaa74e
files: 14
dirs: 1
tokens_total: 12859
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and services to generate, manage, and serve CONTEXT.md manifests.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md manifests across directory trees.
- **config.py** — Loads and resolves configuration from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — Monitors directory tree for file changes and triggers incremental manifest regeneration via debounced events.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The module integrates LLM-based summarization with git-aware change detection and file hashing for efficient incremental updates.
- Configuration is resolved hierarchically from environment, config files, and CLI flags, with automatic LLM provider detection.
- The watcher and server components enable real-time manifest updates and HTTP-based manifest serving with security validation.