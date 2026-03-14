# Gate Closeout Protocol

This document defines the required closeout sequence for every roadmap phase (or "gate") in the project.

## Rule

A phase/gate is not complete until its closeout steps have been executed.

Completion requires:

1. deliverables created and validated,
2. reflection written,
3. feasible in-scope reflection suggestions implemented or explicitly deferred,
4. any resulting doc or decision updates applied,
5. roadmap status updated,
6. end-of-gate report delivered to the founder.

## Required Closeout Steps

### 1. Validate the output

Confirm that the phase's stated exit criteria in the project's roadmap are met. Ensure tests pass and the application still builds (`npm run dev` and `npm run build` succeed).

### 2. Pause and reflect

Do not immediately move to the next phase. Explicitly review:
- what succeeded
- what friction was encountered
- what changed because of technical or product realities
- what should be corrected before the next phase

### 3. File a reflection artifact

Create a dated artifact under `archive/reflections/` using this pattern:
`YYYY-MM-DD-phaseN-reflection.md`

Each reflection should include:
- successes
- friction points
- observations
- suggestions
- implications for the next phase

### 4. Implement suggestions by default

Implement any reflection suggestion that is in scope, low-risk, and hardens the current deliverables. If a suggestion is not implemented, record why (out of scope, blocked, too risky, deferred).

### 5. Carry unactioned suggestions into the next gate (mandatory)

At the end of every reflection, produce a **Disposition table** — one row per suggestion, each marked either "Implemented this gate" or "Carry into Phase N". Then:

1. Open `AGENTS.md` and `state.md`.
2. For every suggestion marked "Carry into Phase N", add it as a numbered deliverable under that phase's section.
3. If Phase N does not yet exist, create a stub section for it.

This step is **not optional**. Suggestions that are not explicitly carried forward or explicitly deferred are considered lost. The carry-forward is the automation — it must happen before the gate can be marked closed.

**Checklist before closing any gate:**
- [ ] Reflection disposition table is complete (no row left blank).
- [ ] Every "carry" item appears verbatim in the target phase's scope in `AGENTS.md` and `state.md`.
- [ ] No suggestion is silently dropped.

### 6. Update durable docs

Update architecture, schema, instruction files, or runbooks if the reflection changes standing guidance.

### 6. Update the roadmap

Mark the phase as completed in the project's progress tracker and roadmap.

### 7. Deliver the report and await disposition

Provide an end-of-gate report. The default founder dispositions are:
- make changes
- roll back specific changes
- commit and proceed

**Do not commit or push automatically at gate closeout.** 

Only after receiving a "commit and proceed" disposition should you:
1. run relevant validation and hashing,
2. `git add` the intended changes,
3. `git commit` with a scoped message,
4. `git push`,
5. report the resulting commit hash before continuing.
