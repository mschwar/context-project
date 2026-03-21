# TODOS

## Run History Pruning

**What:** Add configurable retention policy to prune old run records from per-repo `run_stats.json`.

**Why:** The append-only ledger grows unbounded. A repo refreshed daily for a year accumulates ~365 records. While each record is small (~500 bytes), the file will eventually slow down `read_board()` and waste disk. More importantly, stale data from months ago has diminishing analytical value.

**Pros:**
- Prevents unbounded file growth
- Keeps `read_board()` fast regardless of repo age
- Reduces disk footprint for long-running repos

**Cons:**
- Adds complexity to the write path (prune after append)
- Needs a sensible default (e.g., 90 days or 500 runs) that works for most users
- Must not break global totals — global file tracks aggregates, not individual runs, so pruning per-repo is safe

**Context:** The current `record_run()` appends to a `runs` list with no cap. The pruning should happen inside `record_run()` after the append, trimming runs older than the retention window. The global file (`~/.ctx/run_stats.json`) stores only aggregated totals per repo, so it is unaffected by per-repo pruning. A reasonable default is 90 days or 500 records (whichever is more generous). The retention period could be configurable via `ctx.yaml` if needed, but a hardcoded default is fine for v1.

**Effort:** S (human: ~2 hours / CC: ~10 min)
**Priority:** P3 — not urgent, ledger is small per-record
**Depends on:** Nothing — can be done independently

## MCP Resources for .ctx/ Exports

**What:** Expose `.ctx/CONTEXT.md`, `.ctx/CONTEXT-1.md`, `.ctx/CONTEXT-0.md`, and `.ctx/metadata.json` as MCP resources (read-only URIs) alongside the existing MCP tools.

**Why:** MCP resources are the standard mechanism for agents to discover and read static data. The depth-tiered exports in `.ctx/` are perfect resource candidates — they're pre-compiled, read-only, and always available after `ctx init`. Exposing them as resources lets agents browse available context tiers without needing to call `ctx_export` as a tool.

**Pros:**
- Standard MCP integration pattern (resources for reads, tools for writes)
- Zero-cost for the agent — no tool call needed to read pre-compiled exports
- IDE agents (Claude Code, Cursor) can auto-discover context tiers

**Cons:**
- Adds ~50 lines to `mcp_server.py`
- Must handle missing `.ctx/` gracefully (not yet initialized)
- Resource URIs need a stable naming scheme

**Context:** The MCP server (`mcp_server.py`) currently only exposes tools. Resources are a separate MCP primitive for read-only data. The implementation would add resource handlers that read from `.ctx/` directory. Should check if `.ctx/` exists and return appropriate errors if not initialized.

**Effort:** S (human: ~3 hours / CC: ~15 min)
**Priority:** P2 — high value for agent integration, low effort
**Depends on:** ctx init (shipped in 1.1.0)

## ctx-sdk: Standalone Python Package for .ctx/ Consumers

**What:** Extract a lightweight `ctx-sdk` package that reads `.ctx/` exports without depending on the full `ctx-tool` CLI or LLM providers.

**Why:** SDK consumers (agents, IDE extensions, CI tools) only need to read the pre-compiled exports from `.ctx/`. They shouldn't need to install the full `ctx-tool` with its LLM dependencies just to read CONTEXT.md files. A thin SDK package would provide typed access to metadata.json, depth-tiered exports, and hook_log.json.

**Pros:**
- Minimal dependency footprint for consumers (no LLM libraries)
- Clean separation: `ctx-tool` writes, `ctx-sdk` reads
- Enables lightweight CI integration and IDE plugins

**Cons:**
- Another package to maintain and version
- Needs to stay in sync with `.ctx/` schema changes
- Small audience until `.ctx/` adoption grows

**Context:** The `.ctx/` directory uses a stable schema (metadata.json with schema_version field). The SDK would provide: `CtxProject.load(path)` to find and parse `.ctx/`, typed access to exports at each depth tier, and metadata introspection. Could live in this monorepo as a separate package or as a `ctx.sdk` submodule.

**Effort:** M (human: ~1 week / CC: ~30 min)
**Priority:** P3 — wait for `.ctx/` adoption before investing
**Depends on:** MCP Resources (above) for design alignment on resource naming
