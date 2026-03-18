# AFO Spec 00 — Conventions

> **Status:** Canonical
> **Audience:** Every coding agent (read this first before any stage spec)
> **Scope:** JSON envelope, error taxonomy, exit codes, testing patterns, backwards compatibility

---

## 1. JSON Envelope Schema

Every command, in `--output json` mode, emits **exactly one** JSON object to stdout. No other output reaches stdout or stderr.

```json
{
  "status": "success | error | partial",
  "command": "refresh | check | export | reset",
  "metadata": {
    "version": "0.8.0",
    "elapsed_ms": 1234,
    "tokens_used": 4800,
    "est_cost_usd": 0.014
  },
  "data": { },
  "errors": [
    {
      "code": "provider_unreachable",
      "message": "Connection error: timeout after 10s",
      "hint": "Check your network or run `ctx setup --check`.",
      "path": null
    }
  ],
  "recommended_next": "ctx check . --output json"
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `"success" \| "error" \| "partial"` | Yes | Overall outcome. `partial` means some directories succeeded, some failed. |
| `command` | `string` | Yes | The canonical command name that ran (`refresh`, `check`, `export`, `reset`). |
| `metadata.version` | `string` | Yes | `ctx.__version__` at invocation time. |
| `metadata.elapsed_ms` | `int` | Yes | Wall-clock milliseconds from command start to envelope emission. |
| `metadata.tokens_used` | `int` | Yes | Total LLM tokens consumed. `0` for read-only commands. |
| `metadata.est_cost_usd` | `float` | Yes | Estimated USD cost. `0.0` for read-only or local providers. |
| `data` | `object` | Yes | Command-specific payload. Schema varies per command (see 01-output-broker.md). Empty `{}` on total failure. |
| `errors` | `array` | Yes | List of error objects. Empty `[]` on success. |
| `errors[].code` | `string` | Yes | Machine-readable error code from the taxonomy below. |
| `errors[].message` | `string` | Yes | Human-readable explanation. |
| `errors[].hint` | `string \| null` | Yes | Suggested remediation, or `null` if none. |
| `errors[].path` | `string \| null` | Yes | Filesystem path relevant to this error, or `null`. |
| `recommended_next` | `string \| null` | Yes | A suggested next command, or `null` if no obvious follow-up. |

### Rules

1. The envelope is always valid JSON. Even on crash, the global exception handler emits a valid envelope with `status: "error"`.
2. `data` is never `null` — use `{}` when there is no payload.
3. `errors` is never `null` — use `[]` when there are no errors.
4. `metadata.tokens_used` and `metadata.est_cost_usd` are `0` / `0.0` for commands that don't call an LLM.
5. `recommended_next` is `null` when the command succeeded with nothing further needed.

---

## 2. Error Taxonomy

These are the machine-readable error codes used in `errors[].code`. Each code maps to a specific failure class. Agents use these codes for programmatic decision-making.

| Code | Meaning | Typical Trigger |
|------|---------|-----------------|
| `provider_not_configured` | No LLM provider detected or configured. | Missing API key, no `.ctxconfig`, no local provider running. |
| `provider_unreachable` | Provider detected but network call failed. | Timeout, DNS failure, proxy misconfiguration. |
| `auth_failed` | Provider rejected the credentials. | Invalid or expired API key. |
| `budget_exhausted` | Token or USD budget limit reached. | `max_tokens_per_run` or `max_usd_per_run` exceeded. |
| `lock_held` | Another ctx process holds the write lock. | Concurrent `ctx refresh` or `ctx reset`. |
| `partial_failure` | Some directories succeeded, others failed. | Transient LLM errors on a subset of dirs. |
| `no_manifests` | No CONTEXT.md files found in the target tree. | Running `check` or `export` on a fresh repo. |
| `stale_manifests` | Manifests exist but are out of date. | Content changed since last generation. |
| `invalid_manifests` | Manifests have malformed or missing fields. | Hand-edited or corrupted CONTEXT.md files. |
| `git_unavailable` | A git-dependent feature was requested but git is missing. | `--since` flag without git installed. |
| `unknown_error` | Unclassified exception. | Bug, unexpected filesystem error. |

### Error Code Selection Rules

1. Use the **most specific** code that matches. `provider_unreachable` over `unknown_error`.
2. Multiple errors can appear in a single response (e.g., `partial_failure` + per-directory errors).
3. When `status` is `"partial"`, at least one error with code `partial_failure` must be present.
4. `unknown_error` is the fallback. If you catch an exception and can't classify it, use this.

---

## 3. Exit Codes

| Code | Meaning | JSON `status` |
|------|---------|---------------|
| `0` | Success. All requested work completed. | `"success"` |
| `1` | Failure. Command could not complete, or health check found issues. | `"error"` |
| `2` | Partial success. Some work completed, some failed. | `"partial"` |

### Rules

1. Exit codes apply in **both** human and JSON mode. Agents should check exit codes before parsing JSON.
2. `check` exits `1` when stale/missing/invalid manifests are found (this is not an error — it's the expected check result).
3. `export` always exits `0` unless a filesystem error prevents reading.
4. `reset` exits `0` on success, `1` if the lock cannot be acquired.

---

## 4. Output Mode Rules

ctx supports two output modes: **human** (default) and **json** (`--output json` or `CTX_OUTPUT=json`).

### Human Mode (default)

- Colored text, progress bars, multi-line tables — the current behavior.
- Warnings and tips printed to stderr.
- `--format json` on `diff`/`stats`/`verify` continues to emit bare JSON (no envelope).

### JSON Mode (`--output json`)

1. **stdout**: Exactly one JSON envelope object. Nothing else.
2. **stderr**: Silent. No progress, no tips, no warnings, no color codes.
3. **No interactive prompts**: Any command that would prompt (e.g., `clean` without `--yes`) must either auto-proceed or fail with an error code. See 03-config-and-bootstrap.md.
4. **Progress callbacks**: Suppressed entirely. The `_progress_callback` function must not emit when JSON mode is active.
5. **`click.echo` calls**: All ~40 existing `click.echo` calls in `cli.py` are intercepted by the OutputBroker (see 01-output-broker.md). They do not reach stdout in JSON mode.
6. **Existing `--format json`**: When `--output json` is active on a command that also has `--format json`, the bare JSON from `--format json` becomes the `data` field inside the envelope. `--format json` is ignored as a separate flag — the envelope always wraps it.
7. **`CTX_OUTPUT` env var**: When set to `json`, behaves identically to `--output json`. CLI flag takes precedence over env var.

### Detection Priority

```
--output json (CLI flag)  >  CTX_OUTPUT=json (env var)  >  default (human)
```

---

## 5. Testing Conventions

### General

- All tests use `pytest` with `click.testing.CliRunner`.
- Use `monkeypatch` for environment variables and config overrides.
- Tests must pass on both Windows and POSIX (use `pathlib.Path`, not string concatenation).
- No test may make real LLM calls. Mock at the `LLMClient` protocol boundary.

### JSON Mode Tests

- New JSON tests go in dedicated test files (e.g., `test_output.py`, `test_cli_json.py`) — not mixed into existing `test_cli.py`.
- Every JSON test must validate the envelope structure:
  ```python
  import json
  result = runner.invoke(cli, ["check", ".", "--output", "json"])
  envelope = json.loads(result.output)
  assert "status" in envelope
  assert "command" in envelope
  assert "metadata" in envelope
  assert "data" in envelope
  assert "errors" in envelope
  assert isinstance(envelope["errors"], list)
  ```
- Test both `status: "success"` and `status: "error"` paths for every command.
- Verify that `result.output` contains **only** the JSON envelope (no extra lines).

### Backwards Compatibility Tests

- After command collapse (Stage 2), every old command must still work via hidden alias.
- Alias tests go in `tests/test_cli_compat.py`.
- Each alias test invokes the old command name and verifies it produces the same result as the new canonical command.

### Test File Naming

| Test File | Scope |
|-----------|-------|
| `tests/test_output.py` | OutputBroker unit tests |
| `tests/test_api.py` | `api.py` function tests |
| `tests/test_lock.py` | `lock.py` concurrency tests |
| `tests/test_cli_compat.py` | Hidden alias regression tests |
| `tests/test_mcp_server.py` | MCP stdio server tests |
| `tests/test_cli.py` | Existing tests — do not modify unless a test breaks due to a legitimate behavior change |

---

## 6. Backwards Compatibility Contract

### Hidden Aliases

When commands are renamed or collapsed in Stage 2, the old names become hidden Click commands:

```python
@cli.command(hidden=True)
def init(...):
    """Deprecated: use `ctx refresh --force` instead."""
    # emit deprecation warning in human mode only
    # delegate to the new command
```

### Rules

1. **Human mode only**: Old commands print a one-line deprecation warning to stderr: `"Warning: 'ctx init' is deprecated. Use 'ctx refresh' instead."`.
2. **JSON mode**: No deprecation warning. The old command works identically to the new one. Agents must never see deprecation noise.
3. **Removal timeline**: Hidden aliases remain through all 0.x releases. They are removed in 2.0.0 (not 1.0.0).
4. **No behavioral difference**: An aliased command must produce byte-identical output to its replacement (given identical inputs).
5. **Exit codes**: Aliases use the same exit code contract as the canonical command.

### Command Mapping (Preview)

Full mapping is defined in 02-unified-api.md. Summary:

| Old Command | New Command |
|-------------|-------------|
| `ctx init .` | `ctx refresh . --force` |
| `ctx init . --no-overwrite` | `ctx refresh .` |
| `ctx update .` | `ctx refresh .` |
| `ctx smart-update .` | `ctx refresh .` (auto-detects git) |
| `ctx status .` | `ctx check .` |
| `ctx verify .` | `ctx check . --verify` |
| `ctx stats .` | `ctx check . --stats` |
| `ctx diff .` | `ctx check . --diff` |
| `ctx export .` | `ctx export .` (unchanged) |
| `ctx clean .` | `ctx reset .` |
| `ctx setup` | `ctx refresh . --setup` |
| `ctx watch .` | `ctx refresh . --watch` |

---

## 7. Version Policy

- Version stays at `0.8.0` through all 6 stages.
- Version bumps to `1.0.0` **only** after all stages land and the verification checklist passes.
- The `__version__` string in `src/ctx/__init__.py` is the single source of truth.
- `metadata.version` in the JSON envelope reads from `__version__`.

---

## 8. File Conventions

### New Files

- All new Python modules go under `src/ctx/`.
- All new test files go under `tests/`.
- Use `from __future__ import annotations` in every new file.
- Follow existing patterns: `@dataclass` for data structures, `pathlib.Path` for all paths, type hints on all public functions.

### Modified Files

- When modifying `cli.py`, preserve the existing function order where possible.
- Never remove existing public functions from `generator.py` — `api.py` wraps them.
- When adding to `config.py`, follow the existing `load_config` overlay pattern (file → env var → CLI flag).

### Import Style

```python
# Standard library
from __future__ import annotations
import os
import sys

# Third-party
import click

# Local
from ctx import __version__
from ctx.config import Config, load_config
```
