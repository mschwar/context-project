---
generated: '2026-03-14T21:13:17Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:fbc5175c8865c80f53c2039eefb2d3bf86ee106cee6923e6ea8012297459fe5c
files: 15
dirs: 9
tokens_total: 9737
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests for codebases, enabling hierarchical directory navigation and agentic documentation workflows.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect and normalize line endings across platforms.
- **.gitignore** — Specifies files and directories to exclude from version control (Python, IDE, test, and cache artifacts).
- **AGENTS.md** — Defines the canonical onboarding contract and workflow for agents contributing to the ctx project.
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
- **state.md** — Current development status, completed milestones, and roadmap phases for ctx project.

## Subdirectories

- **.claude/** — Configuration directory for the context project's Claude integration settings and permissions.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration directory containing workflow automation and action definitions for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archive of design documents, AI model analyses, and project reflections for the ctx tool—a filesystem-native hierarchical manifest system enabling coarse-to-fine directory navigation.
- **src/** — Source code directory containing the core implementation of the context project's CLI tools and documentation generation system.
- **tests/** — Test suite for the context project, covering CLI, configuration, generation engine, language parsers, LLM integration, and manifest handling.

## Notes

- The project uses both Python (pyproject.toml) and Node.js (package.json) tooling, with Git hooks managed by Husky for commit validation.
- Documentation includes operational guides (RUNBOOK.md), contribution standards (CONTRIBUTING.md, AGENTS.md), and engineering rules (rules.md) for agentic workflows.
- The archive/ directory preserves design history and reflections on the manifest system's evolution.