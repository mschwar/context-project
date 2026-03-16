---
generated: '2026-03-16T20:57:04Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:c8cba382c7a16d02795df9f118dfb6843c13387c1fd4b3b3c73e7ea67905f1c1
files: 18
dirs: 7
tokens_total: 15253
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context layer tool that generates persistent CONTEXT.md manifests to help AI agents navigate large codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, required behavior, and delegation levels for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx with agentic SDLC principles and test-driven development.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **PHASE16_HANDOFF.md** — Execution contract for Phase 16 work split into small gates for narrower models with recommended order and detailed task specifications.
- **README.md** — Project documentation describing ctx tool for generating persistent CONTEXT.md manifests to help AI agents navigate large codebases.
- **RUNBOOK.md** — Operational guide for running, validating, developing ctx including CLI usage, test execution, release publishing, and common failure modes.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, and component responsibilities.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Node.js package metadata and development dependencies for the ctx project.
- **pyproject.toml** — Python project configuration specifying dependencies, entry points, and build system.
- **rules.md** — Engineering standards and agentic rules for code quality, testing, and manifest protocol compliance.
- **state.md** — Documents current development status, completed milestones, and phases 1-9 of the ctx project through March 2026.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project environment.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Archive of design documents, analyses, and reflections for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer for AI agents.
- **tests/** — Comprehensive test suite covering CLI, configuration, language parsers, generation engine, Git integration, and manifest functionality.

## Notes

- The project uses both Node.js (package.json, Husky) and Python (pyproject.toml) tooling.
- Git hooks and pre-commit validation ensure manifest freshness and conventional commit compliance.
- AGENTS.md and CONTRIBUTING.md define the agentic workflow and contribution standards.
- GATE_CLOSEOUT.md and PHASE16_HANDOFF.md document structured phase execution and handoff protocols.