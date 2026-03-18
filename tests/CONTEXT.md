---
generated: '2026-03-18T18:17:42Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:e81eb6f5d0576bfcf5b73f1c5749b4acb7ba7e23c70bede8c534a14af5f13177
files: 34
dirs: 1
tokens_total: 33538
---
# C:/Users/Matty/Documents/context-project/tests

Comprehensive test suite covering unit, integration, and end-to-end testing for the context project's CLI, API, parsers, and core generation workflows.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures for isolated filesystem tests and temporary directory management.
- **test_agent_handoff.py** — Unit tests for agent handoff workflow validating ctx export and ctx serve as context sources for agent navigation.
- **test_api.py** — Unit tests for the unified API module covering refresh strategies, guardrails, and provider detection.
- **test_cli.py** — Integration tests for CLI commands verifying dependency wiring, output formatting, and end-to-end workflows.
- **test_cli_compat.py** — Compatibility tests ensuring legacy command surfaces remain functional and match canonical commands.
- **test_config.py** — Unit tests for configuration loading from files, environment variables, and CLI arguments with precedence rules.
- **test_csharp_parser.py** — Tests C# parser extraction of public classes, interfaces, enums, structs, records, methods, and properties.
- **test_elixir_parser.py** — Tests for Elixir file parser extracting modules, functions, structs, type annotations, specs, and callbacks.
- **test_generator.py** — Unit tests for the generation engine covering manifest creation, tree traversal, staleness detection, and token budget enforcement.
- **test_git.py** — Unit tests for Git integration covering changed file detection, staged/unstaged deduplication, and unborn HEAD handling.
- **test_go_parser.py** — Tests for Go language parser extracting functions, types, constants, and variables.
- **test_hasher.py** — Tests for file and directory content hashing with ignore pattern support.
- **test_ignore.py** — Tests for ignore pattern loading, merging, and path matching against default and user-defined ignore files.
- **test_integration.py** — End-to-end integration tests verifying manifest generation workflow using a fake LLM client on sample project fixture.
- **test_java_parser.py** — Tests Java parser extraction of public classes, interfaces, enums, records, and methods with modifiers.
- **test_js_ts_parser.py** — Tests for JavaScript/TypeScript parser extracting exports and language constructs.
- **test_kotlin_parser.py** — Tests Kotlin parser extraction of functions, classes, interfaces, objects, and enums from source files.
- **test_language_detector.py** — Tests for language detection from file extensions and project markers.
- **test_llm.py** — Tests for LLM client creation and file/directory summarization with retries.
- **test_lock.py** — Unit tests for CtxLock covering acquisition, release, staleness detection, and concurrent lock scenarios.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Tests for CONTEXT.md manifest file reading, writing, and parsing.
- **test_output.py** — Unit tests for OutputBroker covering JSON envelope generation, error handling, and metadata population.
- **test_php_parser.py** — Tests PHP parser extraction of public functions, classes, interfaces, traits, and enums from PHP files.
- **test_prompts.py** — Regression tests verifying prompt templates exist, contain required placeholders, and include injection-defence language.
- **test_python_parser.py** — Tests for Python language parser extracting classes and functions.
- **test_ruby_parser.py** — Tests Ruby parser extraction of methods, classes, and modules from source files.
- **test_rust_parser.py** — Tests for Rust language parser extracting public items and modules.
- **test_server.py** — Tests for MCP server functionality including serve command invocation and manifest context retrieval via HTTP endpoints.
- **test_setup.py** — Tests for provider detection, config file generation, and setup command with graceful error handling.
- **test_swift_parser.py** — Tests Swift parser extraction of public functions, classes, structs, protocols, and enums from Swift files.
- **test_trust.py** — Tests for token estimation accuracy, cache eviction policy, and transient error messaging with retry exhaustion handling.
- **test_watcher.py** — Unit tests for file system watcher event filtering, debounce logic, and coverage summary reporting.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Test organization mirrors core module structure: parsers (language-specific), CLI/API, generation engine, and infrastructure (Git, hashing, locking).
- Parser tests follow a consistent pattern across 10+ languages, validating extraction of language-specific constructs.
- Integration tests use conftest fixtures for isolated filesystem environments and fake LLM clients to avoid external dependencies.
- Compatibility tests ensure backward compatibility with legacy CLI surfaces alongside canonical commands.