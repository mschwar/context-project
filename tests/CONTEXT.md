---
generated: '2026-10-31T23:52:01Z'
generator: ctx/1.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:c1b6fad430c532715d45680ecf1e4017cab8f748e8241034d4c3b02d46823180
files: 43
dirs: 1
tokens_total: 96535
---
# tests

Tests for various components of the project, including CLI, API, language parsers, and configuration handling.

## Files
- **__init__.py** — [empty file]
- **conftest.py** — Isolates process environment for tests, managing temporary directories and proxy settings.
- **test_agent_handoff.py** — Tests for agent context export and serve functionalities including depth, structure, and staleness filtering.
- **test_api.py** — Tests for unified API module covering various refresh strategies and behaviors.
- **test_cli.py** — Unit tests for ctx.cli module covering various command behaviors and output scenarios.
- **test_cli_compat.py** — Compatibility tests for legacy CLI command surfaces ensuring correct behavior.
- **test_config.py** — Tests configuration loading and resolution across environment variables, CLI, and ctxconfig files.
- **test_csharp_parser.py** — Tests parsing C# classes, interfaces, enums, structs, records, methods, and properties.
- **test_docs.py** — Tests documentation and package metadata against expected patterns and content.
- **test_dogfood_hardening.py** — Regression tests for Phase 30.8 AI-Server Live Dogfood Hardening Gate (Issue #73).
- **test_elixir_parser.py** — Tests for ctx.lang_parsers.elixir_parser including function extraction, module identification, and annotation parsing.
- **test_generator.py** — Tests for ctx.generator — core generation engine.
- **test_git.py** — Tests for git utility functions including handling of staged, unstaged, and untracked changes.
- **test_go_parser.py** — Tests for exporting functions, types, constants, and variables from Go files.
- **test_hasher.py** — Tests for ctx.hasher – file and directory content hashing.
- **test_ignore.py** — Tests for ctx.ignore – merged ignore patterns and path matching.
- **test_init.py** — Tests for ctx.init covering project initialization, uninitialization, and hook runtime.
- **test_integration.py** — End-to-end integration tests for the CLI using a fake client and sample project.
- **test_java_parser.py** — Tests for parsing Java files including classes, interfaces, enums, records, methods, and annotations.
- **test_js_ts_parser.py** — Tests for parsing JavaScript and TypeScript files, including exported functions, classes, interfaces, types, and default exports.
- **test_kotlin_parser.py** — Tests for Kotlin parser covering functions, classes, interfaces, objects, and enums.
- **test_language_detector.py** — Tests for language detection based on file extensions and project files.
- **test_llm.py** — Tests for ctx.llm – provider clients and prompt parsing.
- **test_lock.py** — Tests for ctx.lock CtxLock including basic acquire/release, double acquire, file content verification, and stale lock handling.
- **test_main.py** — Tests module execution via python -m ctx for version reporting.
- **test_manifest.py** — Tests for ctx.manifest — CONTEXT.md read/write/parse functionality.
- **test_mcp_server.py** — Tests for the stdio MCP server including tool calls and resource operations.
- **test_output.py** — Tests for ctx.output OutputBroker covering various output modes and error handling scenarios.
- **test_php_parser.py** — Tests for PHP parser functions and class extraction.
- **test_preflight.py** — Unit tests for PreflightCheck, PreflightResult, and run_preflight covering various check outcomes and scenarios.
- **test_prompts.py** — Tests existence, structure, and content of prompt templates ensuring they contain necessary placeholders and instructions.
- **test_python_parser.py** — Tests for parsing Python files extracting classes and functions.
- **test_qa_hardening.py** — Regression tests for foreign-model QA hardening across concurrency, worktrees, pricing, and skeleton extraction.
- **test_ruby_parser.py** — Tests for RubyParser functionality including methods, classes, and modules extraction.
- **test_rust_parser.py** — Tests for parsing Rust public functions, structs, enums, traits, and modules.
- **test_sdk.py** — Tests for ctx.sdk — zero-dependency reader for .ctx/ exports and metadata.
- **test_server.py** — Tests for the server module including CLI commands and HTTP endpoints.
- **test_setup.py** — Tests for ctx setup command and config helpers including provider detection and default config writing.
- **test_skeleton.py** — Unit tests for ctx.skeleton including extraction, rendering, and structural integrity checks.
- **test_stats_board.py** — Tests for ctx.stats_board — persistent run-stats ledger.
- **test_swift_parser.py** — Tests parsing Swift functions, classes, structs, protocols, and enums.
- **test_trust.py** — Tests for accurate token estimation, cache eviction, and transient error handling in the LLM client.
- **test_watcher.py** — Tests for ctx.watcher focusing on event filtering and debounce logic.

## Subdirectories
- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes
- Cross-module relationships: Tests interact with multiple modules such as `ctx.cli`, `ctx.generator`, `ctx.lang_parsers`, and `ctx.manifest`.
- Conventions: Tests are organized by functionality, covering areas like CLI commands, API behaviors, and language-specific parsing.

<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
