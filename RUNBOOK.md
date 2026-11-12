# Runbook

Operational guide for running, validating, serving, and releasing `ctx`. Give `ctx` a repository path; it parses source files locally with zero API keys or language model calls and writes tiered maps under `.ctx/`.

## Prerequisites

- Python 3.10 or newer
- Git (required by `ctx init` when checking repository boundaries)

Install the package and test tools in editable mode:

```bash
pip install -e ".[dev]"
```

## Validation Commands

Run the unit test suite, documentation hygiene gate, and structural self-check before opening or merging a pull request:

```bash
python -m pytest
python3 -m unittest tests/test_doc_hygiene.py -v
CTX_OUTPUT=json python -m ctx init .
CTX_OUTPUT=json python -m ctx check . --verify --check-exit
CTX_OUTPUT=json python -m ctx uninit .
```

## CLI Operations

### Initialize and Refresh `.ctx/` Maps
Create gitignored `.ctx/` tiered maps (`CONTEXT-0.md`, `CONTEXT-1.md`, `CONTEXT.md`, and `metadata.json`) and update them when signatures or governance docs change:

```bash
ctx init /path/to/project
ctx refresh /path/to/project
ctx refresh /path/to/project --force
ctx refresh /path/to/project --dry-run
```

Remove `.ctx/` and strip any legacy `ctx` git hook markers when finished:

```bash
ctx uninit /path/to/project
```

### Check Freshness, Verification, and Token Stats
Inspect whether `.ctx/` maps match current source hashes, validate frontmatter and tier files, or report estimated token counts:

```bash
ctx check /path/to/project
ctx check /path/to/project --verify --check-exit
ctx check /path/to/project --diff --stat
ctx check /path/to/project --stats --verbose
ctx check /path/to/project --stats --output json
```

Exit code `0` indicates fresh, valid maps; exit code `1` indicates stale, missing, or malformed `.ctx/` files under `--verify` or `--check-exit`.

### Export Maps and Fleet Capsules
Render `.ctx/` maps to standard output on demand (even without running `ctx init` first) or emit a JSON fleet capsule for `project-ledger` and `gbrain`:

```bash
ctx export /path/to/project --depth 0
ctx export /path/to/project --depth 1
ctx export /path/to/project --capsule --out-file capsule.json
```

### Trace Reverse-Dependency Blast Radius
Compute direct and transitive reverse dependents, coupled test files, affected operational surfaces, and governing docs for a file, directory, or symbol:

```bash
ctx impact src/ctx/skeleton.py /path/to/project
ctx impact src/ctx/skeleton.py /path/to/project --depth 2 --output json
```

### Clean Up Legacy Sidecars
Delete retired per-directory `CONTEXT.md` files from older `ctx` releases without touching `.ctx/`:

```bash
ctx reset /path/to/project --dry-run
ctx reset /path/to/project --yes
```

### Run the Model Context Protocol (MCP) or HTTP Server
Expose `ctx` tools and read-only `ctx://.ctx/*` resources over standard input/output for MCP clients, or serve `.ctx/` exports over HTTP:

```bash
ctx serve --mcp /path/to/project
ctx serve /path/to/project
```

Both servers resolve paths relative to the served root directory and reject `..` traversal. Install FastAPI and Uvicorn extras if HTTP mode is needed:

```bash
pip install "ctx-tool[serve]"
```

### Reproduce the Navigation Benchmark
Run the deterministic Phase 27.1 A/B/C static-oracle benchmark across one or more repositories:

```bash
ctx benchmark /path/to/project --out-file docs/benchmarks/phase27-1-navigation-benchmark.md
```

## Publishing a Release

The release workflow (`.github/workflows/publish.yml`) runs on `v*` tags and publishes to the Python Package Index (PyPI) via OpenID Connect (OIDC) trusted publishing.

1. On PyPI, configure project `ctx-tool` with a trusted publisher for `mschwar/context-project`, environment `pypi`, and workflow `publish.yml`.
2. On GitHub, ensure the `pypi` environment exists under repository Settings -> Environments.
3. Tag and push the release:

```bash
git tag v1.1.0
git push --tags
```

> **Package name note:** `pip install ctx-tool` installs the `ctx` CLI command. The PyPI distribution name (`ctx-tool`) differs from the command name (`ctx`) because the bare `ctx` package on PyPI had a 2022 supply-chain incident.

## Roadmap Closeouts and Archives

Follow [GATE_CLOSEOUT.md](./GATE_CLOSEOUT.md) when closing a roadmap phase. Earlier phase handoffs and reflections are preserved under [`archive/`](./archive/) and [`archive/reflections/`](./archive/reflections/).

## Troubleshooting

### Workspace Cache Permission Errors
**Symptom:** Traversal hits `PermissionError` on a local tool cache directory.
**Fix:** Built-in ignore defaults skip `.pytest_cache/`, `.worktrees/`, and `.tmp/`. Add custom cache directories to `.ctxignore`.

### Write Lock Contention (`lock_held`)
**Symptom:** `ctx init`, `ctx refresh`, or `ctx reset` exits with error code `lock_held`.
**Fix:** Wait for the active `ctx` process to finish; `CtxLock` automatically reclaims stale locks left by crashed processes.

### `pytest` Not Found
**Symptom:** `pytest` is missing in the active shell.
**Fix:** Activate the project virtual environment where `.[dev]` is installed and run `python -m pytest`.
