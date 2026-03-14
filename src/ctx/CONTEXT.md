---
generated: '2026-03-14T05:54:49Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a81f1c208e0eb80825804722fdcaed792e65bd6e0ad386a6eb670e1b2de522d5
files: 13
dirs: 1
tokens_total: 12327
---
# C:/Users/Matty/Documents/context-project/src/ctx

Filesystem-native context layer for AI agents that generates and manages CONTEXT.md manifests.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx covering version control, Python, Node.js, IDE, temporary files, OS junk, and environment secrets.
- **__init__.py** — Package initialization file declaring ctx as a filesystem-native context layer for AI agents with version 0.1.0.
- **__main__.py** — Module entry point that invokes the Click CLI when ctx is run as a Python module.
- **cli.py** — Click CLI implementation with commands for init, update, status, and smart_update to generate and manage CONTEXT.md manifests.
- **config.py** — Configuration loader that resolves settings from .ctxconfig files, environment variables, and CLI flags with provider-specific defaults.
- **generator.py** — Core generation engine that walks directory trees bottom-up, reads files, detects binary content, calls LLM for summaries, and writes CONTEXT.md manifests.
- **git.py** — Git utility function to retrieve a list of changed files in a repository since the last commit or staged changes.
- **hasher.py** — Content hashing module using SHA-256 to compute stable directory hashes for staleness detection of manifests.
- **ignore.py** — Ignore pattern loader using pathspec for gitignore-style matching of files and directories to exclude from processing.
- **language_detector.py** — Language detector that identifies programming languages from file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for summarizing files and generating directory markdown bodies.
- **manifest.py** — CONTEXT.md file parser and writer handling YAML frontmatter with metadata and markdown body content.
- **server.py** — FastAPI server exposing an MCP endpoint to retrieve CONTEXT.md manifests for specified directory paths.

## Subdirectories

- **lang_parsers/** — Language-specific parsers for extracting code structure and definitions from source files.

## Notes

- None