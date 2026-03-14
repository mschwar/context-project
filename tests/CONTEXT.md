---
generated: '2026-03-14T23:34:06Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:8cb2c2897eba074264352ca668ffdba78bc70318d58ed45a6f9fb00a084015b3
files: 24
dirs: 1
tokens_total: 20537
---
# C:/Users/Matty/Documents/context-project/tests

Test suite for the context-project, covering CLI, parsers, configuration, Git integration, LLM clients, and manifest generation.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures providing workspace-local temporary directories for tests.
- **test_cli.py** — Tests for CLI command wiring, dependency injection, and output formatting.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_csharp_parser.py** — Tests C# parser extraction of public classes, interfaces, enums, structs, records, and methods.
- **test_generator.py** — Tests for core generation engine including tree creation, updates, and status checking.
- **test_git.py** — Tests for Git integration to detect changed files in repositories.
- **test_go_parser.py** — Tests for Go language parser extracting functions, types, constants, and variables.
- **test_hasher.py** — Tests for file and directory content hashing with ignore pattern support.
- **test_ignore.py** — Tests for ignore pattern loading and merging with path matching logic.
- **test_integration.py** — End-to-end CLI tests on sample fixture project with fake LLM client.
- **test_java_parser.py** — Unit tests for Java parser validating extraction of public classes, interfaces, enums, records, methods, and modifiers.
- **test_js_ts_parser.py** — Tests for JavaScript/TypeScript parser extracting exports and language constructs.
- **test_language_detector.py** — Tests for language detection from file extensions and project markers.
- **test_llm.py** — Tests for LLM client creation and file/directory summarization with retries.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Tests for CONTEXT.md manifest file reading, writing, and parsing.
- **test_prompts.py** — Regression tests verifying prompt templates exist, contain required placeholders, and include injection-defence language.
- **test_python_parser.py** — Tests for Python language parser extracting classes and functions.
- **test_rust_parser.py** — Tests for Rust language parser extracting public items and modules.
- **test_server.py** — Tests for MCP server endpoints serving CONTEXT.md manifests.
- **test_setup.py** — Tests for setup command, provider detection, and config file generation with various LLM providers.
- **test_trust.py** — Tests for token estimation with tiktoken fallback, cache eviction with size limits, and transient error messaging.
- **test_watcher.py** — Tests for file system watcher event filtering and debounce logic.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by module and feature area, with language-specific parser tests grouped together.
- Integration tests use fixture projects and fake LLM clients to validate end-to-end workflows.
- Conftest.py provides shared pytest fixtures for temporary directory management across all tests.