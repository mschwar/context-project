---
generated: '2026-03-14T05:58:09Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:68c096e1fd97edee14b11f90addbee7eaa50827f82e37500adff24bfd49a3da4
files: 13
dirs: 1
tokens_total: 12327
---
# C:/Users/Matty/Documents/context-project/src/ctx

Filesystem-native context layer for AI agents with CLI tools and LLM integration for generating directory manifests.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, covering version control, Python/Node.js environments, IDE files, temporary files, OS junk, and secrets.
- **__init__.py** — Package initialization file declaring ctx as a filesystem-native context layer for AI agents with version 0.1.0.
- **__main__.py** — Module entry point that invokes the Click CLI when ctx is run as a Python module.
- **cli.py** — Click CLI implementation with commands for init, update, status, smart_update, and serve operations on directory manifests.
- **config.py** — Configuration loader that merges .ctxconfig files, environment variables, and CLI flags with provider-specific defaults.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, detects binary content, calls LLM for summaries, and writes CONTEXT.md manifests.
- **git.py** — Git utility module that retrieves list of changed files from a repository since the last commit.
- **hasher.py** — Content hashing module using SHA-256 to compute stable directory hashes for staleness detection.
- **ignore.py** — Ignore-pattern matching using .ctxignore files in gitignore style with pathspec library.
- **language_detector.py** — Language detector that identifies programming languages from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory markdown.
- **manifest.py** — CONTEXT.md file format parser and writer with YAML frontmatter containing metadata and markdown body.
- **server.py** — FastAPI server exposing MCP endpoints to retrieve CONTEXT.md manifests for specified directory paths.

## Subdirectories

- **lang_parsers/** — Language-specific parsers for extracting code structure and definitions from source files.

## Notes

- None