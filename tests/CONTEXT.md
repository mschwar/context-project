---
generated: '2026-10-30T15:04:21Z'
generator: ctx/1.1.0
model: qwen2.5:7b-instruct
content_hash: sha256:0cba51e902a11c8e4a339e01113b4a760fe4056e99e06f3d4011de083ce0f695
files: 42
dirs: 1
tokens_total: 49043
---
# /central/repos/active/context-project/tests

Tests for various components of the context-project, including CLI, API, language parsers, and server functionalities.

## Files
- **__init__.py** — Package initialization for the tests directory.
- **conftest.py** — Isolates process environment for tests, managing temporary directories and proxy settings.
- **test_agent_handoff.py** — Tests for agent context export and serve functionalities including depth, structure, and staleness filtering.
- **test_api.py** — Tests for unified API module covering various refresh strategies and behaviors.
- **test_cli.py** — Unit tests for ctx.cli module covering various CLI commands and their interactions.
- **test_cli_compat.py** — Compatibility tests for legacy command surfaces covering deprecation, help output, and dry run behavior.
- **test_config.py** — Tests for ctx.config handling different configuration sources and overrides.
- **test_csharp_parser.py** — Tests parsing C# classes, interfaces, enums, structs, records, methods, and properties.
- **test_docs.py** — Checks documentation and package metadata against expected patterns and contents.
- **test_dogfood_hardening.py** — Regression tests for Phase 30.8 AI-Server Live Dogfood Hardening Gate.
- **test_elixir_parser.py** — Tests for ctx.lang_parsers.elixir_parser including function extraction, module identification, and annotation parsing.
- **test_generator.py** — Tests for ctx.generator, verifying core generation engine functionality.
- **test_git.py** — Tests for git utility functions including handling of unstaged, staged, and unborn head scenarios.
- **test_go_parser.py** — Tests for exporting functions, types, constants, and variables from Go files.
- **test_hasher.py** — Tests for ctx.hasher – file and directory content hashing.
- **test_ignore.py** — Tests for ctx.ignore — merged ignore patterns and path matching.
- **test_init.py** — Tests for `ctx.init` covering Tier 1 and Tier 2 initialization, `.ctx/` exports, hook chaining, PID debounce, and `uninit_project`.
- **test_integration.py** — End-to-end test for CLI refresh functionality creating manifests.
- **test_java_parser.py** — Tests for parsing Java files including classes, interfaces, enums, records, methods, and annotations.
- **test_js_ts_parser.py** — Tests for parsing JavaScript and TypeScript files, including exported functions, classes, interfaces, types, and default exports.
- **test_kotlin_parser.py** — Tests for Kotlin parser covering functions, classes, interfaces, objects, and enums.
- **test_language_detector.py** — Tests for language detection based on file extensions and project files.
- **test_llm.py** — Tests for ctx.llm — provider clients and prompt parsing
- **test_lock.py** — Tests for ctx.lock CtxLock including basic acquire/release, concurrency, and stale lock handling.
- **test_main.py** — Tests module execution via python -m ctx for version reporting.
- **test_manifest.py** — Tests for ctx.manifest — CONTEXT.md read/write/parse functionality.
- **test_mcp_server.py** — Tests for the stdio MCP server including tool calls and resource operations.
- **test_output.py** — Tests for ctx.output OutputBroker covering various output modes and error handling scenarios.
- **test_php_parser.py** — Tests for PHP parser functions and class extraction.
- **test_preflight.py** — Contains unit tests for preflight checks and the run_preflight function.
- **test_prompts.py** — Tests existence, structure, and content of prompt templates ensuring they contain necessary placeholders and instructions.
- **test_python_parser.py** — Tests for parsing Python files extracting classes and functions.
- **test_ruby_parser.py** — Tests for RubyParser functionality including methods, classes, and modules extraction.
- **test_rust_parser.py** — Tests for parsing Rust public functions, structs, enums, traits, and modules.
- **test_sdk.py** — Tests for ctx.sdk — zero-dependency reader for .ctx/ exports and metadata.
- **test_server.py** — Tests for the server module including CLI commands and HTTP endpoints.
- **test_setup.py** — Tests for ctx setup command and config helpers including provider detection and default config writing.
- **test_skeleton.py** — Tests for ctx.skeleton module covering structural and boundary document hash calculations, and context rendering.
- **test_stats_board.py** — Tests for ctx.stats_board — persistent run-stats ledger functionality.
- **test_swift_parser.py** — Tests parsing Swift functions, classes, structs, protocols, and enums.
- **test_trust.py** — Tests for accurate token estimation, cache eviction, and transient error handling in the LLM client.
- **test_watcher.py** — Tests for ctx.watcher focusing on event filtering and debounce logic.

## Subdirectories
- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes
- Cross-module relationships: Tests interact with multiple modules such as `ctx.cli`, `ctx.config`, `ctx.generator`, and `ctx.manifest`.
- Conventions: Tests are organized by functionality, covering initialization, parsing, and server operations.

<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
