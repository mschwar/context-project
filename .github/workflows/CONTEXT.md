---
generated: '2026-03-14T06:44:35Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:d09b454db1ba7c5db9de25f7ae65de19bcee208dfa679bc1be518d62833d77b1
files: 3
dirs: 0
tokens_total: 452
---
# C:/Users/Matty/Documents/context-project/.github/workflows

Contains GitHub Actions workflow definitions that automate validation, testing, and quality checks for the project.

## Files

- **ctx-check.yml** — GitHub Actions workflow that validates CTX manifest files on push and pull requests.
- **pr-checks.yml** — GitHub Actions workflow that runs Node.js build and test checks on pull requests to main branches.
- **tests.yml** — GitHub Actions workflow that tests Python package across multiple OS and Python versions with pytest.

## Subdirectories

- None

## Notes

- These workflows provide continuous integration for manifest validation, Node.js builds, and cross-platform Python testing.