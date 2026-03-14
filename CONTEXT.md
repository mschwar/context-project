---
generated: '2026-03-14T05:55:09Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:7aeeaec0143cad091f90501f5c23aa1c713d34bce935877f35e29f88e8e2ff84
files: 11
dirs: 8
tokens_total: 5434
---
# C:/Users/Matty/Documents/context-project

A tool that generates CONTEXT.md manifests to help AI agents navigate codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx covering version control, Python, Node.js, IDE, temporary files, OS junk, and environment secrets.
- **.gitattributes** — Git configuration file that enables automatic line-ending normalization for text files across platforms.
- **.gitignore** — Git ignore rules for Python artifacts, virtual environments, IDE caches, test artifacts, and environment configuration files.
- **AGENTS.md** — Canonical onboarding and workflow contract for agents contributing to ctx, including mission, rules, required behaviors, and development phases.
- **CONTRIBUTING.md** — Contributing guidelines for the agentic SDLC, covering context maintenance, implementation blocks, test-driven autonomy, and manifest review practices.
- **README.md** — Project overview and installation instructions for ctx, a tool that generates CONTEXT.md manifests to help AI agents navigate codebases.
- **RUNBOOK.md** — Operational runbook covering prerequisites, validation procedures, CLI usage, common failure modes, and development task guidelines.
- **architecture.md** — Architecture documentation describing the bottom-up generation strategy, content-based staleness detection, component breakdown, and manifest format.
- **pyproject.toml** — Python project configuration file specifying dependencies, build system, entry points, and optional development tools for ctx.
- **rules.md** — Engineering standards and agentic rules covering code principles, path handling, hash integrity, binary safety, manifest protocol, and testing requirements.
- **state.md** — Development status report documenting completed milestones, current health, and three-phase roadmap for hygiene, reliability, and ecosystem integration.

## Subdirectories

- **.claude/** — Configuration directory for Claude context and project settings.
- **.github/** — GitHub configuration directory for project automation and workflows.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.pytest_cache/** — Pytest cache directory for storing test execution metadata and plugin data.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Design documents and analysis for ctx, a Python CLI tool that generates hierarchical CONTEXT.md manifest files for directory trees to enable AI agent navigation of codebases.
- **src/** — Source code directory for the context project.
- **tests/** — Test suite for the context-project application covering CLI, configuration, generation, and integration functionality.

## Notes

- None