---
generated: '2026-03-15T06:52:46Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:fae0dd61866543c177c8178664eb8bdcc21e7b86c56c0bace5c5f6a549ef5262
files: 18
dirs: 7
tokens_total: 14983
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context layer tool (ctx) that generates persistent CONTEXT.md manifests to help AI agents navigate and understand large codebases.

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
- **archive/** — Archive of design documents, analyses, and reflections for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer for AI agents.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, configuration, Git integration, LLM clients, and manifest generation.

## Notes

- This project uses both Node.js (package.json) and Python (pyproject.toml) tooling, suggesting a polyglot development environment.
- Git hooks (Husky, pre-commit) enforce manifest freshness and conventional commits, indicating strong process discipline.
- The archive/ directory preserves design history and rationale for future reference and agent onboarding.