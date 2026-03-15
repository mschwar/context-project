---
generated: '2026-03-15T06:40:14Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:51db63c04a52d19df8d7c5099988dcf445d50a657a50b17f1021c00721e78b65
files: 14
dirs: 1
tokens_total: 12974
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools, LLM integration, and manifest generation for directory documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md manifests across directory trees.
- **config.py** — Loads and resolves configuration from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server exposing MCP endpoints to read and serve CONTEXT.md manifests from a configured root directory.
- **watcher.py** — Monitors directory tree for file changes and triggers incremental manifest regeneration via debounced events.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The module integrates LLM providers (Anthropic, OpenAI) for intelligent summarization and supports incremental updates via git and file hashing.
- Configuration is resolved hierarchically from environment, config files, and CLI flags; ignore patterns follow gitignore conventions.
- The FastAPI server and watcher enable real-time manifest serving and automatic regeneration on file changes.