---
generated: '2026-03-18T18:25:24Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:2759dbf45f021ca16cafdcd677e6a72fd4068e311cffde488ce769d28b5a1b32
files: 8
dirs: 0
tokens_total: 16226
---
# C:/Users/Matty/Documents/context-project/docs/afo

Architecture and design specifications for the ctx command-line tool, covering JSON output conventions, API unification, concurrency safety, MCP server integration, and agent workflows.

## Files

- **00-conventions.md** — Defines JSON envelope schema, error taxonomy, exit codes, output modes, and testing conventions for ctx commands.
- **01-output-broker.md** — Specifies OutputBroker context manager that intercepts stdout/stderr and emits structured JSON envelopes in JSON mode.
- **02-unified-api.md** — Collapses 12 CLI commands into 4 canonical commands (refresh, check, export, reset) backed by a new api.py module.
- **03-config-and-bootstrap.md** — Specification for environment variable parity, budget guardrails, and auto-config bootstrap in ctx.
- **04-concurrency.md** — Introduces PID-based file locking and atomic writes via os.replace to prevent concurrent write corruption.
- **05-mcp-server.md** — Specification for stdio-based MCP server exposing ctx API functions as tools over JSON-RPC 2.0.
- **06-docs-and-discovery.md** — Rewrites AGENTS.md as machine-readable agent onboarding contract with command examples, error codes, and integration patterns.
- **07-workflow-patterns.md** — Documents standard workflows: pre-commit hooks, CI gates, PR context blocks, agent handoff recipes, and natural language command mapping.

## Subdirectories

- None

## Notes

- These specifications form a coherent architecture: conventions (00) establish the JSON contract, OutputBroker (01) implements it, the unified API (02) simplifies the CLI surface, config (03) handles initialization, concurrency (04) ensures safety, MCP (05) enables tool integration, and docs/discovery (06) + workflows (07) guide adoption.
- The progression from low-level concerns (output formatting, locking) to high-level patterns (agent workflows) suggests these should be implemented in order.
- Cross-module dependencies: OutputBroker depends on conventions; unified API depends on both; MCP server depends on unified API; workflows depend on all prior layers.