---
generated: '2026-03-14T06:46:29Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:aeb0afa680e7b47abcc98effcc84ca0022c4a0482d783d9ae2bd9680fbac15e7
files: 13
dirs: 1
tokens_total: 12483
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module for generating and managing CONTEXT.md documentation manifests with LLM-powered summaries.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization file declaring ctx version and module docstring.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI with commands to generate, update, and check status of CONTEXT.md manifests.
- **config.py** — Configuration loading from environment variables, .ctxconfig files, and CLI flags with provider defaults.
- **generator.py** — Core generation engine that walks directory trees bottom-up to produce CONTEXT.md files with LLM summaries.
- **git.py** — Utility to retrieve changed files from git repository since last commit or staged changes.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with recursive directory hash computation.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns via pathspec.
- **language_detector.py** — Programming language detection from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file format parsing and writing with YAML frontmatter and markdown body.
- **server.py** — FastAPI server exposing MCP endpoint to retrieve CONTEXT.md manifests for specified directories.

## Subdirectories

- **lang_parsers/** — Language-specific parsers for extracting code structure and definitions from source files.

## Notes

- The generator orchestrates the full pipeline: configuration, ignore patterns, language detection, LLM summarization, and manifest writing.
- Multiple LLM providers (Anthropic, OpenAI) are supported via a pluggable protocol in llm.py.
- Staleness detection and incremental updates rely on content hashing and git change tracking.