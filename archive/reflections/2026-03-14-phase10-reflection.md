# Phase 10 Reflection — Trust It (tiktoken, Cache Eviction, Transient Error Messaging)

**Date:** 2026-03-14
**Branch:** `feat/phase10-trust` (PR #25)
**Status:** Complete

---

## Successes

- **tiktoken integration** — The lazy-load pattern (`_TIKTOKEN_ENCODER = None` / `False` sentinel) is clean and correct. Falling back to `len/4` when tiktoken is unavailable preserves the existing behaviour for environments where the dep can't be installed. The `(ImportError, ValueError)` narrow catch (from Gemini) is the right scope — `tiktoken.get_encoding` raises `ValueError` for unknown encoding names, not `ImportError`.
- **Cache eviction** — The `while/del` loop using insertion-ordered dict iteration is O(n removals) with O(1) memory, better than the initial `dict(list(...)[-n:])` which materialized the full list. For a 10k-entry cache adding 1 entry, this is effectively one `del` instead of creating a 10k-element list.
- **`TRANSIENT_ERROR_PREFIX` constant** — single definition in `llm.py`, imported everywhere that uses it. Gemini's pattern (define where raised, import where caught) is the correct direction.
- **`patch()` for global state in tests** — replacing manual save/restore with `unittest.mock.patch` is cleaner and exception-safe. The test now correctly simulates the `False` sentinel without touching module state permanently.

## Friction

- **`_estimate_tokens` global state across tests** — `_TIKTOKEN_ENCODER` is a module-level global. Tests that call `_estimate_tokens` directly may interact with each other if tiktoken loads successfully in one test and sets the global. The `patch` approach in `test_estimate_tokens_falls_back_when_tiktoken_unavailable` handles this correctly, but it's worth noting the test ordering sensitivity.
- **Gemini review round** — All five Gemini suggestions were correct and implemented immediately. The pattern of Gemini catching broad `except Exception` clauses is consistent across phases. This should be a standing rule: always narrow exception clauses before submitting for review.

## Observations

- `tiktoken` downloads encoding data on first use (`cl100k_base` ~1.7MB). In CI environments without internet access, the first call will raise and fall back to the heuristic — correct behaviour, but the fallback message in the log won't indicate why. This is acceptable given the fallback is transparent.
- The `max_cache_entries` default of 10,000 is conservative. A typical large repo has 100–500 directories, each generating ~10 file cache entries — so 5,000 entries would cover most real-world cases with room to spare. 10,000 provides a 2x safety margin.
- Phases 8–10 as a group form a complete adoption arc: installable → automated → trustworthy. The project is now at a state where a non-technical founder could realistically use it.

## Suggestions

1. **Standing rule: narrow exception clauses** — add to `AGENTS.md` canonical rules: "Always catch specific exception types. `except Exception` is a code smell; use it only at top-level boundaries with explicit logging."
2. **Phase 11 candidates**:
   - **Java / C# parsers** — the only major enterprise languages without structural metadata extraction.
   - **`ctx setup --check`** — a non-destructive flag that prints the detected provider without writing a config file. Useful in CI to verify the environment is correctly configured.
   - **Streaming progress for large directories** — currently the progress callback fires per-directory; a per-file update for large directories would improve perceived responsiveness.

## Project Status

Phases 1–10 are complete. The tool is stable, installable from PyPI, self-configuring, and has 166 tests covering all modules. The adoption arc is complete.
