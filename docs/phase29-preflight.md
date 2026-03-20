# Phase 29 — Preflight Onboarding

> **Status:** Spec
> **Sprint:** 2 (Dogfooding, Analytics, Adoption)
> **Prerequisites:** None. This is the first phase of Sprint 2.
> **Tracking:** `state.md` under "Sprint 2"

---

## 1. Overview

Extend `ctx setup --check` from a lightweight connectivity probe into a comprehensive preflight gate that validates everything needed for a successful `ctx refresh` run. The goal is **fail fast with actionable messages** — a user (human or agent) should be able to run one command and know exactly what's wrong and how to fix it.

### What exists today

`ctx setup --check` currently:
1. Calls `detect_provider()` to find a provider from env vars or local port probes.
2. For cloud providers (anthropic, openai): calls `probe_provider_connectivity()` which hits the `/v1/models` endpoint.
3. For local providers (ollama, lmstudio): skips the probe entirely, returns success.
4. Reports "Connectivity: OK" or "Connectivity: FAILED" with proxy guidance.

### What's missing

- Local providers are not actually validated — `detect_provider` only checks if the port is open, not if a model can produce output.
- No check that the configured model returns substantive text (not empty/garbage).
- No check for `.ctxignore` presence or sanity.
- No check for git repo status.
- No check for disk write permissions on the target tree.
- No check for `.ctxconfig` existence or validity.
- The command is hidden (legacy alias) — it should be promoted if it's the onboarding entry point.

---

## 2. Design Principles

1. **Every check that fails must print exactly what to do to fix it.** No stack traces, no ambiguous errors.
2. **Checks run in dependency order.** If provider detection fails, don't attempt connectivity. If connectivity fails, don't attempt model quality.
3. **All checks are read-only.** Preflight never writes files, creates directories, or modifies config.
4. **JSON mode support.** All results flow through OutputBroker with machine-readable status.
5. **Exit code semantics.** Exit 0 = all checks pass. Exit 1 = one or more checks failed.

---

## 3. Preflight Checks (ordered)

### 3.1 Provider Detection

**What:** Can we find an LLM provider?

**How:** Call `detect_provider()` (already exists).

**Pass:** Returns `(provider, model_or_None)`.

**Fail message:**
```
[FAIL] Provider: no LLM provider detected.
  Fix: set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment,
       or start Ollama / LM Studio before running ctx.
```

**Short-circuit:** Yes. If this fails, skip all remaining checks.

### 3.2 Config Resolution

**What:** Can we load a valid configuration?

**How:** Call `load_config(target_path, require_api_key=True)` inside a try/except for `MissingApiKeyError` and `ValueError`.

**Pass:** Returns a valid `Config` object.

**Fail messages:**

Missing API key:
```
[FAIL] Config: {provider} provider detected but API key is missing.
  Fix: set {ENV_VAR_NAME} in your environment.
```

Invalid config file:
```
[FAIL] Config: .ctxconfig at {path} contains invalid YAML.
  Fix: check the file for syntax errors, or delete it and run `ctx setup` to regenerate.
```

**Short-circuit:** Yes on missing API key (can't proceed without it). No on config file issues — report and continue with remaining checks.

### 3.3 Provider Connectivity

**What:** Can we reach the provider's API?

**How:** Call `probe_provider_connectivity(provider, api_key, base_url)` (already exists). For local providers, make the existing port probe into a real `/v1/models` call that confirms at least one model is loaded.

**Pass:** Returns `(True, None)`.

**Fail messages:**

Cloud auth failure:
```
[FAIL] Connectivity: authentication failed (HTTP {code}) — API key is set but invalid.
  Fix: verify your {ENV_VAR_NAME} value is a valid, active key.
```

Cloud unreachable:
```
[FAIL] Connectivity: cannot reach {provider} API — {error}.
  Fix: check your internet connection.
```

Cloud unreachable with proxy:
```
[FAIL] Connectivity: cannot reach {provider} API — {error}.
  Fix: proxy env vars detected ({var_list}). A broken proxy may be blocking requests.
       Try unsetting: {platform_specific_unset_command}
```

Local provider — no models loaded:
```
[FAIL] Connectivity: {provider} is running but has no models loaded.
  Fix: pull a model first — e.g., `ollama pull llama3.2`
```

Local provider — port closed:
```
[FAIL] Connectivity: {provider} is not responding on {url}.
  Fix: start {provider} before running ctx.
```

**Short-circuit:** Yes. If connectivity fails, skip model quality check.

### 3.4 Model Response Quality

**What:** Does the configured model actually produce useful output?

**How:** Send a minimal single-file summarization request to the model and verify the response is non-empty and contains substantive text.

**Implementation:**

```python
def probe_model_quality(config: Config) -> tuple[bool, str | None]:
    """Send a sample file to the model and verify substantive output.

    Returns (True, None) on success or (False, error_message) on failure.
    """
```

1. Create a minimal LLM client via `create_client(config)`.
2. Call `client.summarize_files()` with a single synthetic test file:
   ```python
   test_file = {
       "path": "example.py",
       "content": "def hello():\n    return 'Hello, world!'",
       "language": "python",
       "metadata": {"functions": ["hello"]}
   }
   ```
3. Check the result:
   - If the call raises an exception: fail with the exception message.
   - If the result list is empty: fail.
   - If the first result's `summary` is empty, whitespace-only, or shorter than 5 characters: fail.
   - Otherwise: pass.

**Pass:** Model returned a substantive summary.

**Fail messages:**

Empty/garbage response:
```
[FAIL] Model quality: {model} returned an empty or unusable summary.
  Fix: try a different model. For local providers, ensure you're using a model
       with at least 7B parameters (e.g., llama3.2, mistral).
```

Model error:
```
[FAIL] Model quality: {model} returned an error — {error}.
  Fix: verify the model name is correct. Run `ollama list` or check your provider dashboard.
```

Timeout:
```
[FAIL] Model quality: {model} did not respond within 60 seconds.
  Fix: the model may be too large for your hardware, or the provider is overloaded.
       Try a smaller model or retry later.
```

**Short-circuit:** No. This is the last check in the dependency chain.

### 3.5 Target Directory Readiness

**What:** Is the target directory suitable for manifest generation?

**How:** Run these sub-checks independently (all run regardless of pass/fail):

**3.5a — Directory exists and is readable:**
```python
target = Path(path)
if not target.is_dir():
    fail("Target: {path} is not a directory or does not exist.")
```

**3.5b — Write permissions:**
```python
import tempfile
try:
    fd, tmp = tempfile.mkstemp(dir=target, prefix=".ctx-preflight-")
    os.close(fd)
    os.unlink(tmp)
except OSError as e:
    fail(f"Target: cannot write to {path} — {e}")
```

**3.5c — Git status (informational, not a blocker):**
```python
try:
    subprocess.run(["git", "rev-parse", "--git-dir"], cwd=target,
                   capture_output=True, check=True, timeout=5)
    git_available = True
except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
    git_available = False
```

Report:
```
[ OK ] Git: repository detected.
```
or:
```
[INFO] Git: not a git repository. ctx will use incremental refresh (mtime-based).
```

**3.5d — .ctxignore status (informational, not a blocker):**

Check if `.ctxignore` exists in the target directory.

Report:
```
[ OK ] Ignore: .ctxignore found at {path}.
```
or:
```
[INFO] Ignore: no .ctxignore found. Using built-in defaults.
       See: https://pypi.org/project/ctx-tool/ for customization.
```

**Short-circuit:** Only 3.5a (if the directory doesn't exist, skip 3.5b-d).

---

## 4. Output Format

### 4.1 Human Mode

Print each check result as it completes, using a consistent prefix:

```
ctx preflight — checking readiness for ctx refresh

[ OK ] Provider: anthropic (via ANTHROPIC_API_KEY)
[ OK ] Config: loaded from /path/to/.ctxconfig
[ OK ] Connectivity: anthropic API reachable
[ OK ] Model: claude-haiku-4-5-20251001 returned valid summary
[ OK ] Target: /path/to/repo is writable
[ OK ] Git: repository detected
[INFO] Ignore: no .ctxignore found. Using built-in defaults.

Ready to run: ctx refresh .
```

Failure example:
```
ctx preflight — checking readiness for ctx refresh

[ OK ] Provider: anthropic (via ANTHROPIC_API_KEY)
[FAIL] Config: anthropic provider detected but API key is missing.
  Fix: set ANTHROPIC_API_KEY in your environment.

Preflight failed. Fix the issues above and re-run: ctx setup --check
```

### 4.2 JSON Mode

OutputBroker envelope with command `"setup"`:

```json
{
  "status": "success",
  "command": "setup",
  "data": {
    "check_only": true,
    "checks": {
      "provider":     {"status": "ok", "detail": "anthropic (via ANTHROPIC_API_KEY)"},
      "config":       {"status": "ok", "detail": "loaded from /path/.ctxconfig"},
      "connectivity": {"status": "ok", "detail": "anthropic API reachable"},
      "model_quality":{"status": "ok", "detail": "claude-haiku-4-5-20251001 returned valid summary"},
      "target":       {"status": "ok", "detail": "/path/to/repo is writable"},
      "git":          {"status": "info", "detail": "not a git repository"},
      "ignore":       {"status": "info", "detail": "no .ctxignore found, using defaults"}
    },
    "ready": true,
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001"
  }
}
```

Failure:
```json
{
  "status": "error",
  "command": "setup",
  "data": {
    "check_only": true,
    "checks": {
      "provider":     {"status": "ok", "detail": "anthropic (via ANTHROPIC_API_KEY)"},
      "config":       {"status": "fail", "detail": "API key is missing", "fix": "set ANTHROPIC_API_KEY"}
    },
    "ready": false
  },
  "errors": [
    {"code": "preflight_failed", "message": "1 check failed", "hint": "ctx setup --check"}
  ]
}
```

Check status values: `"ok"`, `"fail"`, `"info"` (informational, not a blocker).

---

## 5. Implementation Plan

### 5.1 New function in `config.py`

```python
def probe_local_provider_models(base_url: str) -> tuple[bool, str | None, list[str]]:
    """Check if a local provider has models loaded.

    Returns (ok, error_or_None, model_list).
    """
```

This extracts the model-listing logic already in `detect_provider()` into a reusable function. `detect_provider` should be refactored to call this internally.

### 5.2 New function in `config.py`

```python
def probe_model_quality(config: Config) -> tuple[bool, str | None]:
    """Send a sample file to the model and verify substantive output.

    Returns (True, None) on success or (False, error_message) on failure.
    Uses create_client() to instantiate the appropriate client and calls
    summarize_files() with a single synthetic test file.

    Catches all exceptions and returns (False, error_description) rather
    than raising — preflight must never crash.
    """
```

**Important:** This function must import `create_client` from `llm.py` inside the function body to avoid circular imports (config.py is imported by llm.py). Alternatively, place this function in a new `preflight.py` module that imports from both `config.py` and `llm.py`.

### 5.3 New module: `src/ctx/preflight.py`

To avoid circular import issues and keep concerns clean, create a dedicated preflight module:

```python
"""Preflight checks for ctx setup --check.

Validates provider, config, connectivity, model quality, and target
directory readiness. Each check returns a PreflightCheck result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PreflightCheck:
    """Result of a single preflight check."""
    name: str           # "provider", "config", "connectivity", "model_quality", "target", "git", "ignore"
    status: str         # "ok", "fail", "info"
    detail: str         # human-readable description
    fix: str | None = None  # actionable fix instruction (only when status == "fail")


@dataclass
class PreflightResult:
    """Aggregate result of all preflight checks."""
    checks: list[PreflightCheck]
    ready: bool         # True if no check has status == "fail"
    provider: str | None = None
    model: str | None = None


def run_preflight(path: str = ".") -> PreflightResult:
    """Run all preflight checks in dependency order.

    Returns a PreflightResult with individual check results.
    Never raises — all errors are captured as failed checks.
    """
```

The `run_preflight` function executes checks 3.1 through 3.5 in order, respecting short-circuit rules. It returns a `PreflightResult` that the CLI and OutputBroker can render.

### 5.4 Modify `cli.py` setup command

Replace the current `--check` branch (lines 974-990 of `cli.py`) with a call to `run_preflight()`, then render results in human or JSON mode.

```python
if check_only:
    from ctx.preflight import run_preflight
    result = run_preflight(path)

    if not json_mode:
        click.echo("ctx preflight — checking readiness for ctx refresh\n")
        for check in result.checks:
            prefix = {"ok": "[ OK ]", "fail": "[FAIL]", "info": "[INFO]"}[check.status]
            label = check.name.replace("_", " ").title()
            click.echo(f"{prefix} {label}: {check.detail}")
            if check.fix:
                click.echo(f"  Fix: {check.fix}")
        click.echo()
        if result.ready:
            click.echo("Ready to run: ctx refresh .")
        else:
            click.echo("Preflight failed. Fix the issues above and re-run: ctx setup --check")

    broker.set_data({
        "check_only": True,
        "checks": {
            c.name: {"status": c.status, "detail": c.detail, **({"fix": c.fix} if c.fix else {})}
            for c in result.checks
        },
        "ready": result.ready,
        "provider": result.provider,
        "model": result.model,
    })
    if not result.ready and not json_mode:
        sys.exit(1)
    elif not result.ready:
        broker.add_error("preflight_failed", f"{sum(1 for c in result.checks if c.status == 'fail')} check(s) failed", hint="ctx setup --check")
    return
```

### 5.5 Do NOT change `_build_generation_runtime` or `api._build_generation_runtime`

The existing pre-flight connectivity check in the refresh path (`cli.py:122-129` and `api.py:124-127`) stays as-is. It's a fast, focused gate for the refresh command. The extended preflight in `setup --check` is a separate, comprehensive diagnostic tool. They serve different purposes:

- **Refresh pre-flight:** fast, blocks on connectivity only, runs every refresh.
- **Setup preflight:** comprehensive, runs all checks, runs on-demand.

---

## 6. Test Plan

All tests go in `tests/test_preflight.py` (new file).

### 6.1 Unit tests for `PreflightCheck` / `PreflightResult`

- `test_preflight_result_ready_when_all_ok` — all checks `"ok"` or `"info"` → `ready=True`.
- `test_preflight_result_not_ready_when_any_fail` — one `"fail"` check → `ready=False`.

### 6.2 Unit tests for `run_preflight`

All use `monkeypatch` and mocks — no real API calls.

- `test_preflight_no_provider_detected` — `detect_provider` returns None → provider check fails, remaining checks skipped.
- `test_preflight_cloud_provider_missing_api_key` — anthropic detected but no `ANTHROPIC_API_KEY` → config check fails, connectivity/model skipped.
- `test_preflight_cloud_connectivity_fail` — `probe_provider_connectivity` returns `(False, "HTTP 401")` → connectivity fails, model quality skipped.
- `test_preflight_cloud_all_pass` — everything mocked to succeed → all checks ok, `ready=True`.
- `test_preflight_local_provider_no_models` — ollama detected but `/v1/models` returns empty `data` list → connectivity fails with "no models loaded" message.
- `test_preflight_local_provider_all_pass` — ollama with model, quality check mocked to succeed → all ok.
- `test_preflight_model_quality_empty_response` — `summarize_files` returns empty summary → model quality fails.
- `test_preflight_model_quality_timeout` — `summarize_files` raises `TimeoutError` → model quality fails with timeout message.
- `test_preflight_target_not_a_directory` — path doesn't exist → target check fails.
- `test_preflight_target_not_writable` — `mkstemp` raises `OSError` → target check fails.
- `test_preflight_no_git_repo` — `git rev-parse` fails → git check is `"info"`, not `"fail"`.
- `test_preflight_no_ctxignore` — no `.ctxignore` in target → ignore check is `"info"`.
- `test_preflight_has_ctxignore` — `.ctxignore` exists → ignore check is `"ok"`.

### 6.3 CLI integration tests

- `test_setup_check_all_pass_human_mode` — invoke `ctx setup --check {path}`, mock all checks to pass. Verify output contains `[ OK ]` lines and "Ready to run".
- `test_setup_check_fail_human_mode` — invoke with provider detection mocked to fail. Verify output contains `[FAIL]` and exit code 1.
- `test_setup_check_all_pass_json_mode` — invoke with `--output json`. Parse JSON, verify `data.ready == true` and all check statuses.
- `test_setup_check_fail_json_mode` — invoke with connectivity failure. Parse JSON, verify `data.ready == false` and `errors` array populated.
- `test_setup_check_backward_compatible` — verify the existing `setup --check` behavior (provider detection + connectivity) still works for scripts that parse the current output. *Note: the output format is changing, so this test documents the new contract rather than preserving the old one.*

### 6.4 Test count estimate

13 unit tests + 5 CLI tests = **18 new tests**.

---

## 7. File Change Summary

| File | Change |
|------|--------|
| `src/ctx/preflight.py` | **New.** `PreflightCheck`, `PreflightResult`, `run_preflight()`, `probe_model_quality()`, `probe_local_provider_models()`. |
| `src/ctx/config.py` | Minor refactor: extract model-listing from `detect_provider()` into `probe_local_provider_models()` that preflight can reuse. Or: preflight.py reimplements the local model check independently (simpler, avoids touching stable code). |
| `src/ctx/cli.py` | Replace `setup --check` branch (lines 974-990) with `run_preflight()` call and structured output rendering. |
| `tests/test_preflight.py` | **New.** 18 tests per section 6. |
| `state.md` | Mark Phase 29 deliverables as complete. |

---

## 8. Boundaries

### In scope
- All checks described in section 3.
- Human and JSON output modes.
- New `preflight.py` module.
- New `test_preflight.py` test file.
- Updating `setup --check` CLI path.

### Out of scope
- Changing the refresh-path pre-flight check (`cli.py:122-129`, `api.py:124-127`). That stays as-is.
- Making `setup` a non-hidden command. That's a separate decision.
- Writing or modifying `.ctxconfig` files. Preflight is read-only.
- Phase 26 local model compatibility matrix. The model quality check here is a binary go/no-go, not a quality rating.
- Any changes to the core engine (generator.py, llm.py internals, parsers).

---

## 9. Acceptance Criteria

1. `ctx setup --check .` runs all 7 checks and reports pass/fail/info for each.
2. Exit code 0 when all checks pass, exit code 1 when any check fails.
3. Every `[FAIL]` line includes a `Fix:` instruction.
4. `--output json` produces the envelope described in section 4.2.
5. Model quality check sends exactly one LLM call with a synthetic test file.
6. Local providers (ollama, lmstudio) are actually validated — not silently skipped.
7. All 18 tests pass.
8. No changes to `generator.py`, `llm.py` internals, or parser modules.
9. Existing `ctx refresh` pre-flight behavior is unchanged.
