# Phase 30.9 Reflection — Full Repository Audit Remediation Gate (Issue #76)

**Date:** 2026-10-31  
**Baseline:** `ctx` v1.1.0 (`0ec8d7a`, 566 passing tests)  
**Issue:** [#76](https://github.com/mschwar/context-project/issues/76)

## Plan vs Actuals

| Planned Item | Actual Outcome | Notes |
|--------------|----------------|-------|
| **30.9.1 (`D1`)** Portable repo-relative `# <rel_path>` manifest headings | Completed | Updated `_render_manifest_body()` and `validate_manifest_body()` in `src/ctx/generator.py` to render and validate `# {_relative_path_str(path, root)}` (`# .` at repo root) so manifests stay portable across OSes, machines, and git worktrees. |
| **30.9.2 (`D2`)** Unified Tier 2 `ctx refresh` & Tier 1 `CtxProject.is_stale()` | Completed | Added `_refresh_tier2()` wired into `api.refresh()` (zero LLM calls, zero leaf `CONTEXT.md` files, `CtxLock`-protected), auto-synced `.ctx/CONTEXT*.md` after Tier 1 `refresh()`, and fixed `CtxProject.is_stale()` in `src/ctx/sdk.py` for both missing Tier 2 hashes and Tier 1 directory/export drift. |
| **30.9.3 (`D3`)** Sound `smart` refresh (untracked files + pre-existing stale/missing union) | Completed | Added `git ls-files --others --exclude-standard` to `get_changed_files()` in `src/ctx/git.py` and added `_expand_smart_target_directories()` in `src/ctx/generator.py` so `smart` refresh never strands untracked files or pre-existing missing/stale directories. |
| **30.9.4 (`D4`)** Heartbeat-backed atomic `CtxLock` | Completed | Added atomic temp-file + `os.replace` lock writes, a background daemon heartbeat thread, `STALE_TIMEOUT_SECONDS = 900`, PID-liveness-first staleness checks, and PID-ownership verification on release in `src/ctx/lock.py`. |
| **30.9.5 (`D5`)** Token-based `max_file_tokens` slicing & 0-byte `[empty file]` handling | Completed | Added `_truncate_to_tokens()` (`tiktoken` `encode`/`decode` with char fallback) and `_empty_file_summary()` (`[empty file]` without incrementing `files_binary` or failing `ctx check --verify`) in `src/ctx/generator.py`. |
| **30.9.6 (`D6`)** `.gitignore` privacy & noise boundary | Completed | Merged `target_root / ".gitignore"` between `.ctxignore.default` and `target_root / ".ctxignore"` in `src/ctx/ignore.py` while preserving `.ctxignore` `!negation` overrides. |
| **30.9.7 (`D7`)** `skeleton.py` & `build_fleet_capsule` accuracy across 11 languages | Completed | Filtered stdlib modules (Python/Node/Rust/Go/Java/Kotlin/Swift) from `external_deps`, added import extraction for all 11 supported languages plus `go.mod`/`Cargo.toml` module-prefix classification, diversified `key_symbols` across files prioritizing entrypoints, excluded tests/nonexistent `package.json` `main` targets from entrypoints, honored `depth` in `capsule_markdown`, and replaced line-count slicing with delimiter-based `strip_tier2_chrome()`. |
| **30.9.8 (`D8`)** Git worktree, `core.hooksPath`, atomic `.ctx/hook.pid`, & `hook_log.json` pruning | Completed | Supported `.git` worktree pointer files (`git_dir.exists()`), resolved hooks via `git rev-parse --git-path hooks`, moved hook PID lock to `.ctx/hook.pid` with `os.O_CREAT \| os.O_EXCL` atomic creation, and capped `hook_log.json` at `MAX_HOOK_LOG_ENTRIES = 200` in `src/ctx/init.py`. |
| **30.9.9 (`D9`)** Enforced `Config.extensions` / `CTX_EXTENSIONS` allowlist | Completed | Added `resolve_configured_extensions()`, `normalize_extensions()`, and `file_matches_extensions()`, enforcing extension filtering uniformly across generation, hashing, health inspection, verification, and skeleton extraction. |
| **30.9.10 (`D10`)** Accurate pricing, directory summary disk caching, & `tokens_saved` telemetry | Completed | Ordered specific `mini`/`nano` models ahead of prefix substrings in `PRICING_DATA` + added `OUTPUT_PRICING_DATA`, cached `summarize_directory` and token counts in `CachingLLMClient`, propagated `cache_hits`/`cache_misses`/`tokens_saved` through `GenerateStats` -> `RefreshResult`, and fixed `stats_board._build_run_record`. |
| **30.9.11 (`D11`)** Config-first `ctx setup --check` preflight & wording accuracy | Completed | Checked `CTX_PROVIDER`, `.ctxconfig`, and `CTX_BASE_URL` before `detect_provider()` in `src/ctx/preflight.py` and corrected `"mtime-based"` to `"content-hash-based"`. |
| **30.9.12 (`D12`)** Lazy cloud SDK imports, visible `stats`/`setup` CLI commands, DRY `cli.export`, & composite action fix | Completed | Lazy-loaded `anthropic` and `openai` via PEP 562 `__getattr__` in `src/ctx/llm.py`, unhid `ctx stats` and `ctx setup`, delegated `cli.export` to `api.export_context()`, and updated `.github/actions/ctx-check/action.yml` + `.github/workflows/tests.yml`. |
| **30.9.13 (`D13`)** Repo hygiene, documentation alignment, out-of-scope work-queue filing, & full manifest refresh | Completed | Removed stray `'=4.0'`, cleaned `package.json`, aligned `README.md`, `CONTRIBUTING.md`, `RUNBOOK.md`, `AGENTS.md`, `architecture.md`, `state.md`, and `TODOS.md`, queued Wave 2/3 feature unlocks as GitHub Issues [#77](https://github.com/mschwar/context-project/issues/77), [#78](https://github.com/mschwar/context-project/issues/78), and [#79](https://github.com/mschwar/context-project/issues/79), and refreshed all `CONTEXT.md` manifests to `0` stale, `0` missing, `0` invalid. |

## Surprises & Root Causes

1. **Emergent Bug — `api.refresh` Always Recorded `cache_hits=0, cache_misses=0`:**
   - *Symptom:* `api.refresh()` checked `client.hit_miss_counts` on the raw `AnthropicClient` / `OpenAIClient` returned by `create_client(config)`, while `generate_tree()` and `update_tree()` wrapped `client` inside a temporary `CachingLLMClient` and discarded its counters on return.
   - *Fix:* Added `cache_hits`, `cache_misses`, and `tokens_saved` fields to `GenerateStats` (and `tokens_saved` to `RefreshResult`) so real `ctx refresh` runs propagate disk/memory cache hits, misses, and saved tokens into `.ctx-cache/run_stats.json` and `~/.ctx/run_stats.json`.

2. **Directory Cache Key Soundness Under Modified Files With Identical One-Line Summaries:**
   - *Insight:* Keying `CachingLLMClient.summarize_directory` solely on `(model, dir_name, file_summaries, subdir_summaries)` would serve a cached directory summary even after a file's implementation changed if its terse 1-line summary happened not to change. Including the directory's `content_hash` in the cache key ensures modified directories always regenerate on `update_tree` while `--force` refreshes on unchanged directories hit the disk cache at zero token cost.

## Disposition Table

| Finding / Item | Disposition | Target Reference |
|----------------|-------------|------------------|
| P0–P3 repository audit findings (`D1`–`D13`) + emergent `GenerateStats` cache telemetry bug | **Implemented this gate** | Phase 30.9 (`30.9.1`–`30.9.13`, Issue [#76](https://github.com/mschwar/context-project/issues/76)) |
| Hybrid Tier 2 semantic invariant synthesis on `should_invoke_llm()` + local constrained JSON-schema probing | **Carry into Phase 31** | `state.md` §Phase 31, Issue [#77](https://github.com/mschwar/context-project/issues/77) |
| Directed dependency & blast-radius graph (`ctx impact` / `ctx_impact`) + operational surface extraction | **Carry into Phase 32** | `state.md` §Phase 32, Issue [#78](https://github.com/mschwar/context-project/issues/78) |
| Optional cloud LLM SDK packaging split (`[anthropic]`, `[openai]`) + Phase 27.1 A/B agent navigation benchmark | **Carry into Phase 33** | `state.md` §Phase 33, Issue [#79](https://github.com/mschwar/context-project/issues/79) |
