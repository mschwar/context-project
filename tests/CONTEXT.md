---
generated: '2026-03-14T05:54:58Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:bafcdbde15786b9ecfb7d576cff7d4358beea9508ea838fd62b75202088e7cf7
files: 15
dirs: 1
tokens_total: 12615
---
# C:/Users/Matty/Documents/context-project/tests

Test suite for the context-project application covering CLI, configuration, generation, and integration functionality.

## Files

- **__init__.py** — Empty Python package initialization file
- **conftest.py** — Pytest fixture providing workspace-local temporary directory for filesystem tests
- **test_cli.py** — Tests for Click CLI command wiring covering init, update, status, and version commands
- **test_config.py** — Tests for configuration loading from files, environment variables, and CLI arguments with provider and model resolution
- **test_generator.py** — Tests for core generation engine including tree creation, updates, status checking, and token budget enforcement
- **test_git.py** — Tests for Git integration to retrieve changed files using subprocess
- **test_hasher.py** — Tests for file and directory content hashing with SHA256, pattern ignoring, and symlink loop detection
- **test_ignore.py** — Tests for ignore pattern loading and merging default patterns with user-defined patterns
- **test_integration.py** — End-to-end CLI test creating manifests for sample project using fake LLM client
- **test_language_detector.py** — Tests for language detection from file extensions and project configuration files
- **test_llm.py** — Tests for LLM provider clients including Anthropic and OpenAI with retry logic and prompt parsing
- **test_main.py** — Test for Python module invocation via command line reporting version
- **test_manifest.py** — Tests for manifest file read/write with YAML frontmatter and markdown body preservation
- **test_python_parser.py** — Tests for Python AST parser extracting classes and functions from source files
- **test_server.py** — Tests for MCP server endpoints retrieving context manifests and CLI serve command integration

## Subdirectories

- **fixtures/** — Test fixture directory containing sample projects and data for testing context manifest generation.

## Notes

- None