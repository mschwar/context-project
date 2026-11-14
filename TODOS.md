# TODOS

Active engineering backlog for `ctx` (`v2.0.0+`). Completed historical backlog items are archived in [`archive/state-history-phases-1-34.md`](./archive/state-history-phases-1-34.md).

## Completed in `v2.0.0` (Waves A–D) ✓

- **Wave A — Config Wiring, Cross-Host `repo_id`, Archive Hygiene & Tracker Convergence ✓:** Wired `.ctxconfig` `max_depth` and `CTX_MAX_DEPTH` into `extract_skeleton`, switched `repo_id` to normalized `remote.origin.url` / root-commit SHA, moved retired pre-Wave-3A specs into `archive/`, and retired automatic cloud-VM tag builds in `.github/workflows/publish.yml`.
- **Wave B — Hub-Aware Symbol Ranking & `.ctx/capsule.json` Persistence ✓:** Replaced raw substring counting with Python AST non-kwarg identifier extraction + inbound module centrality + entrypoint slot cap, and persisted `.ctx/capsule.json` atomically during `ctx init` and `ctx refresh` for `project-ledger`.
- **Wave C — `ctx impact --git-diff` & `--staged` Proportional Verification Compiler ✓:** Shipped `analyze_diff_impact` across `impact.py`, `api.py`, `cli.py`, and `mcp_server.py` (`ctx_impact`), compiling git working-tree, staged, and branch diffs into `verification_scope` and exact `recommended_checks`.
- **Wave D — 13-Language C/C++ Parity & Monorepo Workspace Graph ✓:** Added `c_cpp_parser.py` + C/C++ `#include` graph edges and cross-package workspace resolution for Python (`packages/*/src/<pkg>`), JS/TS (`package.json` workspaces), and Rust (`Cargo.toml` workspace crates).

## Next Horizon (Wave E)

### 1. Live Agent Harness Pre-Edit Auto-Injection & Edit-Success Benchmark (P2)
- **What:** Wire `ctx export . --depth 0` at cold start and `ctx impact --git-diff HEAD . --output json` prior to verification in fleet agent harnesses (`homelab agent-substrate`), then benchmark real multi-file bugfix pull requests (`raw_grep` vs `ctx` static compiler) on wall-clock time, tool turns, test commands run, and regression rate.
- **Why:** Phase 27.1 proved static-oracle retrieval superiority (`+17.0` percentage points mean recall, `1.000` blast-radius F1, `-87.9%` context tokens). Measuring end-to-end edit and proportional-verification wins on real commits closes the empirical loop.

### 2. Optional `tree-sitter` Grammar Backend (`ctx-tool[treesitter]`) (P3)
- **What:** Keep the zero-dependency regex/stdlib parsers as the default backend while offering an optional `ctx-tool[treesitter]` extra for complex nested C++, Rust macro, and TypeScript type constructs.
- **Why:** Preserves the 3-dependency core install (`click`, `pyyaml`, `pathspec`) while raising parser precision on macro-heavy polyglot codebases.

### 3. Fine-Grained Function Call-Graph Narrowing inside High-Fan-In Modules (P3)
- **What:** When a git diff modifies a single helper inside a high-fan-in module (such as `config.py`), narrow `coupled_tests` to callers importing or invoking that symbol (with automatic fallback to file-level blast radius on dynamic `getattr` / module-attribute access).
- **Why:** Further reduces `coupled_tests` false positives on utility modules without sacrificing recall.
