---
generated: '2026-03-14T21:53:02Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ca05042cda3b62faf3784f7ca44f9a470cc741311d2a6917646f87420d4290e0
files: 14
dirs: 1
tokens_total: 13737
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module providing CLI tools, manifest generation, and LLM-powered directory documentation for CONTEXT.md files.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization file declaring ctx version and module docstring.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and check status of CONTEXT.md manifests.
- **config.py** — Configuration loading from environment variables, .ctxconfig files, and CLI flags with provider defaults.
- **generator.py** — Core generation engine that walks directory trees bottom-up to produce CONTEXT.md manifest files with LLM-generated summaries.
- **git.py** — Utility to retrieve changed files from a git repository since last commit or staged.
- **hasher.py** — Content hashing using SHA-256 for directory staleness detection and change tracking.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Programming language detection from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management with YAML metadata.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests from directories.
- **watcher.py** — File watcher that monitors directory changes and triggers incremental manifest regeneration with debouncing.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract exported symbols and definitions from source files across multiple programming languages.

## Notes

- The generator module orchestrates the full pipeline: configuration, file discovery, LLM summarization, and manifest serialization.
- LLM implementations are pluggable via the protocol in llm.py; config.py determines which provider is active.
- Ignore patterns and git integration enable incremental updates and selective processing of changed files.