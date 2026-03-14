---
generated: '2026-03-14T22:02:04Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a104bd3ffeed315732d53725c599192c5d9f50dd90ed3fd3cd5c636fef311336
files: 16
dirs: 9
tokens_total: 9797
---
# C:/Users/Matty/Documents/context-project

A filesystem-native hierarchical manifest system that generates CONTEXT.md files to help AI agents navigate and understand codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to the ctx project.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Entry point documentation describing ctx's purpose, installation, and usage for generating CONTEXT.md manifests.
- **RUNBOOK.md** — Operational guide for running tests, using the CLI, and handling common failure modes.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration defining ctx as a CLI tool with dependencies and optional dev extras.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Current development status documenting completed phases, health metrics, and upcoming milestones.

## Subdirectories

- **.claude/** — Configuration directory for the context project's Claude integration settings and permissions.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration directory containing workflow automation and action definitions for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archived design documents and analysis for ctx, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code directory containing the main implementation modules for the context project.
- **tests/** — Test suite for the context-project, covering CLI, configuration, code parsing, Git integration, LLM clients, and manifest generation.

## Notes

- The project uses both Python (pyproject.toml) and Node.js (package.json) tooling for development and automation.
- Git hooks are configured via both Husky and a custom .githooks directory for commit validation and testing.
- Documentation includes operational guides (RUNBOOK.md), engineering standards (rules.md), and agent workflows (AGENTS.md).