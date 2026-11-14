# Gate Closeout Protocol

Required verification and closeout sequence before landing any roadmap wave or release in `ctx`.

## Completion Criteria

A wave or release gate is complete when:

1. Code and documentation changes are verified locally in an isolated git branch or worktree.
2. Full `pytest` and stdlib documentation hygiene checks pass with zero untracked `.ctx/` or `.ctx-cache/` residue.
3. Control-plane state (`state.md` and `TODOS.md`) and user/agent docs (`AGENTS.md`, `README.md`, `architecture.md`, `RUNBOOK.md`) match the shipped behavior.
4. Any dated phase reflection or superseded design document is filed under `archive/` (or `archive/reflections/`).

## Required Closeout Steps

### 1. Run Proportional and Structural Verification

Execute from the candidate checkout:

```bash
python -m pytest -q
python3 -m unittest tests/test_doc_hygiene.py -v
CTX_OUTPUT=json python -m ctx init .
CTX_OUTPUT=json python -m ctx check . --verify --check-exit
CTX_OUTPUT=json python -m ctx impact --git-diff origin/main .
CTX_OUTPUT=json python -m ctx uninit .
git status --short
```

Confirm `git status --short` shows only intentional tracked changes and zero `.ctx/` or `.ctx-cache/` leftovers.

### 2. Reconcile Documentation and Trackers

1. Keep `state.md` concise (`<= 150` lines) and accurate to the current release.
2. Record completed waves and carry forward deferred items in `TODOS.md` (do not place backlog items in `AGENTS.md`, which is a strict schema-validated command contract).
3. Update `AGENTS.md`, `README.md`, `architecture.md`, and `RUNBOOK.md` whenever CLI flags, MCP schemas, `.ctx/` artifacts, or supported languages change.

### 3. Archive Historical Artifacts

Move superseded design specs or phase reflections into `archive/` (`archive/reflections/YYYY-MM-DD-<wave>-reflection.md`) so root governance docs stay high-signal and retired files do not pollute `.ctx/CONTEXT-0.md`.

### 4. Land via Pull Request Merge Gate

1. Commit and push the verified branch to `origin`.
2. Open a pull request against `main` and confirm `"GitGuardian Security Checks"` passes on the exact 40-character `HEAD` SHA (`ops/merge-policy.json`).
3. Merge cleanly, fast-forward the primary `main` checkout, and remove temporary worktrees.
