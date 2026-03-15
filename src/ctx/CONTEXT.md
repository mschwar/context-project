---
generated: '2026-03-15T07:36:04Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:7c9da8e964dd55794fe3a0472639d55bb35a5d5c85944d47bdaea93d14afc20c
files: 14
dirs: 1
tokens_total: 13227
---
# C:/Users/Matty/Documents/context-project/src/ctx

Core module implementing a filesystem-native context layer for AI agents, providing CLI tools and LLM integration to generate and maintain CONTEXT.md manifests.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **__init__.py** — Package initialization defining ctx version 0.8.0 as a filesystem-native context layer for AI agents.
- **__main__.py** — Entry point for running ctx as a Python module via `python -m ctx`.
- **cli.py** — Click CLI with commands for generating, updating, and managing CONTEXT.md manifests across directory trees.
- **config.py** — Configuration loading from environment variables, .ctxconfig files, and CLI overrides with provider detection.
- **generator.py** — Core generation engine orchestrating bottom-up directory walks, file reading, LLM calls, and manifest writing.
- **git.py** — Utility for retrieving changed files from a git repository since last commit or staged changes.
- **hasher.py** — Content hashing for staleness detection using SHA-256 with directory hash based on sorted child hashes.
- **ignore.py** — Ignore-pattern matching using .ctxignore files in gitignore style via the pathspec library.
- **language_detector.py** — Language detection for files and directories based on file extensions and project configuration files.
- **llm.py** — LLM client protocol with Anthropic and OpenAI implementations for file and directory summarization.
- **manifest.py** — CONTEXT.md file format parsing and writing with YAML frontmatter and markdown body sections.
- **server.py** — FastAPI server providing MCP endpoints for retrieving CONTEXT.md manifests from a project directory.
- **watcher.py** — File watcher for ctx watch command that monitors directory trees and triggers incremental manifest regeneration.

## Subdirectories

- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes

- The module follows a bottom-up generation pattern where file-level summaries are created first, then aggregated into directory manifests.
- Configuration and LLM provider selection are centralized in config.py and llm.py, supporting multiple AI backends.
- Staleness detection via hasher.py enables incremental updates without regenerating unchanged content.