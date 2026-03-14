---
generated: '2026-03-14T21:12:28Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:5c1d26a37addb53d70f6c7008dde6778105eee51e5ec8e588f61d2b13f332b2d
files: 3
dirs: 0
tokens_total: 473
---
# C:/Users/Matty/Documents/context-project/.github/workflows

GitHub Actions workflow definitions for automated testing, validation, and manifest checks.

## Files

- **ctx-check.yml** — GitHub Actions workflow that validates CTX manifest freshness on pushes and pull requests.
- **pr-checks.yml** — GitHub Actions workflow that runs pytest tests and validates pull requests to main branch.
- **tests.yml** — GitHub Actions workflow that tests package across multiple OS and Python versions with manifest verification.

## Subdirectories

- None

## Notes

- These workflows automate CI/CD processes including test execution, manifest validation, and pull request checks across multiple environments.