---
generated: '2026-03-14T21:47:58Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:15ffaa2ba7f669a1a35b817aa814e6aca8147a24b8fbc61421f5d20e7a50d1de
files: 18
dirs: 1
tokens_total: 15144
---
# C:/Users/Matty/Documents/context-project/tests

Test suite for the context project, covering CLI, configuration, generation engine, language parsers, Git integration, and LLM providers.

## Files

- **__init__.py** — Package marker for tests directory.
- **conftest.py** — Pytest fixture providing workspace-local temporary directory for tests.
- **test_cli.py** — Tests for CLI command wiring, dependency injection, and output formatting.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_generator.py** — Tests for core generation engine including tree creation, updates, and status checking.
- **test_git.py** — Tests for Git integration to detect changed files in repositories.
- **test_go_parser.py** — Tests Go parser extraction of exported functions, types, constants, and variables from Go source files.
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

- Tests are organized by module, with each test file corresponding to a core component (parsers, generators, CLI, etc.).
- The `conftest.py` provides shared pytest fixtures for temporary workspace isolation.
- Integration tests in `test_integration.py` validate end-to-end workflows using fixture projects.