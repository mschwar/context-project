---
generated: '2026-03-18T03:41:43Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ec5a35817e14f58244a188a042b5ebe066313309723ed8b71d8f28402e258514
files: 16
dirs: 1
tokens_total: 15524
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md documentation for AI agents through LLM-powered directory analysis.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md files across directory trees.
- **config.py** — Configuration loading and resolution from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing with progress tracking.
- **git.py** — Git utility functions for detecting repository state and retrieving lists of changed files since last commit.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **lock.py** — Cross-platform file-based PID lock mechanism for coordinating concurrent ctx write operations.
- **manifest.py** — CONTEXT.md file parser and writer handling YAML frontmatter and markdown body serialization.
- **output.py** — Structured JSON output broker for CLI commands with error classification and envelope formatting.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File watcher for ctx watch command that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The generator orchestrates a bottom-up walk through directory trees, delegating file summarization to pluggable LLM providers (Anthropic/OpenAI) and language detection to support multi-language projects.
- Staleness detection via content hashing and git integration enables incremental updates, reducing redundant LLM calls.
- Concurrent write safety is enforced through cross-platform file-based locking in lock.py.
- The manifest module handles serialization of both YAML metadata and markdown documentation into CONTEXT.md files.
- Language-specific parsing in lang_parsers supports extraction of structural information beyond simple file summaries.