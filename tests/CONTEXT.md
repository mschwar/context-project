---
generated: '2026-03-16T20:56:57Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a141d6f1aec616cb504b47b23149177f6aa46c8a9a0442672993c515aaec22a3
files: 29
dirs: 1
tokens_total: 25093
---
# C:/Users/Matty/Documents/context-project/tests

Comprehensive test suite covering CLI, configuration, language parsers, generation engine, Git integration, and manifest functionality.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures providing isolated environment and workspace-local temporary directories for tests.
- **test_cli.py** — Tests for CLI command wiring, dependency injection, and output formatting across init, update, status, and utility commands.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_csharp_parser.py** — Tests C# parser extraction of public classes, interfaces, enums, structs, records, methods, and properties.
- **test_elixir_parser.py** — Tests for Elixir file parser extracting modules, functions, structs, type annotations, specs, and callbacks.
- **test_generator.py** — Tests for core generation engine including tree creation, updates, and status checking.
- **test_git.py** — Tests for Git integration to detect changed files in repositories.
- **test_go_parser.py** — Tests for Go language parser extracting functions, types, constants, and variables.
- **test_hasher.py** — Tests for file and directory content hashing with ignore pattern support.
- **test_ignore.py** — Tests for ignore pattern loading, merging, and path matching against default and user-defined ignore files.
- **test_integration.py** — End-to-end integration tests verifying manifest generation workflow using a fake LLM client on sample project fixture.
- **test_java_parser.py** — Tests Java parser extraction of public classes, interfaces, enums, records, and methods with modifiers.
- **test_js_ts_parser.py** — Tests for JavaScript/TypeScript parser extracting exports and language constructs.
- **test_kotlin_parser.py** — Tests Kotlin parser extraction of functions, classes, interfaces, objects, and enums from source files.
- **test_language_detector.py** — Tests for language detection from file extensions and project markers.
- **test_llm.py** — Tests for LLM client creation and file/directory summarization with retries.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Tests for CONTEXT.md manifest file reading, writing, and parsing.
- **test_php_parser.py** — Tests PHP parser extraction of public functions, classes, interfaces, traits, and enums from PHP files.
- **test_prompts.py** — Regression tests verifying prompt templates exist, contain required placeholders, and include injection-defence language.
- **test_python_parser.py** — Tests for Python language parser extracting classes and functions.
- **test_ruby_parser.py** — Tests Ruby parser extraction of methods, classes, and modules from source files.
- **test_rust_parser.py** — Tests for Rust language parser extracting public items and modules.
- **test_server.py** — Tests for MCP server functionality including serve command invocation and manifest context retrieval via HTTP endpoints.
- **test_setup.py** — Tests for setup command, provider detection, and config file generation with various LLM providers.
- **test_swift_parser.py** — Tests Swift parser extraction of public functions, classes, structs, protocols, and enums from Swift files.
- **test_trust.py** — Tests for token estimation accuracy, cache eviction policy, and transient error messaging with retry exhaustion handling.
- **test_watcher.py** — Tests for file system event filtering and debounce logic in the watcher module, including CONTEXT.md exclusion and rapid event coalescing.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by module and feature area, with language-specific parser tests grouped together.
- Integration tests rely on fixtures in the `fixtures/` subdirectory for realistic project scenarios.
- Pytest configuration and shared fixtures are defined in `conftest.py`.