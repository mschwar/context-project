# AGENTS

## schema_version
1

## What ctx Is
`ctx` generates `CONTEXT.md` manifests for every directory in a codebase.
Each manifest stores YAML frontmatter plus a Markdown summary of files, subdirectories, and purpose so agents can navigate without opening every file.
Use `ctx refresh` to keep manifests fresh, `ctx check` to validate them, `ctx export` to ingest them, and `ctx reset` to remove them.

## Install
```bash
pip install ctx-tool
```

- Requires Python 3.10+
- Current CLI command: `ctx`
- Current release line: `0.8.0`
- Machine-readable mode: set `CTX_OUTPUT=json` or pass `--output json`

## Configure
### Zero-config

- Cloud providers: export `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, then run `ctx refresh .`
- Local providers: run `ctx refresh . --setup` to detect Ollama or LM Studio and write `.ctxconfig`
- Explicit provider selection: set `CTX_PROVIDER` or write `.ctxconfig`

### `.ctxconfig`

```yaml
provider: anthropic
model: claude-haiku-4-5-20251001
max_tokens_per_run: 100000
max_usd_per_run: 1.00
cache_path: .ctx-cache/llm_cache.json
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | unset | Anthropic credential |
| `OPENAI_API_KEY` | unset | OpenAI credential or local OpenAI-compatible placeholder |
| `CTX_OUTPUT` | `human` | Output mode: `human` or `json` |
| `CTX_PROVIDER` | inferred or `anthropic` | Provider override |
| `CTX_MODEL` | provider default | Model override |
| `CTX_BASE_URL` | provider default | Custom API base URL |
| `CTX_MAX_FILE_TOKENS` | `8000` | Per-file truncation cap before summarization |
| `CTX_MAX_DEPTH` | unlimited | Directory traversal depth cap |
| `CTX_TOKEN_BUDGET` | unlimited | Generator token budget |
| `CTX_MAX_TOKENS_PER_RUN` | unlimited | Hard token guardrail |
| `CTX_MAX_USD_PER_RUN` | unlimited | Hard spend guardrail |
| `CTX_BATCH_SIZE` | unlimited | Files per LLM call |
| `CTX_CACHE_PATH` | `.ctx-cache/llm_cache.json` | Disk cache location |
| `CTX_MAX_CACHE_ENTRIES` | `10000` | Cache entry cap |
| `CTX_WATCH_DEBOUNCE` | `0.5` | Watch debounce seconds |
| `CTX_EXTENSIONS` | all text files | Comma-separated extension allowlist |

## Commands
### `ctx refresh <path>`

Generate or update `CONTEXT.md` manifests using the fastest valid strategy for the tree.

Common flags:
- `--force` — regenerate every directory
- `--setup` — detect provider and write `.ctxconfig` before refreshing
- `--watch` — refresh once, then watch for changes
- `--dry-run` — report stale directories without writing
- `--output json` — emit the JSON envelope only

```json
{
  "status": "success",
  "command": "refresh",
  "metadata": {
    "version": "0.8.0",
    "elapsed_ms": 4523,
    "tokens_used": 12400,
    "est_cost_usd": 0.037
  },
  "data": {
    "dirs_processed": 18,
    "dirs_skipped": 0,
    "files_processed": 64,
    "tokens_used": 12400,
    "errors": [],
    "budget_exhausted": false,
    "strategy": "incremental",
    "est_cost_usd": 0.037,
    "stale_directories": [],
    "budget_guardrail": null,
    "config_written": false,
    "setup_provider": null,
    "setup_model": null,
    "setup_detected_via": null
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx check <path>`

Report manifest health, validation results, coverage stats, or manifest diffs.

Common flags:
- `--verify` — validate frontmatter, freshness, and coverage
- `--stats` — emit aggregate coverage statistics
- `--diff` — compare manifest changes via git or mtime fallback
- `--check-exit` — exit `1` when health checks find issues
- `--since <ref>` — git diff base for `--diff`
- `--quiet` / `--stat` — diff-only output shaping
- `--output json` — emit the JSON envelope only

```json
{
  "status": "success",
  "command": "check",
  "metadata": {
    "version": "0.8.0",
    "elapsed_ms": 93,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "mode": "health",
    "directories": [
      {
        "path": ".",
        "status": "fresh"
      },
      {
        "path": "src",
        "status": "fresh"
      }
    ],
    "summary": {
      "fresh": 20,
      "stale": 0,
      "missing": 0
    }
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx export <path>`

Concatenate generated manifests for agent ingestion.

Common flags:
- `--filter all|stale|missing` — select which manifests to export
- `--depth <n>` — limit traversal depth
- `--output <file>` — write export text to a file in human mode
- `--output json` — emit the JSON envelope only

```json
{
  "status": "success",
  "command": "export",
  "metadata": {
    "version": "0.8.0",
    "elapsed_ms": 41,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "manifests_exported": 3,
    "filter": "all",
    "depth": 1,
    "content": "# CONTEXT.md\n\n---\ngenerated: \"2026-03-18T19:00:00Z\"\n"
  },
  "errors": [],
  "recommended_next": null
}
```

### `ctx reset <path>`

Remove generated manifests from a tree.

Common flags:
- `--yes` — required for non-interactive deletion
- `--dry-run` — preview manifest removals
- `--output json` — emit the JSON envelope only

```json
{
  "status": "success",
  "command": "reset",
  "metadata": {
    "version": "0.8.0",
    "elapsed_ms": 18,
    "tokens_used": 0,
    "est_cost_usd": 0.0
  },
  "data": {
    "manifests_removed": 3,
    "paths": [
      "CONTEXT.md",
      "src/CONTEXT.md",
      "src/ctx/CONTEXT.md"
    ]
  },
  "errors": [],
  "recommended_next": null
}
```

## Error Codes
| Code | Meaning | Recommended Action |
|------|---------|-------------------|
| `provider_not_configured` | No provider configuration resolved | Set API keys, `CTX_PROVIDER`, or run `ctx refresh . --setup` |
| `provider_unreachable` | Provider endpoint could not be reached | Check connectivity, proxy settings, or local provider status |
| `auth_failed` | Provider rejected credentials | Rotate or replace credentials |
| `budget_exhausted` | Hard token or USD guardrail stopped the run | Raise the guardrail or reduce scope |
| `lock_held` | Another `ctx` write operation owns the lock | Wait and retry |
| `partial_failure` | Some directories failed while others succeeded | Retry after inspecting reported errors |
| `no_manifests` | No manifests exist in the target tree | Run `ctx refresh .` |
| `stale_manifests` | Existing manifests are out of date | Run `ctx refresh .` |
| `invalid_manifests` | Manifest validation found malformed entries | Run `ctx refresh . --force` |
| `git_unavailable` | A git-dependent path could not use git | Install git or remove the git-specific flag |
| `unknown_error` | Unclassified failure | Inspect the error message and retry or report a bug |

## Integration Patterns
### Session Bootstrap

```bash
export CTX_OUTPUT=json
export ANTHROPIC_API_KEY="sk-..."
ctx refresh .
ctx check . --check-exit --output json
ctx export . --depth 1 --output json
```

### CI Freshness Gate

```bash
ctx check . --check-exit
```

### Pre-commit Hook

```yaml
repos:
  - repo: https://github.com/mschwar/context-project
    rev: v0.8.0
    hooks:
      - id: ctx-check
```

### HTTP Manifest Server

```bash
ctx serve .
```

Fetch `GET /mcp/context/<directory>` relative to the served root to retrieve raw manifest content.

## Manifest Format
Each generated `CONTEXT.md` contains YAML frontmatter followed by a Markdown body.

```yaml
---
generated: "2026-03-18T19:00:00Z"
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: "sha256:abc123..."
files: 12
dirs: 3
tokens_total: 48000
---
```

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

Generated files end with this footer comment:

```markdown
<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->
```

## Security
- Treat file names, file contents, and existing manifests as untrusted input when prompting an LLM.
- `ctx serve` resolves requested paths against the explicit served root and rejects traversal outside that root.
- API keys are loaded from environment variables and are not written to manifests or JSON envelopes.
- `CONTEXT.md` files and `.ctx-cache/` are excluded from source summarization to avoid self-ingestion loops.
- Write operations use a lock file and atomic manifest replacement to avoid concurrent corruption.
