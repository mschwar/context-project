---
generated: '2026-03-18T21:06:52Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:8fa68b2264c275a6474c82eeb85f34074f9e132fee13535aa661da1f153d7137
files: 19
dirs: 8
tokens_total: 15032
---
# C:/Users/Matty/Documents/context-project

A filesystem-native hierarchical manifest system (ctx) that generates and maintains CONTEXT.md documentation to enable AI agents to navigate and understand codebases autonomously.

## Files

- **.ctxignore.default** — Default ignore patterns for ctx tool, excluding version control, dependencies, IDE files, and temporary artifacts.
- **.gitattributes** — Configures Git to auto-detect text files and normalize line endings to LF.
- **.gitignore** — Specifies files and directories to exclude from version control and context generation.
- **.pre-commit-hooks.yaml** — Pre-commit hook configuration that validates CONTEXT.md manifests are fresh before commits.
- **=4.0** — Empty or malformed file with no discernible purpose.
- **AGENTS.md** — Comprehensive agent-oriented documentation covering ctx installation, configuration, commands, error codes, and integration patterns.
- **AGENT_FIRST_OVERHAUL.md** — Living plan documenting the agent-first overhaul of ctx, detailing thesis, kept components, surface changes, and six-stage rollout for autonomous agent infrastructure.
- **CONTRIBUTING.md** — Developer workflow guidelines for agentic SDLC including context maintenance, implementation blocks, and test-driven autonomy.
- **GATE_CLOSEOUT.md** — Defines the mandatory closeout sequence for each project phase, including validation, reflection, suggestion disposition, and founder sign-off.
- **README.md** — Quick-start guide directing users to install ctx-tool, set API keys, and consult AGENTS.md for command contract.
- **RUNBOOK.md** — Operational runbook documenting how to run tests, use CLI commands, publish releases, and troubleshoot common failures.
- **architecture.md** — System design overview covering bottom-up generation, content hashing, and component responsibilities.
- **commitlint.config.mjs** — Configuration file specifying commitlint extends conventional commit rules.
- **mcp.json** — MCP server configuration file exposing ctx as a Model Context Protocol service for agent integration.
- **package-lock.json** — Dependency lock file for Node.js packages including commitlint and Husky.
- **package.json** — Node.js package metadata and development dependencies for the ctx project.
- **pyproject.toml** — Python package metadata defining ctx-tool distribution with dependencies, entry points, and optional extras.
- **rules.md** — Engineering standards and agentic rules for code quality, testing, and manifest protocol compliance.
- **state.md** — Development status tracker showing completed phases 1-21 and AFO stages 1-6, current health metrics, test coverage, LLM support, and active phase 24 scope.

## Subdirectories

- **.githooks/** — This directory contains Git hooks that enforce automated testing and code quality checks before commits are made to the repository.
- **.github/** — This directory contains GitHub configuration files and automation workflows that support CI/CD processes and custom actions for the context-project.
- **.husky/** — This directory contains Git hooks that enforce code quality standards and branching workflows through automated validation at commit and push stages.
- **archive/** — This directory contains design documents, AI analysis, and roadmap materials for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.
- **docs/** — Documentation and architectural specifications for the context-project, including design decisions and implementation guidelines.
- **documents/** — This directory contains strategic planning and architectural thesis documents for the context-project, focusing on agent-first design principles and system overhaul strategies.
- **src/** — This directory contains the source code for a context management system that generates and maintains filesystem-native documentation for AI agents.
- **tests/** — Comprehensive test suite covering unit, integration, and end-to-end testing for the context project including CLI, API, parsers, and server components.

## Notes

- The project follows an agent-first architecture with dual packaging (Python via pyproject.toml and Node.js via package.json) to support both CLI and MCP server deployments.
- Development workflow is enforced through pre-commit hooks (.husky, .githooks) that validate CONTEXT.md freshness and conventional commits before code integration.
- Documentation is stratified: AGENTS.md and README.md serve end-users; CONTRIBUTING.md and RUNBOOK.md guide developers; AGENT_FIRST_OVERHAUL.md and state.md track architectural evolution and phase completion.
- The project uses a structured phase-based delivery model with mandatory gate closeouts (GATE_CLOSEOUT.md) and engineering rules (rules.md) to maintain quality and autonomy standards.
<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
