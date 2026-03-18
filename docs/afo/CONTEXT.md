---
generated: '2026-03-18T08:19:33Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:2bca68f40c82d357115cdbb429491ccab84c5cf231a1909eca1293cf6bb68c82
files: 8
dirs: 0
tokens_total: 16226
---
# C:/Users/Matty/Documents/context-project/docs/afo

Architecture and design specifications for the ctx command-line tool, covering JSON envelope conventions, API unification, concurrency safety, MCP server integration, and agent workflows.

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

- These specifications form a coherent architecture: conventions (00) establish the JSON envelope contract, output-broker (01) implements structured output, unified-api (02) simplifies the command surface, config (03) handles initialization, concurrency (04) ensures safety, mcp-server (05) enables tool integration, docs (06) provides agent discovery, and workflows (07) demonstrate real-world usage patterns.
- The progression from low-level concerns (envelopes, output) to high-level patterns (workflows) suggests these should be implemented in order.