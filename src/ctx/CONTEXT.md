---
generated: '2026-03-14T21:12:33Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:0e4e531d4d9b01ca345ac48c3d9a5ad90e1922886947cf2b1e85fb09e7b5577a
files: 13
dirs: 1
tokens_total: 12587
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module providing CLI tools and generation engine for creating and maintaining CONTEXT.md directory documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization file declaring ctx version and module docstring.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI with commands for init, update, status, smart_update, and serve operations on directory trees.
- **config.py** — Configuration loading from environment variables, .ctxconfig files, and CLI flags with provider defaults.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing.
- **git.py** — Utility to retrieve changed files from a git repository since last commit or staged.
- **hasher.py** — Content hashing using SHA-256 for directory staleness detection and change tracking.
- **ignore.py** — Ignore-pattern matching using .ctxignore files with gitignore-style glob patterns.
- **language_detector.py** — Programming language detection from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file parsing, serialization, and frontmatter management with YAML metadata.
- **server.py** — FastAPI server exposing MCP endpoints for retrieving CONTEXT.md manifests from directories.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract structural information from source code files across multiple programming languages.

## Notes

- The generator.py module is the orchestration hub that coordinates file reading, LLM summarization, and manifest output.
- Configuration flows from environment variables and .ctxconfig files through config.py to CLI commands.
- LLM implementations in llm.py support multiple providers (Anthropic, OpenAI) for flexible summarization backends.