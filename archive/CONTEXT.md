---
generated: '2026-03-14T05:54:58Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:ee213a05d78bc3eb137d3f9d9fc0411b802a978ede1463545542ede4e002613b
files: 6
dirs: 0
tokens_total: 8615
---
# C:/Users/Matty/Documents/context-project/archive

Design documents and analysis for ctx, a Python CLI tool that generates hierarchical CONTEXT.md manifest files for directory trees to enable AI agent navigation of codebases.

## Files

- **AGENTS-v0-roadmap.md** — Roadmap and architecture specification for ctx, a Python CLI tool that generates CONTEXT.md manifest files for directory trees to enable AI agents to navigate codebases hierarchically without reading raw files.
- **Core Idea.md** — High-level concept document proposing a filesystem-native hierarchical manifest system for coarse-to-fine retrieval, treating files as self-contained conversations and enabling agent-first navigation without external vector databases.
- **GPT5.4-dump.md** — Detailed analysis comparing the proposed idea against existing patterns (llms.txt, RAPTOR, repo maps) and recommending a multi-resolution index with four levels (corpus, directory, file, section) plus multiple compact views for each artifact.
- **Grok4.2-dump.md** — Alternative analysis proposing context.txt as a lightweight markdown manifest with YAML metadata, agent guidelines, and file/directory summaries, emphasizing filesystem-native design inspired by llms.txt and ProtoContext specifications.
- **Opus4.6-plan.md** — Executive summary and refined plan for building ctx as a proof-of-concept tool, emphasizing simplicity (one CONTEXT.md file per directory with YAML frontmatter and markdown body) over complex schemas, with clear build phases and deployment strategy.
- **Opus4.6.md** — Evaluation and refined design document establishing ctx as a single-file-per-directory solution using markdown with YAML frontmatter, rejecting over-engineered multi-file schemas in favor of a simple CLI tool that generates and maintains manifests automatically.

## Subdirectories

- None

## Notes

- This archive contains design iterations and analysis documents exploring different approaches to hierarchical manifest generation for AI-agent-friendly codebase navigation.