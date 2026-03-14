---
generated: '2026-03-14T23:23:37Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:9516a51d1b29c1ece70bf894a4e8ce39d84624aa9fe6a9c34f1126e5427d4170
files: 17
dirs: 9
tokens_total: 11854
---
# C:/Users/Matty/Documents/context-project

CLI tool that generates CONTEXT.md manifests for project directories to help AI agents navigate codebases efficiently.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Onboarding contract and workflow guide for agents contributing to ctx, covering mission, current state, canonical rules, and development phases.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — CLI tool that generates CONTEXT.md manifests for project directories to help AI agents navigate codebases efficiently.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, testing, release publishing, cache management, and common failure modes for ctx development.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration specifying dependencies, entry points, and metadata for the ctx-tool PyPI distribution.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Development status and completed milestones tracking ctx's progress through ten phases from foundation to reliability and automation.

## Subdirectories

- **.claude/** — Local configuration and settings directory for the context project.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata and diagnostic information.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archive of design documents, roadmaps, and AI analysis for the ctx project—a filesystem-native hierarchical manifest system enabling coarse-to-fine directory navigation.
- **src/** — Source code for the context project, containing core modules and utilities for AI agent context management.
- **tests/** — Test suite covering CLI, parsers, configuration, Git integration, LLM clients, and manifest generation for the context project.

## Notes

- The project uses Python (pyproject.toml) and Node.js (package.json) tooling with pre-commit hooks and Husky for automation.
- Core documentation includes AGENTS.md for agent onboarding, CONTRIBUTING.md for development guidelines, and RUNBOOK.md for operational procedures.
- Architecture and engineering standards are documented in architecture.md and rules.md respectively.