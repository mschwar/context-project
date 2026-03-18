---
generated: '2026-03-18T18:17:52Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:4c2874d4cb4bed47a9b86a6cfec18c425d5e3369e357de72a03b7417686c07ba
files: 18
dirs: 9
tokens_total: 15270
---
# C:/Users/Matty/Documents/context-project

A filesystem-native manifest system that generates persistent CONTEXT.md files to enable AI agents to navigate and understand large codebases through hierarchical directory summaries.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx, defining mission, current state, rules, and SDLC guardrails.
- **AGENT_FIRST_OVERHAUL.md** — Comprehensive plan for Agent-First Overhaul reframing ctx as autonomous agent infrastructure with six staged rollout phases.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx with agentic SDLC principles and test-driven development.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **README.md** — Quick-start guide and command reference for ctx, a tool that generates persistent CONTEXT.md manifests for AI navigation of large codebases.
- **RUNBOOK.md** — Operational guide for running, validating, developing ctx including CLI usage, test execution, release publishing, and common failure modes.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, and component responsibilities.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Node.js package metadata and development dependencies for the ctx project.
- **pyproject.toml** — Python project configuration specifying dependencies, entry points, and build system.
- **rules.md** — Engineering standards and agentic rules for code quality, testing, and manifest protocol compliance.
- **state.md** — Development status and completed milestones tracking ctx's evolution from foundation through Phase 9, with current health and roadmap.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project's Claude integration.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Design documents, AI analysis, and planning materials for the ctx project.
- **docs/** — Architectural documentation and design specifications for the context-project.
- **documents/** — Strategic planning and architectural thesis documents focusing on agent-first design philosophy and system overhaul strategies.
- **src/** — Source code for the filesystem-native context layer that generates and maintains CONTEXT.md manifests through LLM-powered directory summarization.
- **tests/** — Comprehensive test suite covering unit, integration, and end-to-end testing for CLI, API, parsers, and core generation workflows.

## Notes

- The project uses a hybrid tech stack with Python (core generation engine) and Node.js (development tooling and Git hooks).
- Agentic SDLC principles are central to the project philosophy; see AGENTS.md and CONTRIBUTING.md for workflow contracts and guardrails.
- Pre-commit hooks enforce manifest freshness and conventional commit standards via Husky and commitlint.
- Phase-gated development with mandatory closeout sequences defined in GATE_CLOSEOUT.md ensures structured progression and founder validation.
- The Agent-First Overhaul represents a major architectural shift; see AGENT_FIRST_OVERHAUL.md and state.md for roadmap and current phase status.