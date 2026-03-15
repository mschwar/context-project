---
generated: '2026-03-15T05:51:15Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:3d9feb79799cb3e4d8f04bf8130b562a937af7bde62b4b2e9d01341994d1c76e
files: 14
dirs: 1
tokens_total: 12786
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents using LLM-powered file summarization.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md filesystem manifests.
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

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The generator module orchestrates the full pipeline: configuration loading, file traversal, LLM summarization, and manifest writing.
- LLM implementations are pluggable via the protocol in llm.py; config.py handles provider selection and credential resolution.
- Ignore patterns follow gitignore conventions and are evaluated during directory traversal to exclude files from processing.
- The watcher module enables continuous synchronization of manifests as the codebase evolves.