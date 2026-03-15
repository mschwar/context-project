---
generated: '2026-03-15T03:50:36Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:07515693793d8f21c2bd7c167feb68388b21e14172f165840acfa563ab3faea9
files: 28
dirs: 1
tokens_total: 22693
---
# C:/Users/Matty/Documents/context-project/tests

Comprehensive test suite covering CLI, configuration, language parsers, Git integration, LLM clients, and manifest generation for the context project.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures providing workspace-local temporary directories for tests.
- **test_cli.py** — Tests for CLI command wiring, dependency injection, and output formatting across init, update, status, version, and dry-run operations.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_csharp_parser.py** — Tests C# parser extraction of public classes, interfaces, enums, structs, records, methods, and properties.
- **test_generator.py** — Tests for core generation engine including tree creation, updates, and status checking.
- **test_git.py** — Tests for Git integration to detect changed files in repositories.
- **test_go_parser.py** — Tests for Go language parser extracting functions, types, constants, and variables.
- **test_hasher.py** — Tests for file and directory content hashing with ignore pattern support.
- **test_ignore.py** — Tests for ignore pattern loading and merging with path matching logic.
- **test_integration.py** — End-to-end CLI tests on sample fixture project with fake LLM client.
- **test_java_parser.py** — Tests Java parser extraction of public classes, interfaces, enums, records, and methods with modifiers.
- **test_js_ts_parser.py** — Tests for JavaScript/TypeScript parser extracting exports and language constructs.
- **test_kotlin_parser.py** — Tests Kotlin parser extraction of functions, classes, interfaces, objects, and enums from source files.
- **test_language_detector.py** — Tests for language detection from file extensions and project markers.
- **test_llm.py** — Tests for LLM client creation and file/directory summarization with retries.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Tests for CONTEXT.md manifest file reading, writing, and parsing.
- **test_php_parser.py** — Tests for PHP parser extracting public functions, classes, interfaces, traits, and enums from PHP source files.
- **test_prompts.py** — Regression tests verifying prompt templates exist, contain required placeholders, and include injection-defence language.
- **test_python_parser.py** — Tests for Python language parser extracting classes and functions.
- **test_ruby_parser.py** — Tests Ruby parser extraction of methods, classes, and modules from source files.
- **test_rust_parser.py** — Tests for Rust language parser extracting public items and modules.
- **test_server.py** — Tests for MCP server endpoints serving CONTEXT.md manifests.
- **test_setup.py** — Tests for setup command, provider detection, and config file generation with various LLM providers.
- **test_swift_parser.py** — Tests for Swift parser extracting functions, classes, structs, protocols, and enums from Swift source files.
- **test_trust.py** — Tests for token estimation with tiktoken fallback, cache eviction with size limits, and transient error messaging.
- **test_watcher.py** — Tests for file system watcher event filtering and debounce logic.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by functional area: parsers for each supported language, core features (CLI, config, generation), and integration tests.
- Fixtures directory provides sample projects and test data for end-to-end and integration testing.
- conftest.py provides shared pytest configuration and temporary directory fixtures for test isolation.