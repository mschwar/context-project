❯ read 'core idea'. we're going to build this out and deploy it on my two machines (one mac one windows) as proof of concept. you are the
 lead and partner. evaluate the idea. what works? how can it be improved? improve it, make revisions and refinements to the idea seed,
and then give me a clear overview and leveraged next steps.

● Let me find and read the "core idea" file.

● Searched for 3 patterns, read 3 files (ctrl+o to expand)

● I've read all three files. Let me give you my honest evaluation and a refined direction, then write up the build plan.

  ---
  Evaluation

  What's genuinely strong

  The core insight is real and underserved: agents waste massive context windows crawling raw files. A filesystem-native hierarchical
  manifest that enables coarse-to-fine navigation is the right primitive. Nobody has built this well yet.

  What exists today is fragmented:
  - llms.txt — web-only, single root file, no hierarchy
  - CLAUDE.md / .cursorrules — tool-specific, single file, code-only
  - Aider repo maps — ephemeral, code-only, not persistent
  - RAG systems — require vector DBs, not filesystem-native
  - Repomix/Gitingest — flatten everything (opposite of progressive disclosure)

  Your gap is real: persistent, hierarchical, per-directory manifests for any content type, navigable by any agent, no external
  infrastructure. That's new.

  What's wrong with both AI responses

  GPT over-engineered it. 50+ fields across 4 levels, three separate files per directory (README + manifest.json + summary.md +
  chunks.jsonl + relations.jsonl + refresh.log.jsonl). That's a schema for a database product, not a filesystem convention. Nobody will
  adopt something that heavy.

  Grok was closer but still fuzzy. The markdown format is right, but the spec is loose, and the "just use LlamaIndex/RAPTOR" advice punts
  on the hard part — the generation pipeline IS the product.

  Both missed the key insight: the value isn't in the format spec, it's in the tool that generates and maintains the manifests
  automatically. A perfect schema that nobody generates is worthless. A simple format with a one-command generator wins.

  My refined take

  One file per directory. Markdown with YAML frontmatter. One CLI tool to generate and maintain them.

  That's it. Everything else is premature optimization.

  ---
  Refined Design: ctx

  Format: CONTEXT.md per directory (uppercase like README.md — visible, conventional)

  ---
  generated: 2026-03-13T10:00:00Z
  generator: ctx/0.1.0
  content_hash: sha256:abc123
  files: 12
  dirs: 3
  tokens_total: 48000
  ---
  # /project/src

  Backend API server for the widget platform. Handles auth, data access, and webhook delivery.

  ## Files
  - **server.py** — Express-style HTTP server setup, middleware chain, port config
  - **auth.py** — JWT validation, role-based access, session management
  - **models.py** — SQLAlchemy models for User, Widget, Event tables

  ## Subdirectories
  - **routes/** — API endpoint handlers grouped by resource (users, widgets, events)
  - **middleware/** — Request logging, rate limiting, CORS configuration
  - **tests/** — Pytest suite, 84% coverage, focused on auth and webhook flows

  ## Notes
  - Auth is migrating from session-based to JWT (in progress, see auth.py L45-80)
  - Webhook retry logic lives in routes/webhooks.py, not in a separate service

  Why this works:
  - YAML frontmatter = machine metadata (staleness detection, token budgeting)
  - Markdown body = progressive disclosure (title → one-liner → files → subdirs → notes)
  - Single file = simple to generate, version, diff, read
  - Agent reads top-down, stops when it has enough info to decide: drill deeper or skip

  The CLI tool ctx:
  - ctx init <dir> — Generate CONTEXT.md files recursively
  - ctx update <dir> — Regenerate only stale files (hash mismatch)
  - ctx status — Show which manifests are stale/missing
  - ctx query "question" — Navigate the tree to answer a question (stretch goal)

  Tech stack: Python + Click + Anthropic API. No vector DB, no external deps beyond the LLM call.