---
generated: '2026-03-18T18:25:31Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:5afc0e54b6b49a5385aa3858670ecfbf72c363d21eaa4eb0203d8c782417e21f
files: 1
dirs: 0
tokens_total: 40
---
# C:/Users/Matty/Documents/context-project/.githooks

This directory contains Git hooks that enforce automated testing and code quality checks before commits are made to the repository.

## Files

- **pre-commit** — Git pre-commit hook that runs pytest with quiet output and short traceback format before commits.

## Subdirectories

- None

## Notes

- The pre-commit hook enforces test passage as a gating mechanism for commits, reducing the likelihood of broken code entering the repository.
- This hook should be installed into the Git hooks directory (typically `.git/hooks/`) to be active; consider documenting setup instructions in the project README.