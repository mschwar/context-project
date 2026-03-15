# Runbook

How to operate, validate, and develop `ctx`.

## Prerequisites

- Python 3.10+
- Git
- API Keys for LLM providers (Anthropic, OpenAI) set as environment variables.

Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running Validation

### Full Test Suite
Run the full pytest suite before every commit.
```bash
python -m pytest
```

### Type Checking (Future)
When type checking is fully implemented, run:
```bash
mypy src/ctx
```

## Using the CLI

### Initialize a project
Create initial manifests for a directory tree.
```bash
ctx init /path/to/project
```

### Update a project
Update stale manifests based on content changes.
```bash
ctx update /path/to/project
```

> **Before pushing:** always run `ctx update .` and commit the resulting `CONTEXT.md` changes alongside your code. The `CTX Manifest Check` CI job runs `ctx status . --check-exit-code` and will fail the PR if any manifests are stale.

### Check status
See how many manifests are stale or missing.
```bash
ctx status /path/to/project
```

### Verify manifests
Check CONTEXT.md frontmatter for required fields (generated, generator, model, content_hash, files, dirs, tokens_total).
```bash
ctx verify /path/to/project
```
Exit code 0 if all valid, exit code 1 if any invalid.

### Show stats
Show coverage summary across all directories.
```bash
ctx stats /path/to/project
ctx stats /path/to/project --verbose       # per-directory breakdown
ctx stats /path/to/project --format json   # machine-readable output
```

### Serve manifests
Serve manifests over HTTP.
```bash
ctx serve [PATH]
```

Serves manifests from the specified PATH (default: current directory). All manifest paths are resolved relative to this root.

## Publishing a Release

The publish workflow (`.github/workflows/publish.yml`) triggers on any `v*` tag and publishes to PyPI via OIDC trusted publishing.

**One-time setup (required before the first release):**
1. On PyPI: create a project named `ctx-tool`, go to Publishing → add a trusted publisher for `mschwar/context-project`, environment `pypi`, workflow `publish.yml`.
2. On GitHub: create an environment named `pypi` in repo Settings → Environments.

Once configured, publishing is as simple as:
```bash
git tag v0.8.0
git push --tags
```

> **Package name note:** `pip install ctx-tool` installs the `ctx` CLI command. The PyPI distribution name (`ctx-tool`) and the installed command name (`ctx`) are intentionally different — `ctx` was involved in a 2022 supply-chain incident on PyPI.

## Roadmap Gate Closeout

Every roadmap phase (gate) requires a formal closeout pass.
Follow the steps in [GATE_CLOSEOUT.md](./GATE_CLOSEOUT.md) before marking a phase as complete.

## Phase 16 Handoff

Phase 16 work is intentionally split into small gates for narrower models.

- Read [PHASE16_HANDOFF.md](./PHASE16_HANDOFF.md) before picking up any Phase 16 task.
- Use one gate per branch and one gate per PR.
- Keep the gate's file list, validation commands, and acceptance criteria in the working prompt.

## LLM Disk Cache

`ctx` caches LLM summaries in `.ctx-cache/llm_cache.json` (relative to the project root). The cache key includes the model name, so switching models always produces a cache miss rather than serving stale summaries.

**Resetting the cache:** delete `.ctx-cache/llm_cache.json` (or the whole `.ctx-cache/` directory). The next `ctx update` will regenerate all summaries at normal token cost.

**After upgrading ctx** (or changing the `model` config key): all prior cache entries will be misses on the first run. This is intentional — the one-time regeneration cost is preferable to serving summaries from the wrong model.

**Disabling the cache:** set `cache_path: ""` in `.ctxconfig`.

## Common Failure Modes

### `ctx status .` or `ctx update . --dry-run` fails on workspace cache directories
**Symptom**: A local workspace cache such as `.pytest_cache/` causes `PermissionError` during traversal.
**Fix**: Current default ignores skip `.pytest_cache/`, `.worktrees/`, and `.tmp/`. If a custom cache directory is still surfacing, add it to `.ctxignore`.

### Local Provider Still Hits Context Limits
**Symptom**: A local OpenAI-compatible provider still returns HTTP 400 on a large directory.
**Fix**: `ctx` already retries local providers with smaller fallbacks. If it still fails, lower `batch_size` or `max_file_tokens` in `.ctxconfig`.

### `pytest` Command Not Found
**Symptom**: `pytest` is missing from the shell.
**Fix**: Install the dev extras with `pip install -e ".[dev]"` and run tests with `python -m pytest`.

### Inconsistent Summary Styles
**Symptom**: Manifests have mixed summary lengths or tones.
**Fix**: Refine system prompts in `llm.py` to be more prescriptive about the output format.

## Development Tasks

### Adding an LLM Provider
1. Define a new client class in `llm.py` implementing the `LLMClient` protocol.
2. Update `config.py` to recognize the new provider.
3. Add tests in `tests/test_llm.py`.

### Modifying Manifest Format
1. Update the `Manifest` dataclass and parsing logic in `manifest.py`.
2. Update the `summarize_directory` prompt in `llm.py` to match the new format.
3. Update `architecture.md` to reflect the change.
