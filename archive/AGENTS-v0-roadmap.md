# Agent Handoff: Building `ctx`

## What This Is
A Python CLI tool (`ctx`) that generates `CONTEXT.md` manifest files for every directory in a tree. These manifests give AI agents structured summaries so they can navigate codebases coarse-to-fine without reading raw files.

## Current State
The full architecture is scaffolded with typed interfaces, detailed docstrings, and `raise NotImplementedError` stubs. Every function has an `Implementation:` block in its docstring explaining exactly what to build.

## Project Layout
```
pyproject.toml              # Package config — ready, no changes needed
.ctxignore.default          # Default ignore patterns — ready, no changes needed
src/ctx/
    __init__.py             # Version string — done
    config.py               # STUB — load config from env/file/CLI
    ignore.py               # STUB — .ctxignore pattern matching via pathspec
    hasher.py               # STUB — SHA-256 content hashing (file + directory)
    manifest.py             # STUB — CONTEXT.md read/write/parse
    llm.py                  # STUB — LLM client interface + Anthropic/OpenAI impls
    generator.py            # STUB — core engine: tree walk, summarize, write manifests
    cli.py                  # STUB — Click commands: init, update, status
tests/
    test_hasher.py          # Test case descriptions, no implementations
    test_manifest.py        # Test case descriptions, no implementations
    test_generator.py       # Test case descriptions, no implementations
    fixtures/sample_project # Sample directory tree for testing
```

## Build Order (Phases)

### Phase 1: Foundation (no dependencies between these — can parallelize)
These modules have no internal dependencies. Build them independently.

| Module | Agent Type | What to Build |
|--------|-----------|---------------|
| `config.py` | python-pro | Load config from .ctxconfig YAML, env vars, CLI overrides. See docstring for resolution order. |
| `ignore.py` | python-pro | Load .ctxignore.default + user .ctxignore, merge, return PathSpec. Uses `pathspec` library. |
| `hasher.py` | python-pro | SHA-256 hashing: `hash_file()` reads binary chunks, `hash_directory()` hashes sorted children recursively. |
| `manifest.py` | python-pro | Read/write CONTEXT.md: YAML frontmatter + markdown body. Split on `---` delimiters. |

### Phase 2: LLM Client (depends on config.py)
| Module | Agent Type | What to Build |
|--------|-----------|---------------|
| `llm.py` | ai-engineer | Implement `AnthropicClient` and `OpenAIClient`. Each has `summarize_files()` (batch, returns JSON array of summaries) and `summarize_directory()` (returns formatted markdown body). Use the `anthropic` and `openai` SDKs. See detailed prompt guidance in docstrings. |

### Phase 3: Generator (depends on all of Phase 1 + Phase 2)
| Module | Agent Type | What to Build |
|--------|-----------|---------------|
| `generator.py` | python-pro | Implement `generate_tree()`, `update_tree()`, `get_status()`, `is_binary_file()`, `format_binary_info()`. The big one. See docstrings for full algorithms. |

### Phase 4: CLI Wiring (depends on Phase 3)
| Module | Agent Type | What to Build |
|--------|-----------|---------------|
| `cli.py` | cli-developer | Wire up Click commands to call generator functions. Add progress output. See docstrings. |

### Phase 5: Tests
| Module | Agent Type | What to Build |
|--------|-----------|---------------|
| `test_hasher.py` | test-automator | Implement all test cases listed in the file. Use tmp_path fixtures. |
| `test_manifest.py` | test-automator | Implement all test cases listed in the file. Use tmp_path fixtures. |
| `test_generator.py` | test-automator | Implement all test cases. Mock the LLM client. Use fixtures/sample_project. |

## Key Contracts

### Every function's behavior is specified in its docstring
Read the `Implementation:` section in each function's docstring. It tells you exactly what to do, step by step. Follow it.

### CONTEXT.md Format
```
---
generated: 2026-03-13T10:00:00Z
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:abc123...
files: 12
dirs: 3
tokens_total: 48000
---
# /path/to/directory

One-line purpose.

## Files
- **file.py** — one-line summary
- **data.bin** — [binary: xlsx, 234KB]

## Subdirectories
- **subdir/** — one-line summary

## Notes
- optional hints
```

### Hash Format
All hashes: `sha256:<hex_digest>` (full 64-char hex).

### LLM Prompt Patterns
- **summarize_files**: Send all files in one message, ask for JSON array of one-line summaries. Parse the array. One summary per file, same order as input.
- **summarize_directory**: Send dir path + file summaries + subdir summaries, ask for the CONTEXT.md markdown body in the exact format above.

### Binary File Detection
Read first 8192 bytes. Binary if: contains `\x00` byte, or fails UTF-8 decode. Binary files are listed in manifests as `[binary: ext, size]` but never sent to the LLM.

## Environment
- Python 3.10+
- Cross-platform (Windows + Mac)
- Use `pathlib.Path` everywhere for paths
- Dependencies: click, anthropic, openai, pyyaml, pathspec

## How to Install & Test
```bash
pip install -e ".[dev]"   # Install in dev mode
ctx --version             # Verify CLI works
pytest tests/             # Run tests
ctx init ./tests/fixtures/sample_project  # Test on sample data
```
