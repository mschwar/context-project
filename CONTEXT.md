---
generated: '2026-03-14T21:18:28Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ef65b1aa10cc7b8f1e0a138bbdbd0d53dd2d080611149408a39870ea18f9549e
files: 15
dirs: 9
tokens_total: 9691
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests for codebases, enabling AI agents to navigate and understand project structure through hierarchical documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect and normalize line endings across platforms.
- **.gitignore** — Specifies files and directories to exclude from version control (Python, IDE, test, and cache artifacts).
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Describes how to participate in the agentic SDLC workflow and maintain context manifests.
- **GATE_CLOSEOUT.md** — Specifies the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Entry point and usage guide for ctx, a tool that generates CONTEXT.md manifests for codebases.
- **RUNBOOK.md** — Operational guide for running validation, using the CLI, and handling common failure modes.
- **architecture.md** — Describes the bottom-up generation strategy, component breakdown, and manifest format for ctx.
- **commitlint.config.mjs** — Configures commitlint to enforce conventional commit message standards.
- **package-lock.json** — Lock file specifying exact versions of npm dependencies for reproducible builds.
- **package.json** — Defines project metadata, scripts, and npm dev dependencies for the context project.
- **pyproject.toml** — Specifies Python package configuration, dependencies, and entry points for ctx.
- **rules.md** — Engineering standards and agentic workflow rules for code quality and manifest generation.
- **state.md** — Development status tracker documenting completed phases, current health, and upcoming milestones for the ctx project.

## Subdirectories

- **.claude/** — Configuration directory for the context project's Claude integration settings and permissions.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration directory containing workflow automation and action definitions for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archived design documents and analysis for ctx, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code directory containing the core implementation of the context project's CLI tools and documentation generation system.
- **tests/** — Test suite for the context project, covering CLI, configuration, generation engine, language parsers, LLM integration, and manifest handling.

## Notes

- This project uses both Python (pyproject.toml) and Node.js (package.json) tooling, with Git hooks managed by Husky for commit validation.
- The AGENTS.md, CONTRIBUTING.md, and rules.md files define the agentic SDLC workflow and contribution standards.
- State tracking and roadmap closeout procedures are documented in state.md and GATE_CLOSEOUT.md respectively.