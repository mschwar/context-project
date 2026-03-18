---
generated: '2026-03-18T08:19:41Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ff81727f87c6f8b860126e0dcdf7b13b94ca90e90422dae54f66d863ff197645
files: 6
dirs: 1
tokens_total: 6967
---
# C:/Users/Matty/Documents/context-project/archive

This directory contains design documents, AI analysis, and planning materials for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.

## Files

- **AGENTS-v0-roadmap.md** — Roadmap and architecture for ctx, a Python CLI tool generating CONTEXT.md manifests for hierarchical directory navigation by AI agents.
- **Core Idea.md** — Core concept: filesystem-native hierarchical manifest system enabling coarse-to-fine agent retrieval without reading raw files.
- **GPT5.4-dump.md** — GPT analysis comparing ctx idea against existing patterns, proposing multi-level metadata schema with directory, file, and chunk indexes.
- **Grok4.2-dump.md** — Grok analysis validating ctx concept, recommending markdown+YAML format with per-directory context.txt files and auto-generation pipeline.
- **Opus4.6-plan.md** — Opus summary refining the ctx design to single CONTEXT.md per directory with YAML frontmatter and markdown body for agent navigation.
- **Opus4.6.md** — Opus evaluation and refined design for ctx: lightweight filesystem-native manifest tool with CLI commands for init, update, and status.

## Subdirectories

- **reflections/** — This directory contains phase-by-phase reflection documents tracking the evolution, achievements, and recommendations across the context-project development lifecycle.

## Notes

- This archive represents the ideation and design phase of the ctx project, with multiple AI model analyses (GPT, Grok, Opus) converging on a markdown+YAML manifest format.
- The progression from "Core Idea" through various model evaluations to "Opus4.6" shows iterative refinement toward a single CONTEXT.md-per-directory standard.
- Cross-reference the reflections/ subdirectory for phase-level summaries and lessons learned during development.