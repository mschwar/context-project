---
generated: '2026-03-15T07:05:00Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ca14a65f7454b986f007cc8562e908dc6134f1819ffbc56e4e84f06143534c41
files: 29
dirs: 1
tokens_total: 23936
---
# C:/Users/Matty/Documents/context-project/tests

Test suite covering CLI commands, configuration, language parsers, core generation engine, Git integration, hashing, ignore patterns, LLM client, manifest handling, and server endpoints.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures that isolate ambient env state and provide workspace-local temporary directories for tests.
- **test_cli.py** — Tests for CLI command wiring, dependency injection, and output formatting across init, update, status, version, and utility commands.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
- **test_csharp_parser.py** — Tests C# parser extraction of public classes, interfaces, enums, structs, records, methods, and properties.
- **test_elixir_parser.py** — Tests for Elixir file parser extracting modules, functions, structs, type annotations, specs, and callbacks.
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
- **test_php_parser.py** — Tests PHP parser extraction of public functions, classes, interfaces, traits, and enums from PHP files.
- **test_prompts.py** — Regression tests verifying prompt templates exist, contain required placeholders, and include injection-defence language.
- **test_python_parser.py** — Tests for Python language parser extracting classes and functions.
- **test_ruby_parser.py** — Tests Ruby parser extraction of methods, classes, and modules from source files.
- **test_rust_parser.py** — Tests for Rust language parser extracting public items and modules.
- **test_server.py** — Tests for MCP server endpoints serving CONTEXT.md manifests.
- **test_setup.py** — Tests for setup command, provider detection, and config file generation with various LLM providers.
- **test_swift_parser.py** — Tests Swift parser extraction of public functions, classes, structs, protocols, and enums from Swift files.
- **test_trust.py** — Tests for token estimation with tiktoken fallback, cache eviction with size limits, and transient error messaging.
- **test_watcher.py** — Tests for file system watcher event filtering and debounce logic.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by functional area: parsers for each language, core features (generator, config, git, hashing), CLI/server interfaces, and integration tests.
- Language parser tests follow a consistent pattern across multiple supported languages (Python, Go, Rust, Java, C#, JavaScript/TypeScript, PHP, Ruby, Kotlin, Swift, Elixir).
- Integration tests use the fixtures directory for end-to-end validation.
- The shared conftest now clears ambient proxy/provider env vars so local test runs stay machine-independent.
