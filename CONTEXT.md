---
generated: '2026-03-14T05:58:16Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ac5e1d9b90f03ccc9184c13c702cab5f5c75f16baea066d6cf5102849e09f18b
files: 11
dirs: 8
tokens_total: 5434
---
# C:/Users/Matty/Documents/context-project

Tool that generates CONTEXT.md manifests to help AI agents navigate codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, covering version control, Python/Node.js environments, IDE files, temporary files, OS junk, and secrets.
- **.gitattributes** — Git configuration file that enables automatic line-ending normalization for text files across platforms.
- **.gitignore** — Git ignore rules for Python artifacts, virtual environments, IDE caches, test artifacts, and environment configuration files.
- **AGENTS.md** — Canonical onboarding and workflow contract for AI agents contributing to ctx, including mission, rules, current state, and development phases.
- **CONTRIBUTING.md** — Contribution guidelines for the agentic SDLC workflow, covering context maintenance, test-driven development, and manifest review practices.
- **README.md** — Project overview and installation instructions for ctx, a tool that generates CONTEXT.md manifests to help AI agents navigate codebases.
- **RUNBOOK.md** — Operational runbook covering prerequisites, validation procedures, CLI usage, common failure modes, and development task guidelines.
- **architecture.md** — Technical architecture documentation describing bottom-up generation, content-based staleness detection, component breakdown, and manifest format specification.
- **pyproject.toml** — Python project configuration file defining dependencies, build system, package metadata, and entry points for the ctx command-line tool.
- **rules.md** — Engineering standards and agentic rules covering code principles, workflow rules, hash integrity, binary safety, manifest protocol, and testing requirements.
- **state.md** — Development status report documenting completed milestones, current health, and three-phase roadmap for hygiene, reliability, and ecosystem integration.

## Subdirectories

- **.claude/** — Configuration directory for Claude context and project settings.
- **.github/** — GitHub configuration directory for project automation and workflows.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.pytest_cache/** — Pytest cache directory for storing test execution metadata and plugin data.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Design documents and analysis for ctx, a Python CLI tool that generates hierarchical CONTEXT.md manifest files for directory trees to enable AI agent navigation of codebases.
- **src/** — Filesystem-native context layer for AI agents with CLI tools and LLM integration.
- **tests/** — Test suite for the context-project application covering CLI, configuration, generation, and integration functionality.

## Notes

- None