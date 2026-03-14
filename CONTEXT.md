---
generated: '2026-03-14T06:46:44Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:64e0507b03fa79edf0760af5ceccd7fc2aa4655ee17c6bcb15be6aa263082f6f
files: 11
dirs: 10
tokens_total: 5637
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context layer that generates recursive CONTEXT.md summaries for codebases to enable AI agent navigation and understanding.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE settings.
- **AGENTS.md** — Defines the canonical onboarding contract, mission, rules, and workflow for agents contributing to ctx.
- **CONTRIBUTING.md** — Describes the agentic software development lifecycle, context maintenance, and contribution guidelines.
- **README.md** — Introduces ctx as a filesystem-native context layer that generates recursive CONTEXT.md summaries for codebases.
- **RUNBOOK.md** — Operational guide for running validation, using the CLI, troubleshooting failures, and developing new features.
- **architecture.md** — Explains the bottom-up generation strategy, content-based staleness detection, and component architecture of ctx.
- **pyproject.toml** — Defines project metadata, dependencies, and build configuration for the ctx package.
- **rules.md** — Engineering standards and agentic workflow rules for code quality, path handling, hashing, and LLM prompting.
- **state.md** — Current development status, completed milestones, and progress through four implementation phases.

## Subdirectories

- **.claude/** — Configuration directory for the context project's Claude integration settings and permissions.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration directory for project automation and workflows.
- **.husky/** — Configuration directory for husky, a tool that manages git hooks for automated validation and workflow operations.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Design documents and analysis for ctx, a Python CLI tool that generates hierarchical CONTEXT.md manifest files for directory trees to enable AI agent navigation of codebases.
- **sdlc-bootstrap-kit/** — Toolkit for automating SDLC environment setup with Git hooks, dependency installation, and Conventional Commits enforcement.
- **src/** — Source code for the context project, containing core modules for documentation generation and management.
- **tests/** — Test suite for the context project covering CLI, configuration, generation engine, Git integration, hashing, ignore patterns, LLM providers, manifest parsing, and language detection.

## Notes

- The project uses a bottom-up generation strategy with content-based staleness detection to maintain CONTEXT.md files across the codebase.
- Agentic workflows are formalized in AGENTS.md and rules.md to guide AI contributions and maintain code quality standards.
- Git hooks and husky configuration automate validation and enforce Conventional Commits in the development lifecycle.