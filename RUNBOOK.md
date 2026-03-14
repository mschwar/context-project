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
pytest
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

## LLM Disk Cache

`ctx` caches LLM summaries in `.ctx-cache/llm_cache.json` (relative to the project root). The cache key includes the model name, so switching models always produces a cache miss rather than serving stale summaries.

**Resetting the cache:** delete `.ctx-cache/llm_cache.json` (or the whole `.ctx-cache/` directory). The next `ctx update` will regenerate all summaries at normal token cost.

**After upgrading ctx** (or changing the `model` config key): all prior cache entries will be misses on the first run. This is intentional — the one-time regeneration cost is preferable to serving summaries from the wrong model.

**Disabling the cache:** set `cache_path: ""` in `.ctxconfig`.

## Common Failure Modes

### HTTP 400 Bad Request (Context Length)
**Symptom**: LLM returns 400 when processing a large directory.
**Fix**: The tool currently processes files in batches. If the batch or the resulting summaries exceed context limits, it may fail. Implementation of 400 context-length fallback is in the backlog.

### BitNet Subprocess Not Found
**Symptom**: `BitNetClient` fails because it can't find `run_inference.py`.
**Fix**: Ensure the `--base-url` points to the directory containing the BitNet scripts. This is a known issue on Windows.

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
