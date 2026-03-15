---
generated: '2026-03-15T04:13:31Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:6f7f8f93070b650aede9e5cbd0c4edfb80cf07af3bac410d036ccd604577b98b
files: 14
dirs: 1
tokens_total: 12763
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and LLM-powered directory summarization with manifest generation and incremental updates.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md manifests.
- **config.py** — Loads and resolves configuration from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests.
- **watcher.py** — Monitors directory tree for file changes and triggers incremental manifest regeneration via debounced events.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural definitions from source files across multiple programming languages.

## Notes

- The module follows a layered architecture: configuration and CLI at the top, generation and manifest management in the middle, and language detection and LLM integration at the foundation.
- Incremental updates are supported through git integration, content hashing, and file watching for efficient re-generation.
- Multiple LLM providers are supported via a protocol-based abstraction in llm.py.