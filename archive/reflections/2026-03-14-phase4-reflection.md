# Phase 4 Reflection — Prompt Quality & Batch Control

**Date:** 2026-03-14
**Branch:** `feat/phase4-prompt-quality-batch-control`
**Status:** Complete, pending PR to `main`

---

## Successes

- All six `DEFAULT_PROMPT_TEMPLATES` rewritten with explicit, machine-readable rules. The 20-word sentence cap and purpose-over-implementation framing materially improve consistency across providers.
- `batch_size` config gives users direct control over LLM call granularity without requiring code changes. Fills the gap for small-context local models (Ollama, LM Studio) that were silently failing on large batches.
- `_apply_batch_size()` helper extracted cleanly from duplicated logic in `AnthropicClient` and `OpenAIClient`. Both now share one implementation.
- `bitnet` removed from CLI choices without breaking the deprecation error path for env/config users — clean separation between the UI surface and the runtime fallback.
- SDLC guardrails (husky, commitlint, pre-commit pytest, GitHub Actions) bootstrapped on the same branch without polluting the feature commits.

## Friction

- The SDLC bootstrap (`chore/sdlc-bootstrap`) was developed in parallel and merged into this feature branch rather than into `main` first. This created a noisy merge commit and muddied the branch history. Future SDLC-level chores should land on `main` before feature work branches off.
- `AGENTS.md` still referenced the stale `feat/local-providers-token-budget` branch notice at the time of Phase 4 work — agents reading the doc would have started from the wrong base.

## Observations

- `Config.token_budget` and `CachingLLMClient` are both wired up but incomplete at runtime. These half-finished features are invisible to users and add surface area without benefit until Phase 5 closes them.
- The prompt template rewrites are not validated by automated tests — there is no assertion that the LLM follows the 20-word rule or returns the expected markdown structure. Output quality is observed manually.

## Suggestions

1. **Phase 5 immediate:** Close `token_budget` enforcement and disk cache before adding any new features. Half-implemented config fields erode trust in the config system.
2. **Prompt regression tests:** Add at least a smoke test that exercises each template with a `FakeLLMClient` and asserts the prompt string contains expected structural markers (e.g., `## Files`, `## Subdirectories`).
3. **SDLC chores on main first:** Any infrastructure or process work (hooks, CI, config) should land on `main` before feature branches diverge, to keep feature PRs clean.

## Implications for Phase 5

- Start from `main` after this branch is merged.
- Phase 5 scope is locked: persistent cache (5.1), token budget enforcement (5.2), `--dry-run` flag (5.3).
- No new dependencies needed for any Phase 5 deliverable.
- Prompt regression tests (suggestion 2) are a stretch goal if time allows; do not block Phase 5 on them.
