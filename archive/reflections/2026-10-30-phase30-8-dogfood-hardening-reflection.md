# Phase 30.8 Reflection — AI-Server Live Dogfood Hardening Gate (Issue #73)

**Date:** 2026-10-30  
**Baseline:** `ctx` v1.1.0 (`84ea67c`, 555 passing tests)  
**Issue:** [#73](https://github.com/mschwar/context-project/issues/73)

## Plan vs Actuals

| Planned Item | Actual Outcome | Notes |
|--------------|----------------|-------|
| **30.8.1** `.ctx/` ignore parity, `ctx init` ordering, & `ctx reset` `.ctx/` protection | Completed | Added `.ctx/` and `.ctx-hook.pid` to both `.ctxignore.default` and `src/ctx/.ctxignore.default`; moved `.ctx/.gitignore` and root `.gitignore` mutation ahead of `refresh()` in `init_project()`; excluded `.ctx/` and `.ctx-cache/` in `api._iter_tree_manifests()`, `api.reset()`, `cli.reset()`, and `cli.clean()`. |
| **30.8.2** Zero-config `ctx setup --check` local model resolution & embedding-model filtering | Completed | Filtered `*embed*` model IDs when selecting a default completion model in `detect_provider()` (with fallback when only embedding models exist) and forwarded `detected_model` into `run_preflight()` when neither `.ctxconfig` nor `CTX_MODEL` sets an explicit model. |
| **30.8.3** OpenAI-compatible `base_url` `/v1` probe normalization & preflight hints | Completed | Added `normalize_models_probe_url()` in `src/ctx/config.py`, wired it into `detect_provider()`, `probe_provider_connectivity()`, and `_probe_local_models()`, and emitted endpoint-specific preflight fix hints when custom `base_url` fails connectivity. |
| **30.8.4** Single-GPU local concurrency, immediate mid-directory batch disable, & timeout retry cap | Completed | Set `_DEFAULT_LOCAL_PARALLEL_DIRS = 1`, added thread-safe `self._batch_lock` + dynamic per-chunk `_effective_files_per_call()` loop + 1-file plain-text tolerance in `OpenAIClient`, and added `LOCAL_TIMEOUT_RETRY_ATTEMPTS = 2` in `_call_with_retries(..., is_local=True)`. |
| **30.8.5** Subcommand `--output [human\|json]` support & `ctx export --output json` collision fix | Completed | Added `_subcommand_output_option` / `_resolve_json_mode()` across canonical subcommands, added `--out-file` to `ctx export`, and routed `ctx export --output json\|human` to format selection instead of writing `./json`. |
| **30.8.6** `ctx check --check-exit` & `ctx setup --check` JSON-mode non-zero exit enforcement | Completed | Removed early `return`s inside `with OutputBroker(...)` in `cli.check`, `cli.setup`, `cli.export`, `cli.reset`, and `cli.clean` so `_exit_for_broker()` always enforces non-zero exit codes on JSON errors. |
| **30.8.7** Tier 2 (`mode: "tier2"`) awareness across `ctx check`, MCP `ctx_check`, `ctx export`, and HTTP `ctx serve` | Completed | Added `_is_tier2_repo()` and `_check_tier2()` in `src/ctx/api.py`, Tier 2 depth-aware export in `api.export_context()` / `cli.export()`, and Tier 2 root serving + `.ctx` path blocking in `src/ctx/server.py`. |
| **30.8.8** Prompt few-shot JSON array examples & redundant filename-prefix stripping | Completed | Replaced markdown bullet examples in `DEFAULT_PROMPT_TEMPLATES["file_summary_system"]` with a valid JSON array example, instructed models not to echo filenames, and added `_strip_redundant_filename_prefix()` in `src/ctx/generator.py`. |
| **30.8.9** `ctx.sdk` `hook_telemetry` alias & zero-dependency `is_stale()` | Completed | Added `CtxProject.hook_telemetry` property alias and wrapped `from ctx.skeleton import ...` in `CtxProject.is_stale()` with `ImportError` fallback. |
| **30.8.10** `pytest` global stats isolation (`CTX_GLOBAL_STATS_PATH`) | Completed | Added `CTX_GLOBAL_STATS_PATH` support in `stats_board._global_stats_path()`, set it in `tests/conftest.py`, and cleaned historical `.tmp/test-work/` entries from `~/.ctx/run_stats.json`. |

## Surprises & Root Causes

1. **Silent CI Freshness-Gate Bypass in `CTX_OUTPUT=json ctx check . --check-exit`:**
   - *Symptom:* `.github/workflows/ctx-check.yml` runs `CTX_OUTPUT=json python -m ctx check . --check-exit`, which had been passing green in CI despite 7 stale and 1 missing `CONTEXT.md` manifests in `context-project` itself.
   - *Root Cause:* Inside `with OutputBroker(...) as broker:` in `cli.check` (and `cli.setup`), an early `return` triggered `broker.__exit__` (printing the valid JSON envelope containing `errors: [{"code": "stale_manifests", ...}]`) and then returned from the Click command *before* `_exit_for_broker(broker, json_mode=json_mode)` could call `sys.exit(1)`.
   - *Fix:* Eliminated early `return`s inside `with OutputBroker(...)` blocks so `_exit_for_broker()` always runs, and refreshed all `CONTEXT.md` manifests in `context-project` so the restored CI gate passes honestly.

2. **Static Batch Step Inside `OpenAIClient.summarize_files`:**
   - *Symptom:* During live Ollama `qwen2.5:7b-instruct` dogfooding on a 19-file directory, `local_batch_fallbacks` climbed to 4 even though `_fallback_to_single_file_summaries()` set `self._local_batching_disabled = True` on the very first chunk.
   - *Root Cause:* `summarize_files()` computed `self._effective_files_per_call(len(files))` (`4`) once up front and passed that static integer into `_apply_batch_size()`, so the remaining 3 chunks in the same directory still ran as 4-file batches.
   - *Fix:* Replaced static `_apply_batch_size()` for local providers with a dynamic `while index < len(files):` loop that re-queries `self._effective_files_per_call(remaining)` on every chunk, plus thread-safe locking and 1-file plain-sentence tolerance once batching is disabled.

## Disposition Table

| Finding / Item | Disposition | Target Reference |
|----------------|-------------|------------------|
| `.ctx/` self-ingestion, `ctx init` `.gitignore` ordering, & `ctx reset` `.ctx/` deletion | **Implemented this gate** | Phase 30.8 (`30.8.1`) |
| `detect_provider` embedding-model selection & `run_preflight` `detected_model` drop | **Implemented this gate** | Phase 30.8 (`30.8.2`) |
| OpenAI-compatible `base_url` `/v1/v1/models` 404 & generic internet hint | **Implemented this gate** | Phase 30.8 (`30.8.3`) |
| Single-GPU 4-worker contention, mid-directory batch fallback loop, & 5x300s local timeout retries | **Implemented this gate** | Phase 30.8 (`30.8.4`) |
| Subcommand `--output json` support & `ctx export --output json` `./json` file collision | **Implemented this gate** | Phase 30.8 (`30.8.5`) |
| `ctx check --check-exit` & `ctx setup --check` JSON-mode exit-code 0 bug | **Implemented this gate** | Phase 30.8 (`30.8.6`) |
| Tier 2 blindness across `ctx check`, MCP `ctx_check`, `ctx export`, and HTTP `ctx serve` | **Implemented this gate** | Phase 30.8 (`30.8.7`) |
| Prompt bullet examples causing non-JSON local output & echoed `<filename>: ` prefixes | **Implemented this gate** | Phase 30.8 (`30.8.8`) |
| `ctx.sdk` `hook_telemetry` spec mismatch & `pathspec` transitive dependency in `is_stale()` | **Implemented this gate** | Phase 30.8 (`30.8.9`) |
| `pytest` polluting `~/.ctx/run_stats.json` with `.tmp/test-work/` entries | **Implemented this gate** | Phase 30.8 (`30.8.10`) |
| Optional OpenAI structured-output / constrained JSON-schema capability probe for local providers | **Carry into Phase 31** | `state.md` §Phase 31 (`31.2`) |
