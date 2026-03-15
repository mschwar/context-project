---
generated: '2026-03-15T07:09:11Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:80b8a14e9d2fbe59e74d42091126979c4a0d478bbcfd7d86568417a8958874dc
files: 18
dirs: 7
tokens_total: 15066
---
# C:/Users/Matty/Documents/context-project

A filesystem-native hierarchical manifest system that generates persistent CONTEXT.md files to help AI agents navigate large codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx with agentic SDLC principles and test-driven development.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **PHASE16_HANDOFF.md** — Phase 16 execution contract defining gates, scope, tasks, and guardrails for narrower model compatibility.
- **README.md** — Project documentation describing ctx tool for generating persistent CONTEXT.md manifests to help AI agents navigate large codebases.
- **RUNBOOK.md** — Operational guide covering CLI usage, testing, validation, release publishing, and common failure modes for ctx development.
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
- **src/** — Source code for the context-project application, containing core modules and utilities.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, configuration, Git integration, LLM clients, and manifest generation.

## Notes

- The project uses both Node.js (package.json, Husky) and Python (pyproject.toml) tooling.
- Git hooks and pre-commit validation enforce manifest freshness and conventional commits.
- Phase-based execution contracts (PHASE16_HANDOFF.md, GATE_CLOSEOUT.md) structure development workflow.
- Archive directory preserves historical design decisions and project evolution.