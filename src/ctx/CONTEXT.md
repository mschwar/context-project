---
generated: '2026-03-16T15:26:10Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:74f769a84d876bb0a8b4481ff7e433eba09c65deb1d14415252d9c3bddff0052
files: 14
dirs: 1
tokens_total: 13198
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core implementation of ctx, a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **__init__.py** — Package initialization defining ctx as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI entry point providing commands to generate, update, and manage CONTEXT.md manifests.
- **config.py** — Configuration loading and resolution from environment variables, .ctxconfig files, and CLI overrides.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, calls LLM for summaries, and writes manifests.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staging.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash composition.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Detects programming language from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management.
- **server.py** — FastAPI server providing HTTP endpoints to read and serve CONTEXT.md manifests with security checks for path traversal.
- **watcher.py** — File system watcher that monitors directory changes and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The generator.py module orchestrates the manifest creation workflow by coordinating with config, ignore, hasher, language_detector, and llm modules.
- LLM implementations in llm.py are pluggable; configuration determines which provider is used.
- The manifest.py module handles both reading existing CONTEXT.md files and writing updated versions with preserved frontmatter.
- Security is enforced in server.py to prevent path traversal attacks when serving manifests over HTTP.