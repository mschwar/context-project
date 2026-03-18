---
generated: '2026-03-18T03:42:03Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:926556f89f98ef81f93218d4fb4abef1ac00bdbf9ef821f0101e37df144fcd87
files: 19
dirs: 9
tokens_total: 17140
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context generation tool (ctx) that creates and maintains CONTEXT.md manifests to help AI agents navigate large codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx, defining mission, rules, required behavior, and SDLC guardrails.
- **AGENT_FIRST_OVERHAUL.md** — Comprehensive plan for reorienting ctx as agent-first infrastructure with staged rollout across structured output, unified API, non-interactive configuration, and discovery mechanisms.
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
- **state.md** — Current development status and completed milestones for ctx, tracking health, phases 1-9, and ecosystem features as of March 2026.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project's Claude integration.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Design documents, AI analysis, and planning materials for the ctx project.
- **docs/** — Documentation and architectural specifications for the context-project.
- **documents/** — Strategic documentation outlining the vision and implementation roadmap for evolving ctx into an agent-first infrastructure platform.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer that generates and maintains CONTEXT.md documentation for AI agents.
- **tests/** — Comprehensive test suite covering CLI commands, language parsers, core generation logic, Git integration, and end-to-end workflows for the context project.

## Notes

- The project uses a hybrid Node.js and Python stack (package.json and pyproject.toml), with Python as the primary implementation language.
- Git hooks (Husky, pre-commit) enforce manifest freshness and conventional commits as part of the development workflow.
- Agent-first design is central to the project vision, with AGENTS.md and AGENT_FIRST_OVERHAUL.md defining the strategic direction and operational contracts.
- Phase-based delivery model with gate closeout procedures ensures structured progress tracking and validation at each milestone.