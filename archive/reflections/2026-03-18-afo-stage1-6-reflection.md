# AFO Stage 1–6 Reflection

**Date:** 2026-03-18
**Branch:** `feat/afo-stage1-6-closeout`
**Scope:** Closeout for Agent-First Overhaul Stages 1–6
**Tests:** 407 passing at closeout validation
**External validation input:** live-repo reports from `gstack-main`

---

## Successes

- AFO Stages 1–6 all landed on `main` with the intended surface shift: canonical `refresh` / `check` / `export` / `reset`, JSON envelopes, non-interactive config, agent-first docs, stdio MCP, and workflow patterns.
- The merged branch state is coherent from an operator perspective: pre-commit and CI now both gate freshness with `ctx check . --check-exit`, and `AGENTS.md` documents the session-bootstrap, session-end, and handoff patterns.
- MCP integration is now first-class enough for IDE-hosted agents to discover and call `ctx` through `ctx serve --mcp`, while HTTP serving remains available as an optional extra.
- The closeout validation itself exposed and corrected a small documentation-test drift: the Stage 6 docs test was asserting an inline shell form for the CI command even though the shipped workflow intentionally split `run:` and `env:`.

## Friction

- The strongest external-repo findings were not bootstrap or command-surface issues. They were trust issues in generated manifests: hallucinated file lists, duplicate bullets, `None` rows, and weak directory-purpose summaries.
- `refresh()` still eagerly calls git diff before strategy selection, so non-git extracted trees remain a real failure mode despite the unified `refresh` surface being framed as directory-tree oriented.
- The current closeout carry-forward rule points backlog into `AGENTS.md`, but post-Stage-4 `AGENTS.md` is now a machine-readable command contract. For AFO closeout, the actionable carry-forward scope is tracked in `state.md` and `AGENT_FIRST_OVERHAUL.md` to avoid polluting the agent contract with roadmap prose.

## Observations

- The AFO work succeeded at agent operations and packaging, but not yet at manifest trust. External validation shows that correctness of the manifest body is now the main product risk.
- `ctx check --verify` is stronger than the old frontmatter-only `verify`, but it still does not validate manifest body structure or body-to-filesystem consistency.
- Prompt tuning alone is unlikely to fully solve the reported defects. Hallucinated file/subdirectory bullets and illegal `None` rows are better handled deterministically or with post-generation validation.
- Local-provider fallback kept real runs alive, but the current batching path still degrades quality invisibly when malformed batches cause repeated per-file fallback.

## Suggestions

1. Make `refresh` git-optional by deferring `get_changed_files()` until the smart path is actually selected, and fall back cleanly for non-git trees.
2. Stop letting the LLM author `## Files` and `## Subdirectories`; render those sections deterministically from the real directory contents.
3. Extend `ctx check --verify` with body-level verification for duplicate bullets, nonexistent files, missing real files, illegal `None` rows, and count mismatches.
4. Fix UTF-8 boundary handling in `is_binary_file()` so valid text files are not misclassified as binary when a multibyte sequence straddles the sample boundary.
5. Tighten prompt calibration for repo-specific summaries, especially to avoid boilerplate like “main entry point” and to describe `SKILL.md` / prompt files accurately.
6. Treat local providers as a separate operating mode: smaller default batches or automatic batch-downshift after the first malformed response, plus surfaced fallback counts in CLI/API results.
7. Add external-repo regression coverage for non-git extracted trees, UTF-8 boundary fixtures, malformed-but-fresh manifest bodies, and snapshot/rubric checks for manifest quality.

## Implications For The Next Phase

- The next follow-on phase should focus on manifest trust and real-world validation rather than more interface changes.
- The highest-value work now is deterministic manifest structure, stronger verification, and regression fixtures from real repositories.

## Disposition Table

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | Make `refresh` git-optional | Carry into Phase 24 |
| 2 | Deterministic `## Files` / `## Subdirectories` sections | Carry into Phase 24 |
| 3 | Body-level verification in `ctx check --verify` | Carry into Phase 24 |
| 4 | UTF-8-safe binary detection | Carry into Phase 24 |
| 5 | Prompt calibration for repo-specific summaries and `SKILL.md` handling | Carry into Phase 24 |
| 6 | Local-provider adaptive batching plus surfaced fallback counts | Carry into Phase 24 |
| 7 | External-repo regression fixtures and snapshot/rubric checks | Carry into Phase 24 |
