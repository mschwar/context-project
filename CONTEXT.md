---
generated: '2026-03-14T22:13:08Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:41ba27121e2596ac05c6ea9f8e6cd6f7029d52d8698873425a790daa579aeda8
files: 16
dirs: 9
tokens_total: 10138
---
# C:/Users/Matty/Documents/context-project

A filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Entry point documentation describing ctx's purpose, installation, and usage for generating CONTEXT.md manifests.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, validation, LLM caching, common failure modes, and development tasks.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration defining ctx as a CLI tool with dependencies and optional dev extras.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Development status tracker documenting completed phases, current health, and upcoming milestones for the ctx project.

## Subdirectories

- **.claude/** — Configuration directory for the context project's Claude integration settings and permissions.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration directory containing workflow automation and action definitions for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archived design documents and analysis for the ctx project, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code directory containing the main implementation modules for the context project.
- **tests/** — Test suite for the context-project, covering CLI, configuration, code parsing, Git integration, LLM clients, and manifest generation.

## Notes

- The project uses Python (pyproject.toml) with Node.js tooling (package.json) for Git hooks and commit linting.
- Core documentation includes AGENTS.md and rules.md for agentic workflow governance, and RUNBOOK.md for operational guidance.
- The =4.0 file appears to be a malformed or corrupted entry and may require investigation.