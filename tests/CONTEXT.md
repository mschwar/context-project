---
generated: '2026-03-18T21:48:59Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:8464888a5572ef572082cded2f3061c13a052c718a2af99a776369999935e0e3
files: 36
dirs: 1
tokens_total: 37192
---
# C:/Users/Matty/Documents/context-project/tests

Comprehensive test suite covering unit tests, integration tests, and compatibility checks for the ctx context-generation system across CLI, API, parsers, LLM providers, and agent workflows.

## Files
- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures for isolated filesystem tests and temporary directory management.
- **test_agent_handoff.py** — Unit tests for agent handoff workflow validating ctx export and ctx serve as context sources for agent navigation.
- **test_api.py** — Unit tests for the unified API module covering refresh strategies, guardrails, and error handling.
- **test_cli.py** — Unit tests for CLI command wiring, output formatting, and integration with the generation engine.
- **test_cli_compat.py** — Compatibility tests ensuring legacy command surfaces remain functional and match canonical commands.
- **test_config.py** — Unit tests for configuration loading from files, environment variables, and CLI arguments with precedence rules.
- **test_csharp_parser.py** — Tests C# parser extraction of public classes, interfaces, enums, structs, records, methods, and properties.
- **test_docs.py** — Documentation and package metadata checks validating AGENTS.md contract, README brevity, and roadmap state.
- **test_elixir_parser.py** — Tests for Elixir file parser extracting modules, functions, structs, type annotations, specs, and callbacks.
- **test_generator.py** — Unit tests for the core generation engine covering manifest creation, staleness detection, and validation.
- **test_git.py** — Unit tests for Git integration covering changed file detection, staged/unstaged deduplication, and unborn HEAD handling.
- **test_go_parser.py** — Tests for Go language parser extracting functions, types, constants, and variables.
- **test_hasher.py** — Unit tests for file and directory hashing functionality covering basic hashing, line ending normalization, ignore patterns, symlink loops, and staleness detection.
- **test_ignore.py** — Unit tests for ignore pattern loading and path matching functionality in the ctx module.
- **test_integration.py** — End-to-end integration tests verifying manifest generation workflow using a fake LLM client on sample project fixture.
- **test_java_parser.py** — Tests Java parser extraction of public classes, interfaces, enums, records, and methods with modifiers.
- **test_js_ts_parser.py** — Tests for JavaScript/TypeScript parser extracting exports and language constructs.
- **test_kotlin_parser.py** — Tests Kotlin parser extraction of functions, classes, interfaces, objects, and enums from source files.
- **test_language_detector.py** — Tests for language detection from file extensions and project markers.
- **test_llm.py** — Unit tests for LLM provider clients, prompt parsing, caching, and batch handling across Anthropic and OpenAI.
- **test_lock.py** — Unit tests for CtxLock covering acquisition, release, staleness detection, and concurrent lock scenarios.
- **test_main.py** — Tests for module invocation via python -m ctx command.
- **test_manifest.py** — Unit tests for CONTEXT.md manifest read/write operations covering roundtrip serialization, frontmatter parsing, and footer handling.
- **test_mcp_server.py** — Unit tests for the stdio MCP server covering initialization, tool calls, error handling, and path validation.
- **test_output.py** — Unit tests for OutputBroker covering JSON envelope generation, error handling, and metadata population.
- **test_php_parser.py** — Tests PHP parser extraction of public functions, classes, interfaces, traits, and enums from PHP files.
- **test_prompts.py** — Regression tests for prompt templates validating structure, placeholders, and injection-defence instructions.
- **test_python_parser.py** — Tests for Python language parser extracting classes and functions.
- **test_ruby_parser.py** — Tests Ruby parser extraction of methods, classes, and modules from source files.
- **test_rust_parser.py** — Tests for Rust language parser extracting public items and modules.
- **test_server.py** — Tests for the HTTP server and CLI serve command including manifest retrieval and MCP integration.
- **test_setup.py** — Tests for provider detection, config file generation, and setup command with graceful error handling.
- **test_swift_parser.py** — Tests Swift parser extraction of public functions, classes, structs, protocols, and enums from Swift files.
- **test_trust.py** — Tests for token estimation accuracy, cache eviction policy, and transient error messaging with retry exhaustion handling.
- **test_watcher.py** — Unit tests for file system watcher event filtering, debounce logic, and coverage summary reporting.

## Subdirectories
- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes
- Parser tests are organized by language (Python, Go, Rust, Java, C#, Kotlin, PHP, Ruby, Swift, Elixir, JavaScript/TypeScript) and validate extraction of public symbols and type information.
- Integration tests use a fake LLM client and sample project fixtures to verify end-to-end manifest generation workflows.
- Compatibility tests ensure legacy command surfaces remain functional alongside canonical commands.
- Pytest fixtures in conftest.py provide isolated filesystem and temporary directory management for deterministic test execution.

<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
