---
generated: '2026-03-17T07:15:28Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:7f9f6784eb1bc2c7e3be9bd49eb720a9225bfc5e757dda93501e30c191651480
files: 18
dirs: 7
tokens_total: 15258
---
# C:/Users/Matty/Documents/context-project

A filesystem-native manifest generation tool (ctx) that creates persistent CONTEXT.md files to help AI agents navigate and understand large codebases through hierarchical directory summaries.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx, defining mission, rules, required behaviors, and SDLC guardrails.
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
- **state.md** — Development status document tracking completed milestones, current health, and phase progress for the ctx project through Phase 20.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project's Claude integration.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Design documents, AI analysis, and project reflections documenting the evolution and architectural decisions for the ctx tool.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer for AI agents.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, configuration, Git integration, LLM client functionality, and end-to-end workflows for the context manifest generation system.

## Notes

- The project uses a hybrid tech stack with Python (core implementation) and Node.js (development tooling), coordinated through package.json and pyproject.toml.
- Agentic SDLC principles are central to the project; AGENTS.md, CONTRIBUTING.md, and rules.md define the contract for AI-assisted development.
- Pre-commit hooks (Husky, .pre-commit-hooks.yaml) enforce manifest freshness and conventional commits, ensuring consistency across phases.
- Phase-based delivery model documented in GATE_CLOSEOUT.md and PHASE16_HANDOFF.md; state.md tracks progress through Phase 20.
- Archive directory preserves design rationale and architectural evolution, supporting long-term maintainability and agent onboarding.