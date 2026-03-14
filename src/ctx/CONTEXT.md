---
generated: '2026-03-14T22:48:20Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:497b559cadfbd3b6d937e61cc20d1594333dcd032d0383f5fdc19d20d18f0fa5
files: 14
dirs: 1
tokens_total: 13838
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and services to generate and maintain CONTEXT.md manifests across directory trees.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and check CONTEXT.md manifests across directory trees.
- **config.py** — Configuration loading and resolution from environment variables, .ctxconfig files, and CLI overrides for LLM provider settings.
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

- The module integrates LLM-based summarization with git-aware change detection and file system watching for incremental updates.
- Configuration is resolved hierarchically from environment, config files, and CLI arguments.
- Manifest staleness is tracked via content hashing to optimize regeneration.