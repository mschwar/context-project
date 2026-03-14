---
generated: '2026-03-14T22:42:44Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:d7ab0013ece0eb9ab6c5ebf3897ce291f429aab03a03237570717dda62cc98ce
files: 4
dirs: 0
tokens_total: 655
---
# C:/Users/Matty/Documents/context-project/.github/workflows

Contains GitHub Actions workflows that automate testing, validation, and publishing for the context-project.

## Files

- **ctx-check.yml** — GitHub Actions workflow that validates CTX manifest freshness on pushes and pull requests.
- **pr-checks.yml** — GitHub Actions workflow that runs tests and validates pull requests to main branch.
- **publish.yml** — GitHub Actions workflow that builds and publishes package to PyPI on version tags.
- **tests.yml** — GitHub Actions workflow that runs test suite across multiple OS and Python versions.

## Subdirectories

- None

## Notes

- These workflows form the CI/CD pipeline for the project, covering manifest validation, pull request checks, automated testing across environments, and package publishing.