# Contributing to `ctx`

We embrace an **Agentic SDLC**. This means the codebase is designed to be co-authored and maintained by both humans and AI agents.

## The Agentic Workflow

### 1. Context Maintenance
Every PR that adds or modifies a directory MUST update the corresponding `CONTEXT.md` files.
- Use `ctx refresh .` before committing your changes.
- Ensure the `content_hash` in the frontmatter and portable repo-relative `# <path>` heading reflect the new state.
- **Verification:** Run full body and freshness verification locally before opening or merging a PR:
  ```bash
  CTX_OUTPUT=json python -m ctx check . --verify --check-exit
  ```
- **Merge policy (`ops/merge-policy.json`):** Hosted cloud-VM PR triggers are retired (`workflow_dispatch` only). Run `python -m pytest` and `CTX_OUTPUT=json python -m ctx check . --verify --check-exit` locally on the host, and keep `"GitGuardian Security Checks"` green on the exact PR head SHA.

### 2. Implementation Blocks
New functions and classes should include an `Implementation:` block in their docstrings. This provides clear, step-by-step instructions for subsequent agents to follow when filling in stubs or refactoring.

### 3. Test-Driven Autonomy
When adding a feature:
1. Write the test cases first (in `tests/`).
2. Run the tests to confirm they fail.
3. Implement the logic.
4. Run the tests to confirm they pass.
This loop is essential for agents to verify their own work.

### 4. Manifest Review
During code review, pay special attention to the `CONTEXT.md` changes. They are the "map" that other agents use to understand your "territory". If a manifest's purpose statement is vague, the agent's navigation will suffer.

## Development Environment

```bash
pip install -e ".[dev]"
python -m pytest tests/
CTX_OUTPUT=json python -m ctx check . --verify --check-exit
```

## Agentic Rules of Engagement
- **Respect `.gitignore` and `.ctxignore`:** `ctx` merges `.ctxignore.default`, the repo's `.gitignore`, and `.ctxignore` overrides so manifests never leak gitignored workspace state.
- **Atomic Commits:** Prefer small, focused commits following Conventional Commits (enforced via `.husky/commit-msg` commitlint).
- **Deterministic Hashing & Portable Headings:** Hashes and `# <relative-path>` headings must remain identical across Linux, macOS, Windows, and isolated git worktrees.
- **One Gate Per PR:** For roadmap work, keep each branch scoped to one named gate unless `AGENTS.md` or an explicit audit remediation gate specifies otherwise.
