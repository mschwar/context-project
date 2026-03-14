---
generated: '2026-03-14T21:48:03Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:f066cb70985fcd5cb62b4b11838724e33160967b4af97e4942237a18104f7850
files: 15
dirs: 9
tokens_total: 9791
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests for codebases, enabling AI agents to navigate and understand directory structures through hierarchical documentation.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect and normalize line endings across platforms.
- **.gitignore** — Specifies files and directories to exclude from version control (Python, IDE, test, and cache artifacts).
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for contributing to ctx, emphasizing agentic SDLC, context maintenance, and test-driven development.
- **GATE_CLOSEOUT.md** — Specifies the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Entry point and usage guide for ctx, a tool that generates CONTEXT.md manifests for codebases.
- **RUNBOOK.md** — Operational guide for installing, running, validating, and developing ctx with CLI commands and troubleshooting.
- **architecture.md** — Describes the bottom-up generation strategy, component breakdown, and manifest format for ctx.
- **commitlint.config.mjs** — Configures commitlint to enforce conventional commit message standards.
- **package-lock.json** — Lock file specifying exact versions of npm dependencies for reproducible builds.
- **package.json** — Defines project metadata, scripts, and npm dev dependencies for the context project.
- **pyproject.toml** — Specifies Python package configuration, dependencies, and entry points for ctx.
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
- **src/** — Source code for the context project, containing core modules for generating and managing directory manifests.
- **tests/** — Test suite for the context project, covering CLI, configuration, generation engine, language parsers, Git integration, and LLM providers.

## Notes

- This project uses conventional commits (enforced via commitlint) and Git hooks (Husky) for quality assurance.
- Python and Node.js tooling are both configured, indicating a polyglot development environment.
- The archive directory preserves historical design decisions and analysis for reference.