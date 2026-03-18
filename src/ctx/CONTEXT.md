---
generated: '2026-03-18T18:17:30Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:2a70292476cff6871f50bdb6108390ac8a0c95601bed6afb24d6906c59692bb4
files: 17
dirs: 1
tokens_total: 17387
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer for AI agents that generates and maintains CONTEXT.md manifests through LLM-powered directory summarization.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **api.py** — Unified API layer providing canonical refresh, check, export, and reset operations with strategy selection and budget guardrails.
- **cli.py** — Click CLI entry point exposing ctx commands (init, update, status, check, watch, setup, export, reset) with progress tracking and structured output.
- **config.py** — Configuration loading from environment variables and .ctxconfig YAML files with provider detection, connectivity probing, and cost estimation.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing with progress tracking.
- **git.py** — Git utility functions for detecting repository state and retrieving lists of changed files since last commit.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **lock.py** — Cross-platform file-based PID lock mechanism for coordinating concurrent ctx write operations.
- **manifest.py** — CONTEXT.md file parser and writer handling YAML frontmatter and markdown body serialization.
- **output.py** — Structured output broker for JSON envelope generation with error classification and metadata tracking across CLI commands.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File watcher for ctx watch command that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The architecture follows a layered pattern: CLI (cli.py) → API (api.py) → Generator (generator.py) → LLM (llm.py), with supporting utilities for file I/O, hashing, and locking.
- Configuration and provider detection (config.py) enables multi-LLM support with cost estimation and connectivity checks.
- Manifest persistence uses YAML frontmatter for metadata and markdown body for documentation, parsed and written by manifest.py.
- Concurrency is managed through file-based PID locks (lock.py) to prevent simultaneous writes.
- Language detection and parsing (language_detector.py, lang_parsers/) support extraction of structural information for improved summarization.