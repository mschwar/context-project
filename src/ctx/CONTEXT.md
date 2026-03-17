---
generated: '2026-03-17T07:49:48Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:d961aaed1aead4b858a3ab031664e9065905b9da0a533ed1a4432e913a70c904
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

- The generator orchestrates a bottom-up walk that depends on hasher for staleness detection, ignore for filtering, language_detector for classification, and llm for content generation.
- Configuration flows from config.py through cli.py to generator.py, with provider selection (Anthropic/OpenAI) determined at startup.
- Git integration via git.py enables incremental updates by tracking changed files since the last commit.
- The manifest.py module handles serialization of generated documentation into CONTEXT.md files with structured frontmatter.
- Server.py provides HTTP access to manifests with path traversal protections, complementing the CLI-driven generation workflow.