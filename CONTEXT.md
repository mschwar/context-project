---
generated: '2026-03-18T08:20:03Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:12778c2ff714e656ec1c85737e612a7268306eb393d41212b92bc96b6effd2dc
files: 18
dirs: 9
tokens_total: 15172
---
# C:/Users/Matty/Documents/context-project

A filesystem-native manifest system that generates persistent CONTEXT.md files to help AI agents navigate and understand large codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx, defining mission, rules, required behavior, and SDLC guardrails.
- **AGENT_FIRST_OVERHAUL.md** — Comprehensive plan for reorienting ctx as agent-first infrastructure with staged rollout across structured output, unified API, non-interactive configuration, and documentation.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx with agentic SDLC principles and test-driven development.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
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
- **docs/** — Architectural documentation and design specifications for the context-project.
- **documents/** — Strategic planning and architectural thesis documents focusing on agent-first design philosophy and system overhaul strategies.
- **src/** — Source code for the core implementation of a filesystem-native context layer that generates and maintains CONTEXT.md manifests.
- **tests/** — Comprehensive test suite covering unit, integration, and compatibility testing for CLI, API, parsers, and core generation engine.

## Notes

- The project uses a hybrid Node.js/Python stack with commitlint and Husky for enforcing conventional commits and pre-commit validation.
- Agent-first design is a core architectural principle, with AGENTS.md serving as the canonical contract for agentic contributions.
- Documentation is stratified across multiple layers: operational (RUNBOOK.md), engineering standards (rules.md), contribution guidelines (CONTRIBUTING.md), and strategic vision (AGENT_FIRST_OVERHAUL.md).
- Phase-gated development with mandatory closeout sequences ensures structured progression and founder sign-off at each milestone.