---
generated: '2026-03-17T07:34:09Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:6c29e109c613047eff6ff68c5dc4e418d38714aab3a4ceac9df4fbfcaf0cb9de
files: 14
dirs: 1
tokens_total: 13443
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md documentation for AI agents through LLM-powered directory analysis.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands for generating, updating, and managing CONTEXT.md files across directory trees.
- **config.py** — Configuration loading and resolution from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing with progress tracking.
- **git.py** — Git utility functions for detecting repository state and retrieving lists of changed files since last commit.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File watcher for ctx watch command that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The generator orchestrates a pipeline combining git state detection, ignore-pattern filtering, language detection, LLM summarization, and manifest serialization.
- Configuration cascades from environment variables through .ctxconfig files to CLI flags, with automatic LLM provider detection.
- Staleness detection via content hashing enables incremental updates; the watcher supports continuous monitoring for development workflows.
- The server module provides HTTP access to manifests with path traversal protection, enabling integration with external tools.