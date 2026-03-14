# ctx

`ctx` generates `CONTEXT.md` manifests for directories in a project tree so AI
agents can navigate codebases coarse-to-fine without reading every raw file.

## Install

For users:

```bash
pip install .
```

For developers:

```bash
pip install -e ".[dev]"
```

On Windows, `pip --user` may place `ctx.exe` under
`%APPDATA%\Python\Python312\Scripts`. If that directory is not on `PATH`, use
`python -m ctx` or add the Scripts directory to `PATH`.

## Agentic SDLC

`ctx` is built with an **Agentic Software Development Life Cycle**. 

- [Architecture](./architecture.md) — The bottom-up context strategy.
- [Rules](./rules.md) — Engineering standards for humans and agents.
- [State](./state.md) — Current development health and roadmap.
- [Contributing](./CONTRIBUTING.md) — How to participate in the agentic workflow.

## Usage

```bash
ctx init ./path/to/project
ctx update ./path/to/project
ctx status ./path/to/project
```
