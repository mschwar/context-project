---
generated: '2026-03-18T03:41:54Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:bc257730c0e88e3bc107a3834423f380234bb2328b08d2c1c11ca8da5e4cf064
files: 32
dirs: 1
tokens_total: 29759
---
# C:/Users/Matty/Documents/context-project/tests

Comprehensive test suite covering CLI commands, language parsers, core generation logic, Git integration, and end-to-end workflows for the context project.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures providing isolated environment and workspace-local temporary directories for tests.
- **test_agent_handoff.py** — Unit tests for agent handoff workflow validating ctx export and ctx serve as context sources for agent navigation.
- **test_cli.py** — Unit tests for CLI commands covering dependency wiring, output formatting, and integration with core generation and status functions.
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments.
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
- **test_setup.py** — Tests for setup command, provider detection, and config file generation with various LLM providers.
- **test_swift_parser.py** — Tests Swift parser extraction of public functions, classes, structs, protocols, and enums from Swift files.
- **test_trust.py** — Tests for token estimation accuracy, cache eviction policy, and transient error messaging with retry exhaustion handling.
- **test_watcher.py** — Unit tests for file system watcher event filtering, debounce logic, and coverage summary reporting.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Test organization mirrors core module structure with one test file per major feature (parsers, CLI, generation, Git, LLM integration).
- Language parser tests follow a consistent pattern validating extraction of public symbols and language-specific constructs.
- conftest.py provides shared fixtures for isolated test environments; integration tests use sample projects from fixtures/.
- Tests cover both happy-path functionality and edge cases (concurrent locks, transient errors, token budget enforcement, unborn HEAD).