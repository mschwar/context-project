# API Evaluation & Loop Resilience Reflection

**Date:** 2026-03-20
**Branch:** `feat/resilient-until-complete`
**Tests:** 432 passing (6 new)
**PR:** #64

---

## Context

Post-Phase-25 API stress test on three real-world directory trees using cloud providers (Anthropic Claude Haiku 4.5). The evaluation exposed a critical resilience gap in the `--until-complete` loop and produced the first real-world API cost benchmarks.

## Successes

- **Loop resilience fix works end-to-end.** The `--until-complete` loop now continues when transient errors occur alongside forward progress, stops on stall (zero progress) or clean completion. The Baha'i tree (31 dirs, 566 files) completed in 2 passes with zero errors.
- **Error accumulation fix is correct.** Replacing errors each pass (instead of extending) means directories retried and succeeded no longer appear as errors in the final result. Confirmed by spot-check: 0 errors reported despite hash failures on Google Drive `.gdoc`/`.gsheet` shortcut files.
- **Cumulative USD guardrail is enforced.** New between-cycle check prevents multi-pass runs from exceeding `max_usd_per_run` across cycles. Token budget remains per-pass by design.
- **API cost benchmarks established.** First real-world cost data for cloud provider runs on personal document trees.
- **Manifest accuracy is high.** 5/5 random spot-checks showed exact file/subdirectory match between CONTEXT.md and filesystem reality. Content summaries were accurate and useful.

## Evaluation Results

### DISSERTATION Tree (171 dirs)
- **Provider:** Anthropic (Claude Haiku 4.5)
- **Coverage:** 171/171 (100%)
- **Tokens:** 1,577,032
- **Exit code:** 2 (budget guardrail fired after completion)
- **Note:** All directories were successfully processed; the guardrail fired post-completion

### Baha'i Tree (31 dirs, 566 files)
- **Provider:** Anthropic (Claude Haiku 4.5)
- **Coverage:** 31/31 (100%)
- **Passes:** 2 (pass 1: 31 dirs/116k tokens; pass 2: validation, 23k tokens)
- **Tokens:** 138,931
- **Estimated cost:** $0.11
- **Wall time:** ~7.5 minutes
- **Errors:** 0
- **Spot-check:** 5/5 directories verified — exact file counts and names match reality

### products_GRANTS Tree (390 dirs, 2,410 files)
- **Provider:** Anthropic (Claude Haiku 4.5)
- **Coverage:** 0/390
- **Outcome:** Blocked — Anthropic API credits exhausted before processing began
- **Note:** This run validated the failure path — every directory error was a credit-balance failure, and the pre-fix loop would have broken on the first error. Post-fix, the loop correctly detected zero progress and stopped.

## Cost Model (Haiku 4.5 via API)

| Tree | Dirs | Files | Tokens | Cost | Per-Dir | Per-File |
|------|------|-------|--------|------|---------|----------|
| Baha'i | 31 | 566 | 138,931 | $0.11 | $0.004 | $0.0002 |
| DISSERTATION | 171 | ~1,200 | 1,577,032 | ~$1.26 | $0.007 | ~$0.001 |

## Friction Points

- **Google Drive shortcut files (.gdoc, .gsheet) cause hash errors.** These are tiny JSON pointers that can't be opened locally. ctx handles them gracefully (manifests still generate correctly), but the stderr noise is significant — 26 "Failed to hash file" warnings on the Baha'i tree alone.
- **products_GRANTS evaluation blocked by credits.** Unable to validate API cost for the largest tree. Retry needed once credits are topped up.
- **The original loop was catastrophically fragile.** Any single directory error — even a transient one — would break the entire `--until-complete` loop. On the 390-dir GRANTS tree, this meant 0/390 coverage with no retry.

## Observations

- The 2-pass pattern on the Baha'i tree is expected and efficient: pass 1 processes all leaf directories, pass 2 re-processes parent directories that now have fresh child summaries to incorporate.
- Cost scales roughly linearly with directory count, with per-directory cost varying by content density ($0.004-$0.007/dir).
- The `.gdoc`/`.gsheet` hash errors are a Google Drive-specific issue. These files are virtual — they exist as local shortcut files but their actual content lives in Google's cloud. A future improvement could detect and skip these file types.

## Suggestions

1. **Suppress or downgrade `.gdoc`/`.gsheet` hash warnings** — detect Google Drive shortcut files by extension and skip hashing silently, or log at DEBUG level instead of WARNING.
2. **Complete the products_GRANTS API evaluation** — once credits are topped up, rerun to establish cost benchmarks for the largest tree (390 dirs, 2,410 files).
3. **Add `.gdoc`/`.gsheet`/`.gslides` to default ignore** — these virtual files add no value to manifests and generate noisy errors on Google Drive-synced trees.

## Disposition Table

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | Suppress Google Drive shortcut hash warnings | Backlog |
| 2 | Complete products_GRANTS API evaluation | Pending credits |
| 3 | Add Google Drive extensions to default ignore | Backlog |
