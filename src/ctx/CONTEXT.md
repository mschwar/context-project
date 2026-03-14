---
generated: '2026-03-14T22:01:41Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:e3c6e4e70bf452ebc73c11de12c45a4891ca4ea37070beeeb6ced14c8122587e
files: 14
dirs: 1
tokens_total: 13775
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing context generation, LLM integration, and manifest management for automated documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization file declaring ctx version and module docstring.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI with commands for init, update, status, smart_update, watch, and serve operations.
- **config.py** — Configuration loading from environment variables, .ctxconfig files, and CLI overrides.
- **generator.py** — Core generation engine orchestrating directory walks, file reading, LLM calls, and manifest writing.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Programming language detection from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests.
- **watcher.py** — File system watcher triggering incremental manifest regeneration on source file changes.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract exported symbols and definitions from source files across multiple programming languages.

## Notes

- The generator module serves as the orchestration hub, coordinating config, ignore patterns, hashing, LLM calls, and manifest output.
- LLM integration supports multiple providers (Anthropic, OpenAI) through a protocol-based architecture.
- The CLI provides both one-time operations (init, update, status) and continuous modes (watch, serve).