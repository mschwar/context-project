---
generated: '2026-03-15T04:04:29Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:8427e1a5aaf7a82e7a6b4a28f36e9a59bad0ed49499d566f6ced1500b5e97284
files: 6
dirs: 1
tokens_total: 6967
---
# C:/Users/Matty/Documents/context-project/archive

Archive of design documents, analyses, and roadmaps for the ctx project—a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.

## Files

- **AGENTS-v0-roadmap.md** — Roadmap and architecture for ctx, a Python CLI tool generating CONTEXT.md manifests for hierarchical directory navigation by AI agents.
- **Core Idea.md** — Core concept: filesystem-native hierarchical manifest system enabling coarse-to-fine agent retrieval without reading raw files.
- **GPT5.4-dump.md** — GPT analysis comparing ctx idea against existing patterns, proposing multi-level metadata schema with directory, file, and chunk indexes.
- **Grok4.2-dump.md** — Grok analysis validating ctx concept, recommending markdown+YAML format with per-directory context.txt files and auto-generation pipeline.
- **Opus4.6-plan.md** — Opus summary refining the ctx design to single CONTEXT.md per directory with YAML frontmatter and markdown body for agent navigation.
- **Opus4.6.md** — Opus evaluation and refined design for ctx: lightweight filesystem-native manifest tool with CLI commands for init, update, and status.

## Subdirectories

- **reflections/** — A collection of phase-by-phase project reflections documenting the evolution, achievements, and recommendations across development cycles.

## Notes

- This directory contains historical design iterations and AI model evaluations that informed the final ctx architecture.
- Multiple model analyses (GPT, Grok, Opus) converged on a markdown+YAML format with per-directory CONTEXT.md files.