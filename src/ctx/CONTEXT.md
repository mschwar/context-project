---
generated: '2026-03-18T08:19:37Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:3a6d7e63166af8beda22235c979827fe31bdaab7c387816f9a9b804c4cf57f62
files: 17
dirs: 1
tokens_total: 17461
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents through LLM-powered directory documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **api.py** — Unified API layer providing canonical commands for refresh, check, export, and reset operations.
- **cli.py** — Click CLI entry point exposing ctx commands with progress tracking, cost estimation, and structured output.
- **config.py** — Configuration loading from environment variables and .ctxconfig files with provider detection and validation.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing with progress tracking.
- **git.py** — Git utility functions for detecting repository state and retrieving lists of changed files since last commit.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **lock.py** — Cross-platform file-based PID lock mechanism for coordinating concurrent ctx write operations.
- **manifest.py** — CONTEXT.md file parser and writer handling YAML frontmatter and markdown body serialization.
- **output.py** — Structured output broker for JSON envelope generation and exception classification in CLI commands.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File watcher for ctx watch command that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The generator orchestrates the full pipeline: file traversal, language detection, LLM summarization, and manifest persistence.
- LLM abstraction (llm.py) supports multiple providers; config.py handles provider selection and validation.
- Concurrency is managed via lock.py to prevent manifest corruption during simultaneous writes.
- Staleness detection uses content hashing; git.py enables incremental updates based on changed files.
- CLI (cli.py) and API (api.py) layers provide both user-facing and programmatic interfaces to core operations.