---
generated: '2026-03-15T05:51:35Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:d7531ce6321ca7f9413a10f232dc085e648718b5f601f3c286dc4e20128ce7db
files: 18
dirs: 7
tokens_total: 14824
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context layer tool (ctx) that enables AI agents to navigate and understand codebases through hierarchical CONTEXT.md manifests.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx with agentic SDLC principles and test-driven development.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **PHASE16_HANDOFF.md** — Phase 16 execution contract defining gates, tasks, and acceptance criteria for current development.
- **README.md** — Quick-start guide and command reference for the ctx filesystem-native context layer tool.
- **RUNBOOK.md** — Operational procedures for running, validating, developing, and releasing ctx.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, and component responsibilities.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Node.js package metadata and development dependencies for the ctx project.
- **pyproject.toml** — Python project configuration specifying dependencies, entry points, and build system.
- **rules.md** — Engineering standards and agentic rules for code quality, testing, and manifest protocol compliance.
- **state.md** — Current development status, completed milestones, and roadmap phases for ctx.

## Subdirectories

- **.claude/** — Configuration directory for the context project containing local settings and permitted operations.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Archive of design documents, analyses, and reflections for the ctx project.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer for AI agents.
- **tests/** — Comprehensive test suite covering CLI, parsers, configuration, Git integration, LLM clients, and core generation engine functionality.

## Notes

- The project uses both Node.js (commitlint, Husky) and Python (pyproject.toml) tooling for development and validation.
- Phase-based execution contracts (PHASE16_HANDOFF.md, GATE_CLOSEOUT.md) indicate structured agentic development workflow.
- Pre-commit hooks and manifest freshness checks enforce protocol compliance across the codebase.