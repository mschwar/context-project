---
generated: '2026-03-15T07:36:05Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:21e9874d9873a4ae06e75bc804efc47dd5c8ca0a966ecf21022c00af2f213b27
files: 29
dirs: 1
tokens_total: 25029
---
# C:/Users/Matty/Documents/context-project/tests

Test suite for the context project covering CLI commands, configuration, language parsers, manifest generation, and integrations.

## Files

- **__init__.py** — Package initialization file for tests directory.
- **conftest.py** — Pytest fixtures for isolated environment and temporary directory management.
- **test_cli.py** — CLI command tests covering init, update, status, version, diff, export, stats, clean, and verify operations.
- **test_config.py** — Configuration loading tests for file, environment, and CLI argument resolution.
- **test_csharp_parser.py** — C# language parser tests extracting classes, interfaces, methods, and properties.
- **test_elixir_parser.py** — Elixir language parser tests extracting modules, functions, structs, types, specs, and callbacks.
- **test_generator.py** — Core generation engine tests for manifest creation, updates, status checking, and token budgeting.
- **test_git.py** — Git integration tests for detecting changed files in staged and unstaged states.
- **test_go_parser.py** — Go language parser tests extracting exported functions, types, constants, and variables.
- **test_hasher.py** — File and directory hashing tests for content integrity and staleness detection.
- **test_ignore.py** — Ignore pattern loading and matching tests for .ctxignore and .ctxignore.default files.
- **test_integration.py** — End-to-end CLI integration test creating manifests on sample project fixture.
- **test_java_parser.py** — Java language parser tests extracting classes, interfaces, methods, and nested types.
- **test_js_ts_parser.py** — JavaScript/TypeScript parser tests extracting functions, classes, interfaces, types, and exports.
- **test_kotlin_parser.py** — Kotlin language parser tests extracting functions, classes, interfaces, objects, and enums.
- **test_language_detector.py** — Language detection tests identifying programming languages by file extension and project markers.
- **test_llm.py** — LLM client tests for Anthropic, OpenAI, caching, retries, and prompt template handling.
- **test_main.py** — Module invocation test verifying ctx runs correctly via python -m.
- **test_manifest.py** — Manifest read/write tests for CONTEXT.md frontmatter and body preservation.
- **test_php_parser.py** — PHP language parser tests extracting functions, classes, interfaces, traits, and enums.
- **test_prompts.py** — Prompt template tests verifying structure, placeholders, and injection defense.
- **test_python_parser.py** — Python language parser tests extracting classes and functions from source code.
- **test_ruby_parser.py** — Ruby language parser tests extracting methods, classes, and modules.
- **test_rust_parser.py** — Rust language parser tests extracting public functions, structs, enums, traits, and modules.
- **test_server.py** — MCP server tests for context endpoint and CLI serve command integration.
- **test_setup.py** — Setup command tests for provider detection, config writing, and API key validation.
- **test_swift_parser.py** — Swift language parser tests extracting functions, classes, structs, protocols, and enums.
- **test_trust.py** — Token estimation, cache eviction, and transient error messaging tests.
- **test_watcher.py** — File system watcher tests for event filtering, debouncing, and coverage reporting.

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- Tests are organized by functional area: parsers for each supported language, core features (CLI, config, generation), and integrations (Git, LLM, server).
- Pytest fixtures in conftest.py provide isolated test environments and temporary directories.
- Language parser tests follow a consistent pattern across multiple supported languages.