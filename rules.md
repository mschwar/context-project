# Engineering Standards and Coding Rules

Standards for developers and coding agents modifying `ctx`.

## Core Principles

- **Zero-LLM Determinism:** `ctx` extracts all maps, capsules, and impact graphs locally from source files without external network calls or API keys.
- **No Sidecar Litter:** Never commit per-directory `CONTEXT.md` files; `.ctx/` outputs stay gitignored at the repository root.
- **Surgical Changes:** Keep diffs focused on the requested behavior and preserve CLI and JSON envelope compatibility.
- **Test-Backed Logic:** Pair every parser, graph, CLI, or server change with unit tests in `tests/`.
- **Ignore Consistency:** Every command that walks repository files must apply the same `.ctxignore.default`, `.gitignore`, and `.ctxignore` filter boundary.

## Python Code Standards

1. **Typing:** Require Python 3.10+ type annotations across public functions, methods, and dataclasses.
2. **Paths:** Use `pathlib.Path` for all filesystem operations so paths work identically on Linux, macOS, and Windows.
3. **Immutability and Atomic Writes:** Prefer `@dataclass` result records, guard concurrent writes with `CtxLock`, and write files via temporary files plus `os.replace`.
4. **Explicit Error Handling:** Catch specific exception classes and map user-facing failures to documented error codes in [AGENTS.md](./AGENTS.md#error-codes).
5. **Minimal Dependencies:** Keep runtime dependencies limited to `click`, `pyyaml`, and `pathspec` (`pyproject.toml`); keep FastAPI and Uvicorn isolated behind the optional `[serve]` extra.

## Hash and Binary Safety

- Prefix all SHA-256 digests with `sha256:` followed by lowercase hexadecimal characters.
- Compute `structural_hash` and `boundary_doc_hash` over normalized forward-slash relative paths so digests never vary by operating system or checkout directory.
- Detect binary files via null-byte inspection and UTF-8 decoding checks before parsing source text.
- Confine `ctx serve` and Model Context Protocol (MCP) resource reads (`ctx://.ctx/*`) strictly within the resolved root path.

## Documentation Standards

- Keep [AGENTS.md](./AGENTS.md) compliant with `schema_version 1` section order and valid JSON blocks (`tests/test_docs.py`).
- Keep `README.md` at or under 100 lines with a `1..60` word `## TL;DR` stating inputs, processing, and outputs (`tests/test_doc_hygiene.py`).
- Expand unfamiliar domain acronyms such as Abstract Syntax Tree (AST) at first use, avoid banned filler, and keep prose sentences at or under 45 words.

## Testing Requirements

- **Unit Tests:** Cover parsers (`lang_parsers/`), `skeleton`, `impact`, `ignore`, `hasher`, `lock`, `config`, `api`, `cli`, `sdk`, and `mcp_server`.
- **Fixture Isolation:** Build temporary repositories using Pytest's `tmp_path` or `tempfile.TemporaryDirectory` and shared fixtures under `tests/fixtures/sample_project`.
