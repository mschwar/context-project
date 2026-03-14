---
generated: '2026-03-14T06:44:44Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:0333a238af1fee76238a8b85fd9452011f247813d7da15c17ee6fdc4547875d4
files: 3
dirs: 1
tokens_total: 174
---
# ./.husky

Configuration directory for Husky git hooks that enforce commit message standards and branch protection rules.

## Files

- **commit-msg** — Git hook that validates commit messages using commitlint.
- **pre-commit** — Git hook that prevents direct commits to main or master branches.
- **pre-push** — Git hook that prevents direct pushes to main or master branches.

## Subdirectories

- **_/** — Contains git hook implementations managed by husky for automated validation and operations throughout the git workflow.

## Notes

- These hooks enforce code quality and workflow standards by intercepting git operations at key points in the development process.