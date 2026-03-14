---
generated: '2026-03-14T22:58:45Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:fe2002895723e693d5826abf5214acaa3c4ccd9193cf37730cd5329f11ed04c0
files: 17
dirs: 9
tokens_total: 11639
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context layer tool that generates CONTEXT.md manifests to help AI agents navigate and understand codebases.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts and IDE caches.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, phases, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the required closeout sequence for completing roadmap phases with validation and reflection.
- **README.md** — Quick-start guide and command reference for ctx, a tool that generates CONTEXT.md manifests for codebases.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, validation, LLM caching, common failure modes, and development tasks.
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
- **archive/** — Archived design documents and analysis for the ctx project, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code for the context-project, containing the core implementation of a filesystem-native context layer.
- **tests/** — Test suite for the context-project, covering CLI, configuration, code parsing, Git integration, LLM client operations, and manifest generation.

## Notes

- The project uses Python (pyproject.toml) and Node.js (package.json) tooling for development and distribution.
- Git hooks and pre-commit validation ensure manifest freshness and conventional commit compliance.
- Documentation includes agent workflows (AGENTS.md), engineering rules (rules.md), and operational guidance (RUNBOOK.md).