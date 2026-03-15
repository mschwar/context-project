---
generated: '2026-03-15T08:03:00Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:925c3e8abf50ce6e1c8ebf979110b1f682634e386a2297da4c9ab34c54f27780
files: 18
dirs: 7
tokens_total: 14579
---
# C:/Users/Matty/Documents/context-project

A filesystem-native context tool that generates hierarchical CONTEXT.md manifests so agents can navigate projects with coarse-to-fine summaries.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx, excluding version control, dependencies, editor state, workspace caches, temporary artifacts, and transient editor byproducts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control, including Python artifacts, editor state, workspace caches, and transient temp files.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that checks if ctx manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Canonical onboarding and workflow contract defining mission, rules, Phase 16 gate order, and SDLC guardrails for agents contributing to ctx.
- **CONTRIBUTING.md** — Guidelines for participating in the agentic SDLC workflow and maintaining code quality standards.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **PHASE16_HANDOFF.md** — Gate-by-gate execution contract for Phase 16, with scope, validation, and guardrails tailored for smaller models.
- **README.md** — Project overview and quick start for generating and maintaining hierarchical CONTEXT.md manifests.
- **RUNBOOK.md** — Operational runbook covering prerequisites, CLI usage, testing, release publishing, cache management, common failure modes, and Phase 16 handoff guidance.
- **architecture.md** — System design overview covering the manifest navigation primitive, bottom-up generation, content hashing, and component responsibilities.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Project metadata and scripts for Node.js tooling including commitlint and Husky setup.
- **pyproject.toml** — Python package configuration specifying dependencies, entry points, and metadata for the ctx-tool PyPI distribution.
- **rules.md** — Engineering standards and agentic rules for code quality, manifest protocol compliance, and ignore consistency.
- **state.md** — Development status tracker documenting completed milestones, current health, and the gated Phase 16 roadmap.

## Subdirectories

- **.claude/** — Configuration directory for the context project containing local settings and permitted operations.
- **.githooks/** — Git hooks directory for automated pre-commit testing and validation.
- **.github/** — GitHub configuration and automation for the context-project repository.
- **.husky/** — Husky configuration directory containing Git hooks for commit message validation and branch protection.
- **archive/** — Archive of design documents, analyses, and reflections for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **src/** — Source code for the context project, containing core modules for AI agent context generation.
- **tests/** — Test suite covering CLI commands, configuration, language parsers, core generation engine, Git integration, hashing, ignore patterns, LLM client, manifest handling, and server endpoints.

## Notes

- This project uses both Python (pyproject.toml) and Node.js (package.json) tooling for development and distribution.
- Git hooks and pre-commit validation ensure manifest freshness and conventional commit compliance.
- The archive directory preserves design history and rationale for the manifest system.
- Phase 16 now has an explicit handoff document that scopes one gate per branch and adds tighter guardrails for narrower models.
- Default ignore rules now skip workspace-noise directories such as `.pytest_cache/`, `.worktrees/`, and `.tmp/`, plus transient `*.tmp.*` and `*.pyc.*` artifacts.
