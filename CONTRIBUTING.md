# Contributing to `ctx`

`ctx` is maintained by humans and coding agents working from deterministic static contracts. Every contribution takes source, parser, or documentation changes as input and must leave tests, `.ctx/` verification, and documentation hygiene checks green.

## Development Setup

Install the package with development extras in an existing virtual environment and run the test suite:

```bash
pip install -e ".[dev]"
python -m pytest tests/
python3 -m unittest tests/test_doc_hygiene.py -v
```

## Local Verification Workflow

### 1. Structural Map Check
`ctx` compiles tiered maps into a gitignored `.ctx/` directory rather than committing per-directory `CONTEXT.md` files. Verify deterministic generation and clean up `.ctx/` locally before opening a pull request:

```bash
CTX_OUTPUT=json python -m ctx init .
CTX_OUTPUT=json python -m ctx check . --verify --check-exit
CTX_OUTPUT=json python -m ctx uninit .
```

### 2. Merge Policy (`ops/merge-policy.json`)
Hosted cloud virtual machine pull-request triggers are retired; GitHub Actions workflows use `workflow_dispatch` only. Run `python -m pytest` and `ctx check . --verify --check-exit` locally on the host, and keep `"GitGuardian Security Checks"` passing on the exact pull-request head SHA.

### 3. Test-First Changes
When adding a language parser rule, CLI flag, or impact-graph behavior:
1. Add or update unit tests under `tests/`.
2. Run `python -m pytest` to confirm the new test fails before your fix.
3. Implement the change under `src/ctx/`.
4. Re-run `python -m pytest` and confirm zero regressions.

## Documentation Hygiene

Human-facing Markdown guides (`README.md`, `CONTRIBUTING.md`, `RUNBOOK.md`, `architecture.md`, `rules.md`, and `docs/benchmarks/*.md`) are gated by `tests/test_doc_hygiene.py`:

- **Lead with inputs and outputs (`DOC-001:TLDR`):** Keep a plain-English `## TL;DR` section (`1..60` words, no UTF-8 byte-order mark) at the top of `README.md` explaining what goes in, what `ctx` computes, and what comes out.
- **Bound sentence length (`DOC-002:RUNON`):** Keep every prose sentence at or under 45 words.
- **Cut filler and expand acronyms (`LAN-009:JARGON`, `LAN-003:ACRONYM`):** Avoid banned AI/corporate filler or ambiguous modals, and expand unfamiliar domain acronyms such as Abstract Syntax Tree (AST) or Model Context Protocol (MCP) at first use.
- **Verify links (`DOC-003:LINK`):** Use repository-relative Markdown links with valid `#heading` anchors, and never commit machine-local `file://` links.

## Engineering Rules

- **Respect `.gitignore` and `.ctxignore`:** `ctx` merges `.ctxignore.default`, ancestor/root/nested `.gitignore` files, and `.ctxignore` overrides (including `!pattern` opt-ins) so workspace caches stay out of maps.
- **Cross-Platform Determinism:** SHA-256 hashes and portable `# <relative-path>` headings must match across Linux, macOS, Windows, and git worktrees.
- **Focused Pull Requests:** Keep commits small following Conventional Commits, and scope roadmap branches to one named gate unless [AGENTS.md](./AGENTS.md) specifies otherwise.
