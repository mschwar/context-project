---
generated: '2026-03-18T18:25:25Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:84ce36616893be32ca06d49a3ae26b18e8ef59ee2575836537c84e4e0aeee52a
files: 4
dirs: 0
tokens_total: 711
---
# C:/Users/Matty/Documents/context-project/.github/workflows

This directory contains GitHub Actions workflows that automate CI/CD processes including manifest validation, testing, pull request checks, and package publishing.

## Files

- **ctx-check.yml** — GitHub Actions workflow that validates CTX manifest freshness on pushes and pull requests.
- **pr-checks.yml** — GitHub Actions workflow that runs tests and validates pull requests to main branch.
- **publish.yml** — GitHub Actions workflow that builds and publishes package to PyPI on version tags.
- **tests.yml** — GitHub Actions workflow that runs test suite across multiple OS and Python versions.

## Subdirectories

- None

## Notes

- Workflows are triggered on different events: manifest validation on all pushes/PRs, PR checks on main branch PRs, publishing on version tags, and tests across multiple environments.
- The ctx-check.yml workflow suggests the project maintains a CTX manifest that requires freshness validation as part of the CI pipeline.