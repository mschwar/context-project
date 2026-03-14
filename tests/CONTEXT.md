---
generated: '2026-03-14T21:12:56Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a90920ded7b9c88bb63ff96e177f3ee563a2a4cc9894b8d88971b3bf20b56433
files: 17
dirs: 1
tokens_total: 14545
---
# C:/Users/Matty/Documents/context-project/tests

Test suite for the context project, covering CLI, configuration, generation engine, language parsers, LLM integration, and manifest handling.

## Files

- **__init__.py** — Package marker for tests directory.
- **conftest.py** — Pytest fixture providing workspace-local temporary directory for tests.
- **test_cli.py** — Tests for CLI command wiring, dependency injection, and output formatting.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_generator.py** — Tests for core generation engine including tree creation, updates, and status checking.
- **test_git.py** — Tests for Git integration to detect changed files in repositories.
- **test_hasher.py** — Tests for file and directory content hashing with ignore pattern support.
- **test_ignore.py** — Tests for ignore pattern loading and path matching against gitignore-style rules.
- **test_integration.py** — End-to-end CLI tests on sample fixture project with fake LLM client.
- **test_js_ts_parser.py** — Tests for JavaScript/TypeScript parser extracting functions, classes, interfaces, and types.
- **test_language_detector.py** — Tests for language detection from file extensions and project configuration files.
- **test_llm.py** — Tests for LLM provider clients (Anthropic, OpenAI) and prompt parsing.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Tests for CONTEXT.md manifest file reading, writing, and frontmatter parsing.
- **test_python_parser.py** — Tests for Python parser extracting classes and functions from source code.
- **test_rust_parser.py** — Tests for Rust parser extracting public functions, structs, enums, traits, and modules.
- **test_server.py** — Tests for MCP server endpoints and CLI serve command integration.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by module, with each test file corresponding to a major component (CLI, config, generators, parsers, LLM, etc.).
- `conftest.py` provides shared pytest fixtures for temporary workspace isolation.
- `test_integration.py` provides end-to-end validation using fixture projects.