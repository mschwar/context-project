---
generated: '2026-03-17T02:12:33Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:635ddfbd853090f201e37fbf9594f3e2e45746c8876340cd5e310368e8aab551
files: 18
dirs: 7
tokens_total: 15253
---
# C:/Users/Matty/Documents/context-project

A filesystem-native tool that generates and maintains persistent CONTEXT.md manifests to help AI agents navigate and understand large codebases through hierarchical directory summaries.

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
- **state.md** — Development status document tracking completed phases 1–9, current health metrics, and ecosystem features for the ctx tool.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project's Claude integration.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Design documents, AI analysis, and project reflections documenting the evolution and architectural decisions for the ctx tool.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agents.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, configuration, Git integration, LLM clients, and end-to-end manifest generation workflows.

## Notes

- The project uses a hybrid tech stack (Python for core logic, Node.js for tooling) with conventional commits and pre-commit hooks enforcing quality standards.
- Agentic workflow is central to the project design; AGENTS.md, CONTRIBUTING.md, and rules.md define the contract for AI-assisted development.
- Phase-based delivery model with mandatory gate closeouts ensures structured progress tracking and founder validation at each milestone.