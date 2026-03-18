---
generated: '2026-03-18T18:37:16Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:83949ffc2a3277040940353546da56aa0aacc36babce9907f0a58ecfdc5f9682
files: 17
dirs: 1
tokens_total: 17471
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer for AI agents that generates and maintains CONTEXT.md manifests through LLM-powered directory documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **api.py** — Unified API layer providing canonical refresh, check, export, and reset operations with strategy selection and budget guardrails.
- **cli.py** — Click CLI entry point exposing ctx commands (init, update, status, check, watch, setup, export, reset) with progress tracking and structured output.
- **config.py** — Configuration loading from environment variables and .ctxconfig YAML files with provider detection, connectivity probing, and cost estimation.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing with progress tracking.
- **git.py** — Git utility functions for detecting repository state and retrieving lists of changed files since last commit.
- **hasher.py** — Computes SHA-256 hashes of files and directories for staleness detection with symlink loop handling.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory documentation.
- **lock.py** — Cross-platform file-based PID lock mechanism for coordinating concurrent ctx write operations.
- **manifest.py** — CONTEXT.md file parser and writer handling YAML frontmatter and markdown body serialization.
- **output.py** — Structured output broker for JSON envelope generation with error classification and metadata tracking across CLI commands.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File watcher for ctx watch command that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The architecture separates concerns into CLI (cli.py), unified API (api.py), core generation (generator.py), and LLM integration (llm.py).
- Configuration and environment detection (config.py) feeds into cost estimation and provider selection for LLM operations.
- File staleness is tracked via hashing (hasher.py) and git state (git.py) to enable incremental updates.
- Ignore patterns (ignore.py) and language detection (language_detector.py) inform which files are processed and how they are summarized.
- Concurrency is managed through file-based locking (lock.py) to prevent manifest corruption during parallel operations.
- The server (server.py) exposes manifests over HTTP with path traversal protections for integration with external tools.