---
generated: '2026-10-31T22:05:23Z'
generator: ctx/1.1.0
model: qwen2.5:7b-instruct
content_hash: sha256:67374580aa981ab297add9d484fda2970c70ba78122ec91aa39a90cdfbc7ffe5
files: 23
dirs: 1
tokens_total: 10411
---
# src/ctx

Unified API and CLI entry point for managing and validating `CONTEXT.md` files across project directories.

## Files
- **.ctxignore.default** — Default ignore patterns for ctx projects.
- **__init__.py** — Version number for the ctx package.
- **__main__.py** — Entry point for the CLI application.
- **api.py** — Unified API layer for ctx canonical commands including error handling, result classes, and utility functions.
- **cli.py** — It looks like the provided code snippet is a part of a Python script, likely for a command-line tool, possibly related to managing and validating `CONTEXT.md` files in a directory structure. The script appears to handle various modes of operation, such as health checks, manifest verification, and smart updates. Here's a breakdown of the key components: 1. **Modes of Operation**: - **Health Check**: Checks for stale or missing manifests. - **Manifest Verification**: Verifies the integrity of manifests. - **Smart Update**: Incrementally refreshes stale `CONTEXT.md` files based on git-changed files. 2. **Error Handling and Reporting**: - Errors are added to a broker, which can be used to report issues. - Summary statistics are printed, and the script exits with a non-zero status if errors are found. 3. **Output Customization**: - The script supports JSON mode for output. - It can be configured to run in quiet mode, where it only exits with a non-zero status if issues are found. 4. **Configuration and Input**: - The script can be configured with various options, such as provider, model, token budget, and cache path. - It can operate on a specified path and process git-changed files. 5. **Stale and Missing Manifests**: - The script checks for stale and missing manifests and reports them. - It can also verify the integrity of manifests and report any invalid entries. 6. **Smart Update Logic**: - The `smart_update` function processes git-changed files and checks for stale `CONTEXT.md` files. - It can run in dry-run mode, which lists affected directories without regenerating them. ### Example Usage Here's an example of how you might use this script: ```bash # Health check mode python script.py --mode health --path /path/to/directory # Manifest verification mode python script.py --mode verify --path /path/to/directory # Smart update mode python script.py --mode smart-update --path /path/to/directory ``` ### Key Functions - **`_display_status_path`**: Formats the status and path for display. - **`_exit_for_broker`**: Exits the script based on the broker's data. - **`_json_mode`**: Determines if the output should be in JSON format. - **`_echo_legacy_warning`**: Prints a warning message for legacy commands. ### Potential Improvements 1. **Error Handling**: Ensure that all potential errors are handled gracefully. 2. **Logging**: Add logging to help with debugging and tracking. 3. **Configuration Management**: Consider using a more robust configuration management system. 4. **Performance Optimization**: Optimize the performance of the `smart_update` function, especially for large directories. If you have any specific questions or need further assistance with this script, feel free to ask!
- **config.py** — Configuration loading and resolution with environment variable and .ctxconfig file support.
- **generator.py** — Core generation engine walking a directory tree to produce CONTEXT.md files.
- **git.py** — Retrieves changed files in a Git repository, handling unborn heads and untracked files.
- **hasher.py** — Computes and compares SHA-256 hashes for files and directories to detect staleness.
- **ignore.py** — Matches paths against .ctxignore files using pathspec for glob matching.
- **init.py** — Bootstraps .ctx/ infrastructure, installs hooks, and manages project initialization and uninitialization.
- **language_detector.py** — Detects the primary programming language of a file or directory based on extensions and configuration files.
- **llm.py** — LLM client interface with Anthropic and OpenAI implementations, providing file and directory summarization.
- **lock.py** — Manages cross-platform PID locks for ctx write operations with heartbeat functionality.
- **manifest.py** — Reads and parses CONTEXT.md manifest, extracting metadata and body content.
- **mcp_server.py** — name
- **output.py** — Structured output broker for ctx CLI commands managing JSON envelope creation and error handling.
- **preflight.py** — Preflight checks for model quality and connectivity, returning a result with status and details.
- **sdk.py** — Provides typed access to .ctx/ metadata and pre-compiled exports without importing LLM clients.
- **server.py** — Serves CONTEXT.md files from project directories via HTTP API.
- **skeleton.py** — Determines structural skeletons and architectural boundaries without LLM calls.
- **stats_board.py** — Prunes and manages run history for context project audit remediation, respecting retention policies and cache directories.
- **watcher.py** — Monitors directory changes and triggers manifest regeneration with debounced handling.

## Subdirectories
- **lang_parsers/** — Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Notes
- Cross-module dependencies include language-specific parsers in the `lang_parsers` subdirectory for extracting structural elements from source files.
- Key components handle health checks, manifest verification, and smart updates, with robust error handling and output customization.

<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
