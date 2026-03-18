# ctx

Filesystem-native context layer for AI agents.

`ctx` generates `CONTEXT.md` manifests for every directory in a codebase so agents can navigate with structured summaries instead of opening every file.

## Quick Start

```bash
pip install ctx-tool
export ANTHROPIC_API_KEY="sk-..."
ctx refresh .
```

Tell your agent: install `ctx-tool`, run `ctx refresh .`, then use [AGENTS.md](./AGENTS.md) as the command contract.

## Agent Docs

- [AGENTS.md](./AGENTS.md) — canonical onboarding, config, commands, error codes, and manifest schema
- [architecture.md](./architecture.md) — engine design
- [CONTRIBUTING.md](./CONTRIBUTING.md) — developer workflow
- [state.md](./state.md) — roadmap and stage status

## License

MIT
