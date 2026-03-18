---
generated: '2026-03-18T18:58:03Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:c4e568fdf9bc1cdee7892a3514558a06082873bd21069418db55047781e62889
files: 17
dirs: 1
tokens_total: 17510
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents through LLM-powered directory documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **api.py** — Unified API layer providing canonical commands (refresh, check, export, reset) with strategy selection and token guardrails.
- **cli.py** — Click CLI entry point exposing ctx commands (init, update, status, check, watch, setup, export, reset) with progress tracking and structured output.
- **config.py** — Configuration loading from environment variables and .ctxconfig YAML files with provider detection, connectivity probing, and cost estimation.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing with progress tracking.
- **git.py** — Git utility functions for detecting repository state and retrieving lists of changed files since last commit.
- **hasher.py** — Computes SHA-256 hashes of files and directories for staleness detection with symlink loop handling.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **lock.py** — Cross-platform file-based PID lock mechanism for coordinating concurrent ctx write operations.
- **manifest.py** — CONTEXT.md file parser and writer handling YAML frontmatter and markdown body serialization.
- **output.py** — Structured output broker that captures command results and emits JSON envelopes with status, metadata, and error classification.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File watcher for ctx watch command that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The architecture follows a layered pattern: CLI (cli.py) → API (api.py) → Generator (generator.py) → LLM (llm.py), with supporting utilities for hashing, ignoring, and locking.
- Configuration is centralized in config.py and probes for LLM provider availability at startup.
- Manifest persistence uses YAML frontmatter for metadata and markdown body for documentation, parsed/written by manifest.py.
- Concurrency is managed via file-based locks (lock.py) to prevent simultaneous writes to CONTEXT.md files.
- Language detection and parsing are extensible through lang_parsers subdirectory, enabling language-specific API extraction.