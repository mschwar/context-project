---
generated: '2026-03-16T15:27:42Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:3000303cdb886ff822a12f548ffbc152d5d18abd4b9e3d51d9e84909c0fce89e
files: 18
dirs: 7
tokens_total: 15253
---
# C:/Users/Matty/Documents/context-project

A filesystem-native hierarchical manifest system that generates persistent CONTEXT.md files to help AI agents navigate large codebases.

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
- **state.md** — Current development status documenting completed milestones through Phase 9 with health metrics, ecosystem features, and implementation details.

## Subdirectories

- **.claude/** — Configuration directory for the context project containing local settings and permitted operations.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Archive of design documents, analyses, and roadmaps for the ctx project.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, configuration, Git integration, LLM clients, and core generation engine functionality.

## Notes

- The project uses both Node.js (package.json, Husky) and Python (pyproject.toml) tooling.
- Git hooks and pre-commit validation ensure manifest freshness and conventional commit compliance.
- Phase-based delivery structure with detailed closeout and handoff documentation for agent coordination.