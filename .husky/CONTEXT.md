---
generated: '2026-03-18T18:25:33Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:1d26177144e9831bcaa5b36aa7df67228e20cd02b16fa727237ecdf62c162bc9
files: 3
dirs: 0
tokens_total: 200
---
# C:/Users/Matty/Documents/context-project/.husky

This directory contains Git hooks that enforce code quality standards and branching workflows through automated validation at commit and push stages.

## Files

- **commit-msg** — Git hook validating commit messages against conventional commit standards using commitlint.
- **pre-commit** — Git hook preventing direct commits to main or master branches, enforcing feature branch workflow.
- **pre-push** — Git hook preventing direct pushes to main or master branches, requiring pull request workflow.

## Subdirectories

- None

## Notes

- These hooks work together to enforce a pull request-based workflow: commits are restricted to feature branches, commit messages must follow conventional commit format, and pushes to protected branches are blocked.
- Husky manages these Git hooks, ensuring they are installed and executed consistently across all developer environments.