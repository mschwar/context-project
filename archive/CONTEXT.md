---
generated: '2026-03-14T21:18:22Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ffcc325517be4af26a79288f2d93da40c0d9ea8a1704fcc207baa0d655f0c33b
files: 6
dirs: 1
tokens_total: 8615
---
# C:/Users/Matty/Documents/context-project/archive

Archived design documents and analysis for ctx, a filesystem-native hierarchical manifest system enabling AI agents to navigate codebases via CONTEXT.md files.

## Files

- **AGENTS-v0-roadmap.md** — Roadmap and architecture for ctx, a Python CLI tool generating CONTEXT.md manifests for hierarchical directory navigation by AI agents.
- **Core Idea.md** — Core concept: filesystem-native hierarchical manifest system enabling coarse-to-fine agent retrieval without reading raw files.
- **GPT5.4-dump.md** — GPT analysis comparing ctx idea against existing patterns, proposing multi-level metadata schema with directory, file, and chunk indexes.
- **Grok4.2-dump.md** — Grok analysis validating ctx concept, recommending markdown+YAML format with per-directory context.txt files and auto-generation pipeline.
- **Opus4.6-plan.md** — Opus summary refining the ctx design to single CONTEXT.md per directory with YAML frontmatter and markdown body for agent navigation.
- **Opus4.6.md** — Opus evaluation and refined design for ctx: lightweight filesystem-native manifest tool with CLI commands for init, update, and status.

## Subdirectories

- **reflections/** — Archived reflections documenting lessons learned and observations from completed project phases.

## Notes

- These documents trace the evolution of the ctx concept from initial idea through multiple AI model evaluations and refinements.
- The final design converged on a single CONTEXT.md per directory with YAML frontmatter and markdown body structure.