---
generated: '2026-03-14T21:53:13Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a7dc5092bacda6b27347d6569ffc2dc57d0f7b8a548705225d1d85aff045429e
files: 16
dirs: 9
tokens_total: 9797
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests for codebases, enabling AI agents to navigate and understand project structure through hierarchical filesystem documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect and normalize line endings across platforms.
- **.gitignore** — Specifies files and directories to exclude from version control (Python, IDE, test, and cache artifacts).
- **=4.0** — Empty or unrecognized file with no discernible purpose or content.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx, emphasizing agentic SDLC, context maintenance, and test-driven development.
- **GATE_CLOSEOUT.md** — Specifies the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Entry point and usage guide for ctx, a tool that generates CONTEXT.md manifests for codebases.
- **RUNBOOK.md** — Operational guide for installing, running, validating, and developing ctx with CLI commands and troubleshooting.
- **architecture.md** — Describes the bottom-up generation strategy, component breakdown, and manifest format for ctx.
- **commitlint.config.mjs** — Configures commitlint to enforce conventional commit message standards.
- **package-lock.json** — Lock file specifying exact versions of npm dependencies for reproducible builds.
- **package.json** — Defines project metadata, scripts, and npm dev dependencies for the context project.
- **pyproject.toml** — Project configuration defining the ctx package for generating CONTEXT.md manifests with CLI entry point and dependencies.
- **rules.md** — Engineering standards and agentic workflow rules for code quality and manifest generation.
- **state.md** — Development status and completed milestones for ctx across seven phases, from foundation through language expansion.

## Subdirectories

- **.claude/** — Configuration directory for the context project's Claude integration settings and permissions.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration directory containing workflow automation and action definitions for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata and diagnostic information.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archived design documents and analysis for ctx, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code directory containing the main implementation of the context project.
- **tests/** — Test suite for the context project, covering CLI, configuration, generation engine, language parsers, Git integration, and LLM providers.

## Notes

- This project uses both Python (pyproject.toml) and Node.js (package.json) tooling, with Husky and commitlint enforcing commit standards.
- The AGENTS.md, CONTRIBUTING.md, and rules.md files establish agentic workflows and development contracts for contributors.
- Archive directory preserves historical design decisions and analysis for the manifest system architecture.