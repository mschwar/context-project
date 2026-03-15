---
generated: '2026-03-15T07:37:56Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:2016ad06a116a5bee8ae84105f6272164439bc4f043ec001ea2f172b2df687b7
files: 18
dirs: 7
tokens_total: 15253
---
# C:/Users/Matty/Documents/context-project

A filesystem-native tool that generates persistent CONTEXT.md manifests to help AI agents navigate large codebases through hierarchical directory summaries.

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
- **archive/** — Archive of design documents, analyses, and roadmaps for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code for the context-project application, containing core modules and utilities.
- **tests/** — Test suite for the context project covering CLI commands, configuration, language parsers, manifest generation, and integrations.

## Notes

- The project uses both Node.js (commitlint, Husky) and Python (pyproject.toml) tooling for development and distribution.
- Git hooks and pre-commit validation ensure manifest freshness and conventional commit compliance.
- AGENTS.md, CONTRIBUTING.md, and rules.md define the agentic workflow and quality standards for contributors.
- Phase-based execution contracts (GATE_CLOSEOUT.md, PHASE16_HANDOFF.md) structure ongoing development work.