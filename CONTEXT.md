---
generated: '2026-03-14T22:48:33Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:de79b3bcd9365559037cf1d8375fd88b509a4a1bab46cb1927545ad2f68a6339
files: 17
dirs: 9
tokens_total: 10848
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests for codebases, enabling AI agents to navigate and understand project structure through hierarchical filesystem documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining ctx mission, rules, phases, and agent responsibilities.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Quick-start guide and command reference for ctx, a tool that generates CONTEXT.md manifests for codebases.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, validation, LLM caching, common failure modes, and development tasks.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration specifying ctx-tool dependencies, entry points, version, and PyPI metadata.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Development status and completed milestones tracking ctx progress through ten phases from foundation to reliability.

## Subdirectories

- **.claude/** — Local configuration and settings directory for the context project.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archived design documents and analysis for the ctx project, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code for the context project, containing core modules and utilities for AI agent context management.
- **tests/** — Test suite for the context project covering CLI, configuration, generation engine, language parsers, Git integration, and LLM client functionality.

## Notes

- The project uses Python (pyproject.toml) with Node.js tooling (package.json) for Git hooks and commit linting.
- Documentation emphasizes agentic workflows, manifest protocols, and hierarchical codebase navigation.
- Pre-commit hooks and Husky enforce manifest freshness and conventional commits.