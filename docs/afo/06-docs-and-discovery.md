# AFO Spec 06 — Docs & Discovery

> **Status:** Canonical
> **Stage:** 4 (Agent Docs)
> **Prerequisites:** Read 00-conventions.md, 02-unified-api.md, 03-config-and-bootstrap.md

---

## 1. Overview

Rewrite AGENTS.md as the canonical agent onboarding document. Demote README.md to a brief human-facing pitch. Update PyPI metadata. Add a footer to every generated CONTEXT.md so agents encountering manifests in the wild can trace them back to ctx.

---

## 2. AGENTS.md Rewrite

### 2.1 Current State

AGENTS.md is ~353 lines covering mission, rules, workflow, SDLC bumper rails, and 23 phases of development history. Most of this content is for human contributors, not agent consumers.

### 2.2 Target State

AGENTS.md becomes a machine-readable onboarding contract for agents that **use** ctx (not agents that develop ctx). Development history moves to `state.md` / `archive/`.

### 2.3 Required Sections

The new AGENTS.md must contain exactly these sections in this order:

```markdown
# AGENTS

## schema_version
1

## What ctx Is
<2-3 sentences: what ctx does, what CONTEXT.md files are, why agents care>

## Install
<pip install ctx-tool, version, Python requirement>

## Configure
<.ctxconfig or env vars, zero-config path, budget guardrails>

## Commands
<4 canonical commands with JSON examples>

## Error Codes
<machine-readable error taxonomy from 00-conventions.md>

## Integration Patterns
<MCP server, CLI, env var bootstrap>

## Manifest Format
<frontmatter schema, body structure>

## Security
<prompt injection defences, path traversal protection>
```

### 2.4 Section Content Details

#### `schema_version`

```markdown
## schema_version
1
```

Agents can check this to detect breaking changes in the AGENTS.md format.

#### `What ctx Is`

```markdown
## What ctx Is

ctx generates `CONTEXT.md` manifest files for every directory in a codebase.
Each manifest contains a structured summary of the directory's files, subdirectories,
and purpose — produced by an LLM from source code analysis.
Agents read these manifests to navigate unfamiliar codebases without scanning every file.
```

#### `Install`

```markdown
## Install

```bash
pip install ctx-tool
```

- Requires Python 3.10+
- Current version: 0.8.0 (pre-1.0, API may change)
- For MCP IDE integration: no extra install needed
- For HTTP server: `pip install ctx-tool[serve]`
```

#### `Configure`

```markdown
## Configure

### Zero-config (recommended for agents)
Set your API key and output format:
```bash
export ANTHROPIC_API_KEY="sk-..."
export CTX_OUTPUT=json
```

### Config file (.ctxconfig)
```yaml
provider: anthropic
model: claude-haiku-4-5-20251001
max_tokens_per_run: 100000
max_usd_per_run: 1.00
```

### All environment variables
| Variable | Default | Description |
|----------|---------|-------------|
| `CTX_PROVIDER` | `anthropic` | LLM provider |
| `CTX_MODEL` | provider default | Model ID |
| `CTX_OUTPUT` | `human` | Output format (`human` or `json`) |
| `CTX_MAX_TOKENS_PER_RUN` | unlimited | Hard token budget |
| `CTX_MAX_USD_PER_RUN` | unlimited | Hard USD budget |
| `CTX_BASE_URL` | provider default | Custom API endpoint |
| `CTX_TOKEN_BUDGET` | unlimited | Per-run token budget |
| `CTX_CACHE_PATH` | `.ctx-cache/llm_cache.json` | Disk cache path |
```

#### `Commands`

For each of the 4 commands, include:
1. One-line description
2. Common flags
3. A complete JSON output example (copy-pasteable)

```markdown
## Commands

### ctx refresh <path>
Generate or update CONTEXT.md manifests.

Flags:
- `--force` — regenerate all, even fresh
- `--setup` — auto-detect provider and write .ctxconfig first
- `--watch` — refresh then watch for changes
- `--dry-run` — preview without changes
- `--output json` — structured JSON output

```bash
$ ctx refresh . --output json
```
```json
{
  "status": "success",
  "command": "refresh",
  "metadata": {"version": "0.8.0", "elapsed_ms": 4523, "tokens_used": 12400, "est_cost_usd": 0.037},
  "data": {"dirs_processed": 18, "dirs_skipped": 0, "files_processed": 64, "tokens_used": 12400, "errors_count": 0, "budget_exhausted": false, "strategy": "incremental"},
  "errors": [],
  "recommended_next": null
}
```

### ctx check <path>
Check manifest health, coverage, or changes.
< ... similar format for check, export, reset ... >
```

#### `Error Codes`

```markdown
## Error Codes

| Code | Meaning | Recommended Action |
|------|---------|-------------------|
| `provider_not_configured` | No LLM provider found | Set API key or run `ctx refresh --setup` |
| `provider_unreachable` | Network error | Check connectivity |
| `auth_failed` | Invalid API key | Rotate credentials |
| `budget_exhausted` | Token/USD limit hit | Increase budget or reduce scope |
| `lock_held` | Another ctx process running | Wait and retry |
| `partial_failure` | Some directories failed | Retry failed directories |
| `no_manifests` | No CONTEXT.md files found | Run `ctx refresh` first |
| `stale_manifests` | Manifests out of date | Run `ctx refresh` |
| `invalid_manifests` | Malformed CONTEXT.md | Run `ctx refresh --force` |
| `git_unavailable` | Git not installed | Install git or remove `--since` |
| `unknown_error` | Unclassified error | Check stderr or report bug |
```

#### `Integration Patterns`

```markdown
## Integration Patterns

### MCP Server (recommended for IDEs)
Add to your project's `.mcp.json`:
```json
{"mcpServers": {"ctx": {"command": "ctx", "args": ["serve", "--mcp"]}}}
```

### CLI with JSON output
```bash
export CTX_OUTPUT=json
ctx refresh .
ctx check .
ctx export .
```

### First 3 commands for a new codebase
```bash
ctx refresh .           # Generate all manifests
ctx check .             # Verify everything is healthy
ctx export . --depth 1  # Load top-level context
```
```

#### `Manifest Format`

```markdown
## Manifest Format

Each `CONTEXT.md` file contains YAML frontmatter and a Markdown body:

```yaml
---
generated: "2026-03-17T12:00:00Z"
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: "sha256:abc123..."
files: 12
dirs: 3
tokens_total: 48000
---
```

Body structure:
```markdown
# /path/to/directory
One-sentence purpose summary.

## Files
- **file.py** — summary

## Subdirectories
- **subdir/** — summary

## Notes
- optional agent hints
```
```

#### `Security`

```markdown
## Security

- All file names and contents are treated as untrusted data in LLM prompts.
- Path traversal protection on MCP server and HTTP server.
- API keys are never logged or included in output.
- Lock files prevent concurrent write corruption.
```

### 2.5 Where Existing Content Goes

| Current AGENTS.md Section | Destination |
|---------------------------|-------------|
| Mission | Condensed into "What ctx Is" |
| Current State | Remove (derivable from code) |
| Canonical Rules | Move to `CONTRIBUTING.md` |
| Required Behavior | Move to `CONTRIBUTING.md` |
| Workflow | Move to `CONTRIBUTING.md` |
| Git Hooks | Move to `CONTRIBUTING.md` |
| Definition of Done | Move to `CONTRIBUTING.md` |
| Escalation Rules | Move to `CONTRIBUTING.md` |
| SDLC Bumper Rails | Move to `CONTRIBUTING.md` |
| Gate Closeout | Move to `CONTRIBUTING.md` |
| Delegation & Intelligence Levels | Move to `CONTRIBUTING.md` |
| Model Routing | Move to `CONTRIBUTING.md` |
| Small-Model Guardrails | Move to `CONTRIBUTING.md` |
| Development Phases 1-23 | Move to `state.md` (already partially there) |

**Critical rule**: Do NOT delete phase history. Move it. The coding agent must verify the content exists in the destination before removing it from AGENTS.md.

---

## 3. README.md Demotion

### 3.1 Current State

README.md is ~100 lines with quick start, commands table, config example, local LLM notes.

### 3.2 Target State

README.md becomes ~40 lines: tagline, "tell your agent" one-liner, install, and a link to AGENTS.md.

### 3.3 Target Structure

```markdown
# ctx

Filesystem-native context layer for AI agents.

ctx generates `CONTEXT.md` manifests for every directory in your codebase,
giving AI agents structured navigation without scanning every file.

## Quick Start

```bash
pip install ctx-tool
export ANTHROPIC_API_KEY="sk-..."
ctx refresh .
```

## For Agents

See [AGENTS.md](AGENTS.md) for machine-readable onboarding, commands, error codes,
and integration patterns.

## MCP Integration

Add to your project's `.mcp.json`:
```json
{"mcpServers": {"ctx": {"command": "ctx", "args": ["serve", "--mcp"]}}}
```

## Documentation

- [AGENTS.md](AGENTS.md) — Agent onboarding contract
- [CONTRIBUTING.md](CONTRIBUTING.md) — Developer guide
- [architecture.md](architecture.md) — System design

## License

MIT
```

---

## 4. PyPI Metadata Updates

### 4.1 `pyproject.toml` Changes

```toml
[project]
name = "ctx-tool"
description = "Filesystem-native context layer for AI agents — generates CONTEXT.md manifests for codebase navigation"
keywords = [
    "ai",
    "agents",
    "context",
    "codebase",
    "navigation",
    "mcp",
    "llm",
    "documentation",
    "manifest",
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: Software Development :: Documentation",
    "Topic :: Utilities",
    "Environment :: Console",
    "Typing :: Typed",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
]
serve = [
    "fastapi>=0.110.0",
    "uvicorn>=0.29.0",
]
```

---

## 5. Manifest Footer

### 5.1 Purpose

When an agent encounters a `CONTEXT.md` in the wild (a repo it didn't set up), the footer tells it where the file came from and how to regenerate it.

### 5.2 Footer Content

Append to every generated CONTEXT.md body:

```markdown

<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
```

### 5.3 Implementation in `manifest.py`

Modify `write_manifest` to append the footer:

```python
MANIFEST_FOOTER = "\n<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->\n"

def write_manifest(...) -> None:
    # ... existing frontmatter + body assembly ...
    content = f"---\n{yaml_body}---\n{body}{MANIFEST_FOOTER}"
    # ... atomic write ...
```

### 5.4 Footer Rules

1. The footer is an HTML comment — invisible in rendered Markdown.
2. It appears on the last line of every CONTEXT.md.
3. `read_manifest` ignores it (it's after the frontmatter closing `---` and part of the body).
4. Content hash computation includes the body but NOT the footer. The footer is appended after hashing. This prevents the footer itself from making manifests appear stale when upgrading ctx versions.

**Important**: The footer is appended in `write_manifest`, **after** the body is passed in. The `body` parameter does NOT include the footer. The footer is a write-time decoration only.

---

## 6. Files

### Modified

| File | Changes |
|------|---------|
| `AGENTS.md` | Full rewrite to agent onboarding contract |
| `README.md` | Demotion to ~40-line pitch |
| `CONTRIBUTING.md` | Receives developer-facing content from old AGENTS.md |
| `pyproject.toml` | Keywords, classifiers, optional-dependency groups |
| `src/ctx/manifest.py` | Append `MANIFEST_FOOTER` in `write_manifest` |

---

## 7. Verification Checklist

1. New AGENTS.md has all 9 required sections in order.
2. `schema_version` is `1`.
3. Every JSON example in Commands is valid JSON (parseable by `json.loads`).
4. Every error code in the Error Codes table matches the taxonomy in 00-conventions.md.
5. Old AGENTS.md content for developers exists in CONTRIBUTING.md.
6. Phase history exists in state.md.
7. README.md is under 50 lines.
8. `pip install ctx-tool` still works (pyproject.toml is valid).
9. Generated CONTEXT.md files contain the footer comment.
10. Content hashes are NOT affected by the footer addition (no false staleness).
