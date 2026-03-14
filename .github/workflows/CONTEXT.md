---
generated: '2026-03-14T05:54:43Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:c036c48dd84e5ad168cc5014a4d95a093b9a59e99ec3af6d87aee0692eb347e2
files: 2
dirs: 0
tokens_total: 300
---
# C:/Users/Matty/Documents/context-project/.github/workflows

GitHub Actions workflow definitions for automated testing and validation.

## Files

- **ctx-check.yml** — GitHub Actions workflow that runs CTX manifest validation checks on pushes and pull requests to main and feature/fix branches
- **tests.yml** — GitHub Actions workflow that runs Python tests across Ubuntu and Windows with Python 3.10 and 3.12, including package installation, module verification, and manifest health checks

## Subdirectories

- None

## Notes

- Workflows are triggered on pushes and pull requests to specified branches
- Multi-platform and multi-version Python testing is configured