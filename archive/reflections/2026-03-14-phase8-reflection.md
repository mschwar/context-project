# Phase 8 Reflection — Ship It (PyPI Packaging, Publish Workflow, README)

**Date:** 2026-03-14
**Branch:** `feat/phase8-distribution` (PR #23)
**Status:** Complete

---

## Successes

- **PyPI name choice** — `ctx` returned a 404 from the PyPI JSON API, but its 2022 supply-chain history made it a poor choice. `ctx-tool` was also available and is unambiguous. Using the API to verify before committing to the name was the right call.
- **OIDC trusted publishing** — The publish workflow uses `pypa/gh-action-pypi-publish` with `id-token: write` rather than a stored API token secret. This is the modern recommended approach and requires zero ongoing secret rotation.
- **README** — The rewrite from 40 lines to ~100 lines is the right ratio. Quick start is 4 commands. Commands table is scannable. No prose paragraphs. Gemini's `claude-3-5-haiku-20241022` model name suggestion was correct — the prior name was valid but unfamiliar to most readers copying the quick start.

## Friction

- **TOML structural bug** — `[project.urls]` was inserted between `classifiers` and `dependencies`, so `dependencies` was parsed as a URL key. Resulted in `pip install` failure in CI (`project.urls.dependencies must be string`). The bug was invisible locally because the version was already installed in editable mode; CI caught it on fresh install. Root cause: inserting a table header mid-section without checking surrounding keys.
- **CTX Manifest Check failing** — Adding source files without running `ctx update .` is a recurring pattern. Every phase has hit this. The rule is documented but easy to forget under momentum.

## Observations

- The publish workflow requires a `pypi` GitHub environment to be configured with OIDC trusted publishing before the first tag push. This is a one-time manual step on PyPI and GitHub settings that is not automated and not documented yet.
- `pip install ctx-tool` installs the package as `ctx` (the CLI command name). This is correct — the PyPI distribution name and the installed command name are independent. New users might be confused if they search for `ctx` on PyPI and find `ctx-tool`.

## Suggestions

1. **Document the OIDC setup** — add a note to `CONTRIBUTING.md` or `RUNBOOK.md` describing the one-time PyPI trusted publisher configuration required before publishing a new release.
2. **Add `ctx-tool` → `ctx` mapping note to README** — a single line clarifying that `pip install ctx-tool` installs the `ctx` command would prevent confusion.

## Implications for Phase 9

- No blocking gate conditions. Phase 9 can proceed immediately.
- The OIDC setup note is small enough to include in the Phase 8 closeout rather than deferring.
