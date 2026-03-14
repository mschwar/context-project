---
generated: '2026-03-14T21:47:54Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:b48dddbebbf84d5a67b66aa7e03d85ed76312f251b0c472801aa46d0416217ef
files: 13
dirs: 1
tokens_total: 12587
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module for generating and managing CONTEXT.md directory manifests with LLM-powered summaries and git-aware change tracking.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization file declaring ctx version and module docstring.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI with commands for init, update, status, smart_update, and serve operations on directory trees.
- **config.py** — Configuration loading from environment variables, .ctxconfig files, and CLI flags with provider defaults.
- **generator.py** — Core generation engine that walks directory trees bottom-up to produce CONTEXT.md manifest files with LLM-generated summaries.
- **git.py** — Utility to retrieve changed files from a git repository since last commit or staged.
- **hasher.py** — Content hashing using SHA-256 for directory staleness detection and change tracking.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Programming language detection from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management with YAML metadata.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests from directories.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract exported symbols and definitions from source files across multiple programming languages.

## Notes

- The generator.py module orchestrates the manifest creation pipeline using components from config, ignore, hasher, language_detector, and llm modules.
- Git integration (git.py) enables smart_update to track only changed files since the last commit.
- LLM implementations (llm.py) support multiple providers for flexible summarization backends.