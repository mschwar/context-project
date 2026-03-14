---
generated: '2026-03-14T23:23:19Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:9bd85b1336ec4dcae11f47c7345e0c5a31034f82357007186ecc754ff1c01782
files: 6
dirs: 0
tokens_total: 2606
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract public APIs and exported symbols from source code files.

## Files

- **csharp_parser.py** — Extracts public types and methods from C# files using regex pattern matching.
- **go_parser.py** — Extracts exported functions, types, constants, and variables from Go files by capitalization.
- **java_parser.py** — Extracts public types and methods from Java files using regex pattern matching.
- **js_ts_parser.py** — Extracts exported functions, classes, interfaces, and types from JavaScript/TypeScript files.
- **python_parser.py** — Parses Python files using AST to extract top-level classes and functions.
- **rust_parser.py** — Extracts public functions, structs, enums, traits, and modules from Rust files.

## Subdirectories

- None

## Notes

- Each parser is tailored to its language's visibility conventions (e.g., capitalization in Go, `public` keyword in Java/C#, `export` in JS/TS).
- Python parser uses AST analysis while others rely on regex pattern matching.
- Parsers focus on extracting public/exported symbols suitable for documentation generation.