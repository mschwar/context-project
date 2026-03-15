---
generated: '2026-03-15T03:43:55Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:e930ceae36179676ce4621937afd6bd99ca6eeb432066103196b4eb40a5a51fd
files: 17
dirs: 9
tokens_total: 12086
---
# C:/Users/Matty/Documents/context-project

CLI tool that generates CONTEXT.md manifests for project directories to help AI agents navigate codebases efficiently.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **README.md** — CLI tool that generates CONTEXT.md manifests for project directories to help AI agents navigate codebases efficiently.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, testing, release publishing, cache management, and common failure modes for ctx development.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration specifying dependencies, entry points, and metadata for the ctx-tool PyPI distribution.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Development status tracker documenting completed milestones, current health, and active roadmap phases for the ctx project.

## Subdirectories

- **.claude/** — Local configuration and settings directory for the context project.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Historical documentation and design analysis for the ctx tool, a filesystem-native manifest system enabling hierarchical directory navigation for AI agents.
- **src/** — Source code for the context project, containing core modules and utilities for AI agent context management.
- **tests/** — Test suite covering CLI commands, configuration, language parsers, Git integration, file hashing, manifest generation, LLM clients, and end-to-end workflows.

## Notes

- The project uses Python (pyproject.toml) and Node.js (package.json) tooling with pre-commit hooks and Husky for automation.
- AGENTS.md, CONTRIBUTING.md, GATE_CLOSEOUT.md, and rules.md define the agentic SDLC workflow and governance model.
- The =4.0 file appears to be a malformed or temporary artifact and may warrant investigation.