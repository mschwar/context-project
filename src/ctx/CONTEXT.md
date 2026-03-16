---
generated: '2026-03-16T22:02:27Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a9b6fa41c18c9eb5bd78fdbf1336082f7fdf8e53d4d1c59db826c9fa21a38091
files: 14
dirs: 1
tokens_total: 13299
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents using LLM-powered file summarization.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md files across directory trees.
- **config.py** — Configuration loading and resolution from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLMs for summaries, and writes CONTEXT.md manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File system watcher that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The generator module orchestrates the core workflow: directory traversal, file reading, LLM summarization, and manifest writing.
- Configuration is resolved hierarchically from environment, config files, and CLI flags, with automatic LLM provider detection.
- Ignore patterns follow gitignore conventions and are applied during traversal to exclude irrelevant files.
- Staleness detection via content hashing enables incremental regeneration triggered by the watcher or git-based change detection.
- The server module exposes manifests over HTTP with path traversal protections for safe remote access.