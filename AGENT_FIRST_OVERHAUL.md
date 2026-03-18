# Agent-First Overhaul: Comprehensive Plan

> **Status:** Draft — March 17, 2026
> **Authors:** Matt Schwartz, Claude (Technical Lead)
> **Supersedes:** Phases 22–23 in `state.md`

---

## The Thesis

`ctx` should not be a tool humans operate. It should be infrastructure that agents consume, install, configure, and maintain autonomously. The human's role is giving their agent a high-level directive — "keep context fresh," "update ctx before you commit" — the same way they'd say "open a PR" or "run the tests." The agent does the rest.

This reframe preserves everything valuable about the engine (bottom-up traversal, content hashing, incremental updates, parallel processing, 11 language parsers, persistent cache) while re-orienting every surface that touches the outside world: the CLI, the documentation, the output format, the error handling, the installation flow, the MCP server, the package metadata, and the discovery story.

---

## What We Keep (The Engine)

These components are already agent-friendly and need no fundamental changes:

| Component | Why It Stays |
|-----------|-------------|
| Bottom-up tree traversal | Correct algorithm, no UX dependency |
| SHA-256 content hashing + staleness detection | Purely programmatic |
| Incremental update logic | Already optimized for repeated runs |
| Parallel depth-level processing | I/O-bound threading, no human interaction |
| Persistent LLM disk cache | Transparent, model-aware, works silently |
| 11 language parsers | Pure extraction, no UI coupling |
| `.ctxconfig` resolution chain | Already supports env vars and file-based config |
| `.ctxignore` / pathspec filtering | Already declarative |
| Token budget enforcement | Already silent when exhausted |
| LLM provider abstraction | Protocol-based, clean separation |

---

## What Changes (The Surfaces)

### The Problem With the Current Surface

The current CLI was designed for a human sitting at a terminal:

- **12 separate commands** with overlapping concerns (`init` vs `update` vs `smart-update`, `status` vs `stats` vs `verify`)
- **Human-formatted output** (progress bars, colored text, cost estimates printed to stdout)
- **Interactive setup** (`ctx setup` probes and asks questions)
- **Documentation written for human readers** (README with "Quick Start," tutorial-style flow)
- **Error messages that assume a human is reading** (prose hints, shell-specific remediation)
- **Discovery optimized for humans** (PyPI badges, README on GitHub)

An agent needs none of this. An agent needs:

1. A predictable, parseable interface (JSON in, JSON out)
2. Non-interactive installation and configuration
3. A minimal command surface (fewer concepts to learn)
4. Documentation it can read in-context (structured, scannable, compact)
5. Discovery through the channels agents actually use (MCP registries, package metadata, `AGENTS.md` files)
6. Errors that are machine-actionable (exit codes + structured error objects, not prose)

---

## Staged Rollout

The overhaul is broken into six stages. Each stage is independently shippable, testable, and backwards-compatible with the previous state. No big-bang rewrite.

---

### Stage 1: Structured Output Layer

**Goal:** Every existing command gains a machine-readable mode. Agents can start using `ctx` today without parsing human text.

**What ships:**

- **`--output json` global flag** on every command that produces output. When set:
  - All output goes to stdout as a single JSON object
  - No progress bars, no color, no prose
  - Errors are included in the JSON (`"errors": [...]`) rather than printed to stderr
  - Exit codes remain meaningful (0 = success, 1 = failure, 2 = partial)

- **Structured response schemas** documented in a machine-readable format:
  ```
  ctx init . --output json    → { "status": "ok", "dirs_processed": 18, "dirs_skipped": 0, "tokens_used": 4200, "errors": [] }
  ctx update . --output json  → { "status": "ok", "dirs_processed": 3, "dirs_skipped": 15, "stale_before": 3, "stale_after": 0, "errors": [] }
  ctx status . --output json  → { "total": 18, "fresh": 18, "stale": 0, "missing": 0 }
  ctx verify . --output json  → (already exists, extend if needed)
  ctx stats . --output json   → (already exists, extend if needed)
  ctx diff . --format json    → (already exists, extend if needed)
  ```

- **`CTX_OUTPUT=json` environment variable** as an alternative to the flag, so agents can set it once in their environment.

**What doesn't change:** All existing human-formatted output remains the default. Zero breakage for anyone using `ctx` today.

**Files touched:** `cli.py` (add global option + output routing), possibly a new `output.py` module for JSON serialization helpers.

**Tests:** Each command gets a `--output json` test that validates the schema. Existing tests untouched.

**Definition of done:** An agent can run any `ctx` command, parse the JSON output, and make decisions without regex or string matching.

---

### Stage 2: Unified Agent API

**Goal:** Collapse the 12-command surface into a small, composable API that maps to how agents actually think about context maintenance.

**The current 12 commands map to 4 agent operations:**

| Agent Operation | What It Does | Replaces |
|----------------|-------------|----------|
| `ctx refresh` | Make all manifests fresh. Auto-selects the fastest strategy (full init if no manifests exist, smart-update if git is available, incremental update otherwise). | `init`, `update`, `smart-update` |
| `ctx check` | Report health as structured data. Returns staleness, coverage, frontmatter validity, provider connectivity — everything an agent needs to decide whether to refresh. | `status`, `stats`, `verify`, `doctor` (planned) |
| `ctx export` | Emit manifest content for ingestion. Already agent-friendly; keep as-is with minor schema improvements. | `export` (stays) |
| `ctx reset` | Remove all manifests. Clean slate. | `clean` (rename for clarity) |

**Commands that become subcommands or flags:**

| Current Command | Becomes |
|----------------|---------|
| `ctx setup` | `ctx refresh --setup` (auto-configures if no `.ctxconfig` exists, then refreshes) |
| `ctx watch` | `ctx refresh --watch` (refresh then watch for changes) |
| `ctx diff` | `ctx check --diff` (diff is a health signal, not a separate concept) |
| `ctx serve` | `ctx serve` (stays — it's a different runtime mode) |

**The agent mental model becomes:**
```
ctx refresh   →  "make it fresh"
ctx check     →  "is it fresh?"
ctx export    →  "give me the context"
ctx reset     →  "start over"
ctx serve     →  "serve it over HTTP"
```

**Backwards compatibility:** The old command names remain as hidden aliases for at least one major version. `ctx init .` still works, it just routes to `ctx refresh .`. Deprecation warnings only appear in human-formatted output, never in JSON mode.

**Files touched:** `cli.py` (major restructure), new `api.py` module that both the CLI and MCP server call into.

**Tests:** New test suite for the unified API. Old command tests become regression tests for the aliases.

**Definition of done:** An agent needs to know exactly 4 commands (plus `serve`) to fully operate `ctx`.

---

### Stage 3: Non-Interactive Installation & Configuration

**Goal:** An agent can install and configure `ctx` with zero interactive prompts, zero human intervention, and zero ambiguity about whether it worked.

**What ships:**

- **Silent install path:**
  ```bash
  pip install ctx-tool
  ```
  Already works. No changes needed here.

- **Zero-config mode:** If no `.ctxconfig` exists and no env vars are set, `ctx refresh` auto-detects the provider (same logic as current `ctx setup`) and writes `.ctxconfig` automatically. No prompts. The JSON output includes what was detected:
  ```json
  { "auto_configured": true, "provider": "anthropic", "model": "claude-3-5-haiku-20241022" }
  ```

- **Config-as-code:** Full configuration via environment variables, so agents can configure without writing files:
  ```bash
  CTX_PROVIDER=anthropic CTX_MODEL=claude-3-5-haiku-20241022 ctx refresh .
  ```
  Document every env var. Currently partial — make it complete for every config field.

- **Verification built into refresh:** After auto-configuration, the first refresh verifies connectivity before spending tokens. If it fails, the JSON output includes the error and a machine-readable remediation hint:
  ```json
  { "status": "error", "error_code": "provider_unreachable", "provider": "anthropic", "hint": "Set ANTHROPIC_API_KEY environment variable" }
  ```

- **`AGENTS.md` install block:** A copy-pasteable (by an agent) install-and-verify sequence:
  ```bash
  pip install ctx-tool && ctx check . --output json
  ```

**Files touched:** `config.py` (complete env var mapping), `cli.py` (auto-config in refresh path), `AGENTS.md`.

**Tests:** End-to-end test: fresh virtualenv → `pip install` → `ctx refresh . --output json` → verify JSON schema. Auto-config test with mock provider detection.

**Definition of done:** An agent can go from "ctx is not installed" to "all manifests are fresh" in two commands with no human interaction.

---

### Stage 4: Agent-Native Documentation

**Goal:** The primary documentation is optimized for agent consumption. Human documentation exists but is secondary.

**Documentation tiers:**

#### Tier 1: Agent-Facing (Primary)

- **`AGENTS.md` (rewrite)** — The canonical "how to use ctx" for agents. Restructured as:
  - **What ctx is** (2 sentences)
  - **Install** (1 command)
  - **Configure** (env vars table, auto-detect explanation)
  - **Core operations** (the 4 commands with JSON schemas)
  - **Integration patterns** (pre-commit hook, CI check, session-end hook, PR workflow)
  - **Troubleshooting** (error codes → remediation table, no prose)
  - **Manifest format** (exact schema, frontmatter fields, body structure)
  - No tutorial flow. No "quick start." Just a reference document an agent can ctrl+F.

- **`CONTEXT.md` files themselves** — Already agent-readable. No changes to the manifest format.

- **MCP tool descriptions** — When `ctx serve` is registered as an MCP server, its tool descriptions should be concise and action-oriented:
  ```
  ctx_refresh: Regenerate stale CONTEXT.md manifests in a directory tree. Returns JSON with dirs_processed, tokens_used, errors.
  ctx_check: Report manifest health (staleness, coverage, validity). Returns JSON.
  ctx_export: Concatenate all CONTEXT.md files under a path. Returns combined manifest text.
  ```

#### Tier 2: Human-Facing (Secondary)

- **`README.md` (rewrite)** — Short. Aimed at a human who's deciding whether to tell their agent to use `ctx`:
  - What it is (1 paragraph)
  - Why (1 paragraph — "your agent reads these instead of every file")
  - How (tell your agent: "install ctx-tool and run ctx refresh")
  - Links to `AGENTS.md` for the real docs
  - No command reference table (that's in `AGENTS.md`)

- **`architecture.md`** — Keep as-is. Useful for both agents and humans doing deep work.

- **`CONTRIBUTING.md`** — Keep the agentic SDLC sections. Update command references.

- **`RUNBOOK.md`** — Keep for operational reference. Update command references.

#### Tier 3: Package Metadata

- **PyPI description** — Rewrite the `description` field and long description to include keywords agents and agent frameworks search for: "AI agent," "codebase context," "CONTEXT.md," "MCP," "manifest generation."

- **PyPI classifiers** — Add:
  ```
  "Framework :: MCP"  (if/when this exists)
  "Topic :: Software Development :: Code Generators"
  "Topic :: Software Development :: Documentation"
  ```

- **Package keywords** — Add a `keywords` field to `pyproject.toml`:
  ```
  keywords = ["ai", "agent", "context", "codebase", "mcp", "manifest", "llm"]
  ```

**Files touched:** `AGENTS.md` (major rewrite), `README.md` (major rewrite), `pyproject.toml` (metadata), MCP tool descriptions in `server.py`.

**Tests:** Validate that `AGENTS.md` contains all required sections (can be a simple grep-based test). Validate package metadata fields exist.

**Definition of done:** An agent encountering `ctx` for the first time can read `AGENTS.md` and fully operate the tool without reading any other file.

---

### Stage 5: MCP-Native Integration

**Goal:** `ctx` is a first-class MCP server that agents discover and use through standard MCP tooling, not just an HTTP API bolted on.

**What ships:**

- **Proper MCP server implementation:** The current `server.py` is a basic FastAPI app with one endpoint. Replace with (or wrap in) a proper MCP server that:
  - Registers tools (`ctx_refresh`, `ctx_check`, `ctx_export`, `ctx_reset`)
  - Each tool has typed input/output schemas
  - Supports the MCP discovery protocol so agent frameworks can auto-detect capabilities
  - Runs as a subprocess (stdio transport) or HTTP (SSE transport), matching MCP conventions

- **MCP server manifest** (`mcp.json` or equivalent):
  ```json
  {
    "name": "ctx",
    "description": "Filesystem-native context layer — generates and maintains CONTEXT.md manifests for AI agent codebase navigation",
    "tools": [
      {
        "name": "ctx_refresh",
        "description": "Regenerate stale CONTEXT.md manifests in a directory tree",
        "input_schema": { "type": "object", "properties": { "path": { "type": "string" } } },
        "output_schema": { "type": "object", "properties": { "status": {}, "dirs_processed": {}, "tokens_used": {}, "errors": {} } }
      },
      {
        "name": "ctx_check",
        "description": "Report manifest health: staleness, coverage, validity",
        "input_schema": { "type": "object", "properties": { "path": { "type": "string" } } }
      },
      {
        "name": "ctx_export",
        "description": "Concatenate CONTEXT.md files for a directory tree",
        "input_schema": { "type": "object", "properties": { "path": { "type": "string" }, "depth": { "type": "integer" } } }
      }
    ]
  }
  ```

- **Registry listings:** Register `ctx` on major MCP registries (Anthropic's MCP registry, community registries) so agents searching for "codebase context" or "code navigation" find it.

- **Claude Code / Cursor / Windsurf integration docs:** Specific instructions in `AGENTS.md` for how to add `ctx` as an MCP server in each major agent environment:
  ```json
  // Claude Code .mcp.json
  {
    "mcpServers": {
      "ctx": {
        "command": "ctx",
        "args": ["serve", "--mcp"],
        "description": "Codebase context manifests"
      }
    }
  }
  ```

**Files touched:** `server.py` (major rewrite or new `mcp_server.py`), new `mcp.json`, `AGENTS.md` (integration docs), `pyproject.toml` (optional MCP dependencies).

**Tests:** MCP tool registration tests. Input/output schema validation. Transport tests (stdio + HTTP).

**Definition of done:** An agent framework that supports MCP can discover and use `ctx` without any manual configuration beyond adding the server entry.

---

### Stage 6: Agent Workflow Patterns

**Goal:** Provide ready-made integration patterns so agents (and the humans directing them) can wire `ctx` into their existing workflows with minimal effort.

**What ships:**

#### Pattern 1: Session-End Hook
The agent runs `ctx refresh` at the end of every coding session, the same way it might run `git commit`.

```
# In an agent's system prompt or AGENTS.md:
"Before ending a session, run: ctx refresh . --output json"
```

Provide a copy-pasteable system prompt fragment.

#### Pattern 2: Pre-Commit Hook
Already exists (`.pre-commit-hooks.yaml`). Update to use new command names:
```yaml
- id: ctx-check
  name: ctx manifest freshness
  entry: ctx check . --output json
  language: python
  pass_filenames: false
```

#### Pattern 3: CI/CD Gate
Already exists (GitHub Action). Update to use new command surface:
```yaml
- name: Check manifests
  run: |
    pip install ctx-tool
    ctx check . --output json | jq '.stale == 0 and .missing == 0'
```

#### Pattern 4: PR Context Block
Agent appends a context summary to every PR description:
```bash
ctx export . --depth 1 --output json | jq -r '.manifests[].summary'
```

Provide a GitHub Actions workflow that auto-appends this.

#### Pattern 5: Agent-to-Agent Handoff
When one agent hands off to another (e.g., planning agent → coding agent → review agent), the incoming agent reads `ctx export` to get oriented:
```
1. ctx check . --output json    # Am I in a healthy repo?
2. ctx export . --depth 1       # What's the high-level structure?
3. ctx export src/ --depth 2    # Drill into the source tree
```

Document this as a "first 3 commands" pattern in `AGENTS.md`.

#### Pattern 6: Natural Language Trigger
The human says something like "update context" or "refresh manifests" and the agent maps it to `ctx refresh`. Document the natural-language aliases that agents should recognize:
- "update ctx" / "update context" / "refresh context" → `ctx refresh .`
- "check ctx" / "is context fresh" → `ctx check .`
- "show me the context" / "what's in this repo" → `ctx export . --depth 1`

This is documentation, not code — it goes in `AGENTS.md` as a mapping table agents can reference.

**Files touched:** `AGENTS.md` (patterns section), `.pre-commit-hooks.yaml` (update), `.github/workflows/` (update), new example workflow files.

**Tests:** Integration tests for each pattern (mock git hook, mock CI run).

**Definition of done:** A human can say "set up ctx for my project" and their agent has a clear, documented path to wire it in — regardless of whether the workflow is session-based, commit-based, or CI-based.

---

## Second-Order Changes (Post-Overhaul)

These are the ripple effects that need attention after the six stages ship.

### 1. Version Bump & Migration Guide

- Bump to `1.0.0` — this is the agent-first release and it's a meaningful milestone.
- Ship a `MIGRATION.md` that maps old commands to new ones.
- Keep hidden aliases for at least `1.x` lifecycle.
- Deprecation warnings in human output mode only.

### 2. Test Suite Restructure

The current 321 tests are organized around the old command surface. Post-overhaul:

- **Unit tests** stay (generator, hasher, parsers, config, manifest). No changes.
- **CLI tests** split into:
  - `test_api.py` — tests the unified API layer (the real interface)
  - `test_cli_json.py` — tests JSON output schemas for every operation
  - `test_cli_human.py` — tests human-formatted output (regression only)
  - `test_cli_compat.py` — tests that old command aliases still work
- **Integration tests** gain:
  - `test_mcp.py` — MCP tool registration, schema validation, transport
  - `test_agent_workflows.py` — end-to-end patterns (install → configure → refresh → check → export)
  - `test_zero_config.py` — fresh environment → auto-detect → refresh → verify

### 3. Dependency Audit

With the agent-first reframe, review whether all current dependencies are still justified:

| Dependency | Verdict | Notes |
|-----------|---------|-------|
| `click` | **Keep but encapsulate** | CLI framework stays, but the API layer shouldn't depend on it |
| `anthropic`, `openai` | **Keep** | Core LLM providers |
| `pyyaml` | **Keep** | Manifest serialization |
| `pathspec` | **Keep** | Ignore pattern matching |
| `fastapi`, `uvicorn` | **Evaluate** | If MCP server uses stdio transport, HTTP server may become optional. Consider making these optional deps. |
| `watchdog` | **Keep** | File watcher for `refresh --watch` |
| `tiktoken` | **Keep** | Token estimation |

Consider splitting into core and optional dependency groups:
```toml
[project.optional-dependencies]
serve = ["fastapi>=0.110.0", "uvicorn>=0.29.0"]
mcp = ["mcp>=1.0"]  # whatever the MCP SDK package is
dev = ["pytest>=8.0", "pytest-mock>=3.12"]
```

### 4. Error Taxonomy

Define a finite set of machine-readable error codes that agents can branch on:

| Code | Meaning | Agent Action |
|------|---------|-------------|
| `provider_not_configured` | No `.ctxconfig` and auto-detect failed | Set env vars or create `.ctxconfig` |
| `provider_unreachable` | Config exists but connectivity check failed | Check API key, network, proxy |
| `budget_exhausted` | Token budget reached before completion | Increase `token_budget` or run again |
| `partial_failure` | Some directories failed, others succeeded | Inspect `errors` array, retry |
| `no_manifests` | No CONTEXT.md files exist yet | Run `ctx refresh` |
| `stale_manifests` | Some manifests are out of date | Run `ctx refresh` |
| `invalid_manifests` | Frontmatter missing required fields | Run `ctx refresh --force` |
| `git_unavailable` | Git not installed or not a git repo | Non-fatal; mtime fallback used |

Every JSON error response includes `error_code` + `error_message` + optional `hint`.

### 5. Observability for Agents

Replace human-oriented observability (progress bars, cost estimates printed to terminal) with agent-oriented observability:

- **Structured logs:** When `CTX_LOG_FORMAT=json` is set, all log output is JSON lines. Agents can parse these for debugging.
- **Metrics in output:** Every operation's JSON response includes timing, token usage, and cache hit rate. No separate "stats" needed — it's embedded.
- **Event stream (future):** For long-running operations (`refresh` on a large repo), optionally emit newline-delimited JSON events so an agent can monitor progress without polling.

### 6. Security Model Documentation

Agents will install and run `ctx` in automated environments. Document the security model explicitly:

- `ctx` reads source files but never modifies them (only writes `CONTEXT.md` and `.ctx-cache/`)
- `ctx` sends file contents to LLM providers (document which providers, what data leaves the machine)
- `ctx serve` binds to localhost by default (document how to change, and why you probably shouldn't)
- `.ctxignore` can exclude sensitive directories from summarization
- Manifest frontmatter is injection-defended in prompts

This goes in `AGENTS.md` under a "Security" section.

### 7. Naming & Branding Reconsideration

With the agent-first pivot, consider whether the current naming is optimal for agent discovery:

- **Package name `ctx-tool`** — Fine for PyPI, but agents might search for "context" or "manifest." Ensure keywords cover these.
- **Command name `ctx`** — Short, memorable, good. No change.
- **`CONTEXT.md` filename** — This is the product's strongest discovery mechanism. Any agent that encounters a `CONTEXT.md` in a repo can read it and understand what generated it. The file itself is the advertisement. Consider adding a small footer to generated manifests:
  ```
  <!-- Generated by ctx (https://github.com/mschwar/context-project) — pip install ctx-tool -->
  ```

### 8. AGENTS.md as a Living Standard

Post-overhaul, `AGENTS.md` becomes the most important file in the repo — more important than the README. It should be:

- **Versioned** — include a `schema_version` so agents know which version of the contract they're reading
- **Self-describing** — the first line should tell an agent what this file is and why to read it
- **Stable** — changes to `AGENTS.md` should be treated like API changes (semver-aware, backwards-compatible)
- **Testable** — a CI check that validates `AGENTS.md` contains all required sections

### 9. Multi-Agent Coordination

As `ctx` becomes agent-operated, consider concurrency:

- Two agents running `ctx refresh` simultaneously on the same repo could conflict. The current file-level write model is last-write-wins. Consider:
  - A lockfile (`.ctx-cache/lock`) to serialize refreshes
  - Atomic manifest writes (write to temp, rename) — probably already safe on most filesystems, but document the guarantee

### 10. Telemetry & Feedback Loop (Optional, Opt-In)

If we want to improve prompt quality and manifest usefulness over time:

- Optional, opt-in telemetry that reports anonymized stats (languages detected, manifest count, average tokens per directory)
- No file contents, no source code, no manifest text — just aggregate numbers
- Disabled by default. Enabled via `CTX_TELEMETRY=true`.
- This is a "nice to have" — do not ship in the initial overhaul. Consider for `1.1.0`.

---

## Implementation Order & Dependencies

```
Stage 1 (Structured Output)
    ↓
Stage 2 (Unified API) ← depends on Stage 1 (API returns JSON)
    ↓
Stage 3 (Non-Interactive Config) ← depends on Stage 2 (auto-config in refresh path)
    ↓
Stage 4 (Agent Docs) ← depends on Stages 2–3 (documents the new surface)
    ↓
Stage 5 (MCP Native) ← depends on Stage 2 (MCP tools map to unified API)
    ↓
Stage 6 (Workflow Patterns) ← depends on Stages 2–5 (documents integration with new surface)
    ↓
Second-Order Changes (post-overhaul cleanup and hardening)
```

Stages 4 and 5 can run in parallel once Stage 3 is done.
Stage 6 can start as soon as Stage 2 is done (draft patterns) and finalize after Stage 5.

---

## Rough Effort Estimates

| Stage | Scope | Estimated Effort |
|-------|-------|-----------------|
| Stage 1 | Add `--output json` to all commands | Small — mostly CLI wiring |
| Stage 2 | Unified API + command consolidation | Medium — core restructure of `cli.py`, new `api.py` |
| Stage 3 | Auto-config + env var completeness | Small — config.py extensions |
| Stage 4 | Documentation rewrite | Medium — two major doc rewrites |
| Stage 5 | MCP server rewrite | Medium-Large — depends on MCP SDK maturity |
| Stage 6 | Workflow patterns + examples | Small — mostly documentation |
| Second-order | Test restructure, error taxonomy, etc. | Medium — spread across post-launch |

Total: ~4–6 phases of work at the current pace (each stage ≈ 1 phase).

---

## Success Criteria

The overhaul is complete when:

1. **An agent can install ctx in 1 command** with no interactive prompts.
2. **An agent can fully operate ctx** knowing only 4 commands, all with JSON output.
3. **An agent encountering ctx for the first time** can read `AGENTS.md` and be productive in under 30 seconds of processing time.
4. **ctx is discoverable** through MCP registries and package metadata searches for "codebase context."
5. **No human needs to read a README** to get ctx working — they just tell their agent to use it.
6. **All existing functionality is preserved** behind the new surface. Nothing is lost; it's re-skinned.
7. **The test suite validates the agent interface** as the primary contract, with human CLI tests as regression coverage.

---

## Open Questions

1. **MCP SDK maturity:** The MCP ecosystem is still early. Should we build a proper MCP server now, or ship a simpler JSON-over-stdio bridge and upgrade later? (Recommendation: ship stdio bridge first, upgrade when SDK stabilizes.)

2. **Command naming:** Is `ctx refresh` better than `ctx sync`? Is `ctx check` better than `ctx status`? We should pick names that feel natural when an agent (or human instructing an agent) says them aloud.

3. **Scope of Stage 2:** Do we actually remove the old commands in `1.0.0`, or just hide them? (Recommendation: hide them. Remove in `2.0.0`.)

4. **Agent framework partnerships:** Should we reach out to Claude Code, Cursor, Windsurf, Devin, etc. to get `ctx` into their default tool suggestions? This is a go-to-market question, not a technical one, but it affects how we prioritize Stage 5 vs. Stage 6.

5. **Manifest format evolution:** Should `CONTEXT.md` gain any new fields for the agent-first world? For example, a `navigation_hints` field that tells an agent "if you're looking for X, look in subdir Y"? (Recommendation: defer. The current format works. Iterate based on real agent feedback.)
