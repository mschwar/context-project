---
generated: '2026-03-14T22:58:32Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:7d41665205726b97d214a35cf9334d9e51b79079445be91ca3fea00b6ba67d47
files: 14
dirs: 1
tokens_total: 12674
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and check CONTEXT.md manifests.
- **config.py** — Configuration loading and resolution from environment variables, .ctxconfig files, and CLI overrides.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes manifests.
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

- The generator.py module orchestrates the manifest creation workflow by combining configuration, file discovery, hashing, LLM calls, and manifest serialization.
- LLM integration is abstracted through llm.py to support multiple providers; config.py determines which is active.
- Ignore patterns and git integration enable incremental updates and selective processing of changed files.