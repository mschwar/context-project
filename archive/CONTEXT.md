---
generated: '2026-03-18T18:25:31Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a9634b6361a97570ab0a4db2b55fa45382fadb63be8cd9c50bf51b27f71f3351
files: 6
dirs: 1
tokens_total: 6967
---
# C:/Users/Matty/Documents/context-project/archive

This directory contains design documents, AI analysis, and planning materials for the ctx project—a Python CLI tool that generates hierarchical CONTEXT.md manifests to enable AI agents to navigate and understand directory structures without reading raw files.

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

- The archive documents the iterative design process of ctx through multiple AI model analyses (GPT, Grok, Opus), converging on a markdown+YAML format with per-directory CONTEXT.md files.
- Core architectural decision: single CONTEXT.md per directory with structured metadata enables hierarchical navigation without full file reads, supporting coarse-to-fine agent retrieval patterns.