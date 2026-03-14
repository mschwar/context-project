---
generated: '2026-03-14T21:12:25Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:7d0005661a8ae7aae42006164369b810c5474de7620412b53de1d2ddfe406a6b
files: 3
dirs: 0
tokens_total: 1030
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract structural information from source code files across multiple programming languages.

## Files

- **js_ts_parser.py** — Parses JavaScript/TypeScript files to extract exported functions, classes, interfaces, types, and default exports.
- **python_parser.py** — Parses Python files using AST to extract top-level class and function definitions.
- **rust_parser.py** — Parses Rust files to extract public functions, structs, enums, traits, and module declarations.

## Subdirectories

- None

## Notes

- Each parser module is tailored to its language's syntax and conventions, enabling consistent extraction of public APIs and structural definitions across heterogeneous codebases.