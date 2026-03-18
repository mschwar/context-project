# Comprehensive Plan: The Agent-First Overhaul

> **Historical Document** — This is an earlier draft of the AFO strategy, preserved for reference.
> The canonical implementation plan is `AGENT_FIRST_OVERHAUL.md` at the repo root.
> The canonical spec suite is in `docs/afo/` (8 documents, spec numbers 00–07).

This document outlines the tactical and strategic roadmap for overhauling `ctx` from a human-centric CLI tool to an autonomous, agent-first infrastructure layer.

---

## Stage 1: Discovery & Bootstrapping (Find & Install)
**Goal:** Make it trivial for an agent to realize `ctx` exists, learn how to use it, and install it autonomously.

* **Agent-Native Discovery:** Create a standard like `.well-known/agent-instructions.md` or utilize `llms.txt` to broadcast: *"This repo uses `ctx`. To navigate, run `ctx serve` or read `CONTEXT.md` files."*
* **Zero-Friction Setup:** Refactor `ctx setup` to `ctx doctor --auto-fix`. Agents cannot handle interactive prompts. The tool must autonomously detect the environment, probe local/cloud LLMs, write the `.ctxconfig`, and handle proxy/auth issues silently.
* **Self-Bootstrapping Documentation:** Ship a `ctx instructions` command that emits a pre-optimized "System Prompt" block. An agent can run this command to teach itself how to use the tool.

---

## Stage 2: Execution & Output (Read & Run)
**Goal:** Optimize the tool's runtime specifically for token-efficiency and machine parsing.

* **Agent-Optimized Output:** Introduce a global `--format agent` (or make it the default). This strips UI colors, progress bars, and ASCII tables, replacing them with dense, structural summaries (e.g., JSON or highly compact markdown).
* **Cost/Token Awareness:** Agents must be able to reason about budgets. `ctx` commands will output exact token estimations *before* execution, allowing agents to halt if they exceed their allotted budget.
* **Smart Fallbacks:** If an agent executes a malformed `ctx` command, the error output must explicitly state *how* to fix the command, rather than just throwing a stack trace.

---

## Stage 3: The Maintenance Protocol (Deploy & Maintain)
**Goal:** Formalize `ctx` as a mandatory part of an agent's lifecycle (The Protocol of the PR).

* **The `ctx closeout` Command:** A single, unified command that an agent runs at the end of its session. It combines:
  1. `ctx update .` (regenerate stale manifests)
  2. `ctx verify .` (ensure no malformed/missing manifests)
  3. Emit a summary of changes to be appended to a PR description.
* **Git-Hooks as Agent Guardrails:** Expand the Husky/pre-commit hooks to specifically intercept *agent* commits, ensuring they cannot push code without updating the context layer.

---

## Stage 4: The Full Overhaul (Repository & Docs)
**Goal:** Rip out the human-first assumptions across the entire codebase.

* **Doc Rewrite:** Invert the `README.md`. The primary audience is now the AI agent reading it via `curl` or `web_fetch`. Human installation instructions go to the bottom; agent integration instructions go to the top.
* **Agent-centric Architecture:** Update `architecture.md` and `rules.md` to define the "Agentic SDLC" as the primary workflow, enforcing that agents are the maintainers of the repo.
* **CLI UX Demotion:** We will retain human-friendly commands (for debugging), but they will become wrappers around the core agentic API.

---

## Stage 5: Second-Order Post-Overhaul Changes
**Goal:** Handle the downstream effects of agents running `ctx` wildly in the real world.

* **Hard Economic Guardrails:** If agents control `ctx`, they control the API billing. We must implement hard budget locks (e.g., `max_usd_per_run: 5.00` in `.ctxconfig`) that cannot be overridden via CLI flags by the agent itself.
* **Agent Feedback Loops:** Create a mechanism where an agent can flag a `CONTEXT.md` file as "low quality" or "hallucinated", triggering `ctx` to refine its internal prompt templates for that specific directory archetype.
* **Standardized Context Payloads:** Export standard payloads tailored for specific agent frameworks (e.g., Aider, Claude Code, Gemini CLI) so `ctx` becomes the universal translation layer between the filesystem and any framework.
