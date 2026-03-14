---
generated: '2026-03-14T23:09:35Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:e2a0c1deeee34bd5ace41b4f0f1e0cf9a8fd575814b6957367f49820705aefc1
files: 17
dirs: 9
tokens_total: 11846
---
# C:/Users/Matty/Documents/context-project

A filesystem-native tool that generates CONTEXT.md manifests to help AI agents navigate and understand large codebases through hierarchical directory summaries.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Onboarding contract and workflow guide for agents contributing to ctx, covering mission, current state, canonical rules, and development phases.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Quick-start guide and feature overview for ctx, a tool that generates CONTEXT.md manifests to help AI agents navigate large codebases.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, testing, release publishing, cache management, and common failure modes for ctx development.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, LLM abstraction, and data flow.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration specifying dependencies, entry points, and metadata for the ctx-tool PyPI distribution.
- **rules.md** — Engineering standards and agentic rules for code quality, path handling, and manifest protocol compliance.
- **state.md** — Development status and completed milestones tracking ctx's progress through ten phases from foundation to reliability and automation.

## Subdirectories

- **.claude/** — Local configuration and settings directory for the context project.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **.pytest_cache/** — Pytest cache directory storing test execution metadata, results, and configuration to optimize test runs.
- **.worktrees/** — Git worktrees configuration and management directory for the context-project.
- **archive/** — Archive of design documents, roadmaps, and AI analysis for the ctx project—a filesystem-native hierarchical manifest system enabling coarse-to-fine directory navigation.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer.
- **tests/** — Test suite for the context-project, covering CLI, configuration, code parsing, Git integration, LLM clients, and manifest generation.

## Notes

- The project uses Python (pyproject.toml) with Node.js tooling (package.json) for development automation and commit validation.
- AGENTS.md, CONTRIBUTING.md, and rules.md define the agentic workflow and engineering standards for contributors.
- state.md and GATE_CLOSEOUT.md track development progress and phase completion requirements.
- The archive/ directory preserves historical design decisions and analysis for reference.