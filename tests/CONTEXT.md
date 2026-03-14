---
generated: '2026-03-14T06:46:36Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:becd4ea8a307932ba9474f4e15c581e01ee5cd2f46231a3152e53d640856fb43
files: 15
dirs: 1
tokens_total: 12750
---
# C:/Users/Matty/Documents/context-project/tests

Test suite for the context project covering CLI, configuration, generation engine, Git integration, hashing, ignore patterns, LLM providers, manifest parsing, and language detection.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixture providing workspace-local temporary directory for filesystem tests.
- **test_cli.py** — Tests for Click CLI command wiring, dependency injection, and output formatting.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_generator.py** — Tests for core generation engine including tree creation, updates, and status checking.
- **test_git.py** — Tests for Git integration to detect changed files in repositories.
- **test_hasher.py** — Tests for file and directory content hashing with ignore pattern support.
- **test_ignore.py** — Tests for ignore pattern loading and path matching against gitignore-style rules.
- **test_integration.py** — End-to-end CLI test on sample fixture project verifying manifest generation.
- **test_language_detector.py** — Tests for programming language detection from file extensions and project files.
- **test_llm.py** — Tests for LLM provider clients, prompt parsing, and caching behavior.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Tests for CONTEXT.md manifest file reading, writing, and frontmatter parsing.
- **test_python_parser.py** — Tests for Python source code parsing to extract classes and functions.
- **test_server.py** — Tests for MCP server endpoints and CLI serve command integration.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by module, with each test file corresponding to a core feature area.
- The conftest.py provides shared fixtures for filesystem isolation during testing.
- Integration tests validate end-to-end workflows using fixture projects.