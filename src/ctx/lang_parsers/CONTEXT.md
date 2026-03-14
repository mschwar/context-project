---
generated: '2026-03-14T21:40:27Z'
generator: ctx/0.1.0
model: claude-haiku-4-5-20251001
content_hash: sha256:98b2fb1502247120df822ec95dba5bc98921fce82518fcc5e02b530e79593a0c
files: 4
dirs: 0
tokens_total: 1478
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract exported symbols and definitions from source files across multiple programming languages.

## Files

- **go_parser.py** — Parses Go source files to extract exported functions, types, constants, and variables based on capitalization rules.
- **js_ts_parser.py** — Parses JavaScript/TypeScript files to extract exported functions, classes, interfaces, types, and default exports.
- **python_parser.py** — Parses Python files using AST to extract top-level class and function definitions.
- **rust_parser.py** — Parses Rust files to extract public functions, structs, enums, traits, and module declarations.

## Subdirectories

- None

## Notes

- Each parser is tailored to its language's syntax and export conventions (e.g., Go capitalization, Python AST, Rust visibility modifiers).
- Parsers likely share a common interface or base class for consistent integration with the broader context extraction system.