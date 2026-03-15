---
generated: '2026-03-15T03:50:27Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:58c2d52b0ab368c92c8bb59a7be02448f17b8118bf918b10380a824e07c530c1
files: 14
dirs: 1
tokens_total: 12736
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and LLM-powered manifest generation for directory documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md manifests.
- **config.py** — Loads and resolves configuration from environment variables, .ctxconfig files, and CLI flags with provider detection.
- **generator.py** — Core generation engine that walks directory trees bottom-up to produce CONTEXT.md manifest files with LLM-generated summaries.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests.
- **watcher.py** — Monitors directory tree for file changes and triggers incremental manifest regeneration via debounced events.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and definitions from source code files across multiple programming languages.

## Notes

- The module follows a layered architecture: configuration and detection (config, language_detector, git) feed into core generation (generator, hasher, ignore), which uses LLM clients (llm) to produce manifests (manifest) exposed via CLI (cli) or server (server).
- Watcher and incremental updates enable real-time manifest synchronization during development.