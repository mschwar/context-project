# Memo: The Agent-First Thesis
**Date:** March 17, 2026
**Subject:** Transitioning `ctx` from Developer Tool to Agent Infrastructure

## The Core Insight
Currently, `ctx` is designed as a CLI tool for human developers to help their AI agents. This is fundamentally the wrong direction. The most successful software layers are often invisible to the end-user—installed as prerequisites, daemons, or implicit dependencies. 

**The human should not be the user of `ctx`. The user is the agent.**

We need to make `ctx` an "Agent-First" infrastructure. If an agent lands in a repository, it should be able to autonomously discover, install, configure, utilize, and maintain the `ctx` layer without human intervention. 

## The Paradigm Shift
* **From Interactive to Autonomous:** Agents stumble on interactive prompts, `y/n` confirmations, and complex auth flows. Everything must become declarative, idempotent, and self-healing.
* **From Pretty to Dense:** Human-readable tables (like `ctx stats`) waste tokens. Output must optimize for high signal-to-noise density to save context windows.
* **From Manual to Standardized Protocol:** Humans shouldn't have to remember to run `ctx update`. Agents should execute a contextual "closeout" as naturally as they execute a `git commit`.

## North Star Metrics
To measure the success of this overhaul, we will track:
1. **Tokens Saved Per Task:** How much context window is preserved because the agent navigates via `ctx` instead of raw file reads.
2. **Task Speedup:** Time-to-resolution reduction because the agent's first 30 seconds in a repo are guided by an accurate map.
3. **Improved Outcomes (Machine-Rated):** Code correctness, architectural alignment, and fewer hallucinations.
4. **Improved Outcomes (Human-Rated):** Subjective quality of the PR/commit.

By pivoting to an Agent-First model, we stop competing for human mindshare and start capturing Agent Runtime—a massive, rapidly expanding frontier.
