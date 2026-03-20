# Contributing to `ctx`

We embrace an **Agentic SDLC**. This means the codebase is designed to be co-authored and maintained by both humans and AI agents.

## The Agentic Workflow

### 1. Context Maintenance
Every PR that adds or modifies a directory MUST update the corresponding `CONTEXT.md` files.
- Use `ctx refresh .` before committing your changes.
- Ensure the `content_hash` in the frontmatter is updated to reflect the new state.
- Verification: Running `ctx check . --check-exit` should return exit code `0` for a fresh tree.
- **CI enforcement:** The `CTX Manifest Check` workflow currently runs the legacy equivalent `ctx status . --check-exit-code` on every push and PR. The canonical command is `ctx check . --check-exit`. Always run `ctx refresh .` locally and include the updated `CONTEXT.md` files in your commit before pushing.

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
```

## Agentic Rules of Engagement
- **Never bypass `.ctxignore`:** Respect the filtering logic to keep manifests clean and consistent across CLI surfaces.
- **Atomic Commits:** Prefer small, focused commits that update both code and its associated context.
- **Deterministic Hashing:** If you modify `hasher.py`, ensure that hashes remain stable across platforms (Windows/Linux).
- **One Gate Per PR:** For roadmap work, keep each branch scoped to one named gate unless `AGENTS.md` says otherwise.
