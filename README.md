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

## Usage

```bash
ctx init ./path/to/project
ctx update ./path/to/project
ctx status ./path/to/project
```
