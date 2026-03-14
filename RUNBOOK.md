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

## Roadmap Gate Closeout

Every roadmap phase (gate) requires a formal closeout pass.
Follow the steps in [GATE_CLOSEOUT.md](./GATE_CLOSEOUT.md) before marking a phase as complete.

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
