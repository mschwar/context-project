---
generated: '2026-03-18T03:41:43Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:2ea776242e4d05370b623505a77a4ea4f687dd7033bea01d45b0b28a3195b988
files: 8
dirs: 0
tokens_total: 16254
---
# C:/Users/Matty/Documents/context-project/docs/afo

Architectural specification documents defining the unified API, conventions, and integration patterns for the ctx command-line tool.

## Files

- **00-conventions.md** — Defines JSON envelope schema, error taxonomy, exit codes, output modes, and testing conventions for ctx commands.
- **01-output-broker.md** — Specifies OutputBroker context manager that intercepts stdout/stderr and emits structured JSON envelopes in JSON mode.
- **02-unified-api.md** — Collapses 12 CLI commands into 4 canonical commands (refresh, check, export, reset) backed by a new api.py module.
- **03-config-and-bootstrap.md** — Establishes environment variable parity for all config fields, budget guardrails, auto-config flow, and prompt elimination rules.
- **04-concurrency.md** — Introduces PID-based file locking and atomic writes via os.replace to prevent concurrent write corruption.
- **05-mcp-server.md** — Defines stdio-based MCP server exposing ctx's 4 API functions as JSON-RPC 2.0 tools for IDE integration.
- **06-docs-and-discovery.md** — Rewrites AGENTS.md as machine-readable agent onboarding contract with command examples, error codes, and integration patterns.
- **07-workflow-patterns.md** — Documents standard workflows: pre-commit hooks, CI gates, PR context blocks, agent handoff recipes, and natural language command mapping.

## Subdirectories

- None

## Notes

- Documents are sequenced numerically to reflect implementation order and dependency flow: conventions → output handling → API unification → configuration → concurrency safety → MCP server → documentation → workflows.
- The unified API (02) is the architectural centerpiece; all other specs support or depend on its 4-command model.
- MCP server (05) and workflow patterns (07) enable integration with external tools and CI/CD systems.