---
generated: '2026-03-15T04:13:46Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:6630b518b5d932799ec17dc0cf8d6a8797dc03bfc8e7d77465adc3a24f79c86e
files: 17
dirs: 9
tokens_total: 12142
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests for project directories to help AI agents navigate codebases efficiently.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **README.md** — Tool that generates CONTEXT.md manifests for project directories to help AI agents navigate codebases efficiently.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, testing, release publishing, cache management, and common failure modes for ctx development.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration specifying dependencies, entry points, and metadata for the ctx-tool PyPI distribution.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Development status tracker documenting completed milestones, current health, and active roadmap phases for the ctx project.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archive of design documents, analyses, and reflections for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code directory containing the main implementation of the context project.
- **tests/** — Test suite for the context-project, covering CLI operations, language parsers, configuration, Git integration, LLM clients, and manifest generation.

## Notes

- This project implements an agentic SDLC workflow with mandatory phase closeout procedures and agent contribution guidelines.
- Configuration spans Python (pyproject.toml), Node.js (package.json), and Git hooks (Husky, pre-commit) for integrated tooling.
- The archive directory preserves design history and rationale for the manifest system architecture.
