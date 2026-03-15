---
generated: '2026-03-15T06:40:28Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:17d0b04374e9820eeed8d7c2f0f5cbadaa9a94d8be473bbea5613399af970d47
files: 18
dirs: 7
tokens_total: 14914
---
# C:/Users/Matty/Documents/context-project

A filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.

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
- **README.md** — Project overview, quick start guide, command reference, and configuration instructions for the ctx tool.
- **RUNBOOK.md** — Operational guide covering testing, CLI usage, release publishing, cache management, and development tasks.
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
- **src/** — Source code directory containing the main implementation of the context project.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, configuration, Git integration, LLM clients, and core generation engine functionality.

## Notes

- The project uses both Node.js (commitlint, Husky) and Python (pyproject.toml) tooling.
- Git hooks and pre-commit validation enforce manifest freshness and conventional commits.
- Phase-based execution contracts (PHASE16_HANDOFF.md, GATE_CLOSEOUT.md) indicate structured agentic workflow governance.