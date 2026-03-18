---
generated: '2026-03-18T18:26:26Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a03e0ac31a561656bb284f09001bf8a3dc579726f656e3522da19daa46ba3d1d
files: 18
dirs: 9
tokens_total: 15270
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context layer tool (ctx) that generates persistent CONTEXT.md manifests to enable AI agents to navigate and understand large codebases without reading raw files.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and sensitive data.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx, defining mission, current state, rules, required behavior, and SDLC guardrails.
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
- **state.md** — Development status tracker documenting completed milestones, current health, and active phases for the ctx filesystem-native context layer project.

## Subdirectories

- **.claude/** — Configuration directory storing local settings and permissions for the context project's Claude integration.
- **.githooks/** — Git hooks that enforce automated testing and code quality checks before commits are made to the repository.
- **.github/** — GitHub configuration files and automation workflows that support CI/CD processes and custom actions for the context-project.
- **.husky/** — Git hooks that enforce code quality standards and branching workflows through automated validation at commit and push stages.
- **archive/** — Design documents, AI analysis, and planning materials for the ctx project.
- **docs/** — Documentation and architectural specifications for the context-project, including design decisions and implementation guidelines.
- **documents/** — Strategic planning and architectural thesis documents for the context-project, focusing on agent-first design principles and system overhaul strategies.
- **src/** — Source code for a filesystem-native context layer that generates and maintains CONTEXT.md manifests for AI agent documentation.
- **tests/** — Comprehensive test suite covering unit, integration, and end-to-end testing for the context manifest generation system, including CLI, parsers, configuration, and LLM integration.

## Notes

- The project enforces agentic SDLC principles through AGENTS.md, CONTRIBUTING.md, and rules.md, establishing a contract for agent-driven development workflows.
- Git hooks (.githooks, .husky) and pre-commit configuration enforce manifest freshness and conventional commits before code integration.
- Dual language support: Python (pyproject.toml, src/) for core CLI and Node.js (package.json) for development tooling and Git automation.
- State tracking (state.md) and gate closeout procedures (GATE_CLOSEOUT.md) provide phase-based project governance and validation checkpoints.
- Archive and documents directories preserve design evolution and strategic planning artifacts separate from active source and documentation.