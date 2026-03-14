---
generated: '2026-03-14T21:53:07Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:5cb8944d5baee43237db4116566b16591ceee5581dac918eb2acf9ba001737a4
files: 19
dirs: 1
tokens_total: 16092
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
- **test_watcher.py** — Tests for file watcher event filtering and debounce logic in the ctx module.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Each test module corresponds to a major component of the context project (parsers, CLI, generation, integration).
- The `conftest.py` provides shared pytest fixtures for temporary directory management across tests.
- Integration tests in `test_integration.py` validate end-to-end workflows using fixture projects.