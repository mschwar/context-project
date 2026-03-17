# Phase 18 Reflection — Pre-flight Connectivity & Error Guidance

**Date:** 2026-03-16
**Branch:** `feat/phase18-preflight-connectivity`
**Tests:** 288 passing at closeout validation

---

## Successes

- Both Phase 18 deliverables implemented cleanly, directly from the Phase 17 carry-forward suggestions.
- **18.1** (Pre-flight connectivity check): `_build_generation_runtime()` in `cli.py` now calls `probe_provider_connectivity()` before the tree walk for all cloud providers. On failure the operator sees the exact error and a proxy guidance message, then the process exits 1 — no tokens are spent on a doomed refresh.
- **18.2** (Proxy guidance in transient error tip): `_echo_generation_errors()` now checks active proxy env vars (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and lowercase variants) and names them in-line when printing the transient retry tip, eliminating the need to separately run `ctx setup --check` to surface proxy hints.
- `PROXY_ENV_VARS` constant centralised to `config.py` per code review feedback, grouping it with `LOCAL_PROVIDERS` and the probe URL constants rather than scattering it in `cli.py`.
- 7 new tests cover pre-flight success/failure paths, local provider bypass, proxy guidance display, and the no-proxy-vars variant.
- 8 pre-existing tests updated to monkeypatch `probe_provider_connectivity` so they don't hit real endpoints with fake keys.

## Friction

- **Missing constants after Phase 17 merge**: `PROXY_ENV_VARS`, `ANTHROPIC_PROBE_URL`, `ANTHROPIC_API_VERSION`, and `OPENAI_DEFAULT_PROBE_BASE_URL` were referenced before being defined. Required a fix pass before tests could run.
- **8 CLI tests broke after pre-flight was wired in**: Any test that invoked `init`/`update` with a cloud provider config now hit the real probe endpoint with fake keys and failed. Each had to be updated to monkeypatch `probe_provider_connectivity`.
- **Integration test failure**: `test_ctx_init_end_to_end_creates_manifests` uses a placeholder `ANTHROPIC_API_KEY`, so the live probe call failed. Added probe patch there too.
- **`CliRunner(mix_stderr=False)` not supported**: Initial proxy guidance test used `mix_stderr=False` which this Click version does not support. Fixed by using default `CliRunner()` and checking `result.output`.

## Observations

- The pre-flight check pattern (`if provider not in LOCAL_PROVIDERS: probe → exit 1 on failure`) is clean and composable. All three generation entry points (`init`, `update`, `smart_update`) pick it up automatically via `_build_generation_runtime`.
- Centralising `PROXY_ENV_VARS` to `config.py` was the right call — it will be easy to extend (e.g. `NO_PROXY`) without touching cli logic.
- The test-patch burden for the pre-flight check is real: every CLI test that invokes a cloud provider command now needs an explicit `probe_provider_connectivity` monkeypatch. This is a fixed one-time cost and the tests are now correct, but it's worth noting for future changes to the probe signature.

## Suggestions

1. **`ctx setup --check` timeout control** — the probe currently uses the default `urllib.request` timeout; on a slow or misconfigured network it can hang for 30+ seconds. Add a short explicit timeout (e.g. 5 s) with a clear "timed out" message.
2. **Probe result caching within a session** — if a user runs `ctx init` on a large tree, the pre-flight check fires once; but `ctx smart-update` called in rapid succession would probe again each time. Cache the result in-process for the lifetime of one CLI invocation.

## Disposition Of Suggestions

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | `ctx setup --check` timeout control | Backlog — low priority, good UX polish |
| 2 | Probe result caching within a session | Backlog — not worth the complexity until proven to matter |
