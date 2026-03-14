---
generated: '2026-03-14T23:33:55Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:d662e7ea9025706f8534d16cee2b5d030446b167ed6152594a8ccdb06688cd3a
files: 6
dirs: 0
tokens_total: 2610
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract public APIs and declarations from source code files.

## Files

- **csharp_parser.py** — Extracts public types and methods from C# files using regex pattern matching.
- **go_parser.py** — Extracts exported functions, types, constants, and variables from Go files by capitalization.
- **java_parser.py** — Parses Java files to extract public type declarations and method signatures using regex patterns.
- **js_ts_parser.py** — Extracts exported functions, classes, interfaces, and types from JavaScript/TypeScript files.
- **python_parser.py** — Parses Python files using AST to extract top-level classes and functions.
- **rust_parser.py** — Extracts public functions, structs, enums, traits, and modules from Rust files.

## Subdirectories

- None

## Notes

- Each parser is tailored to its language's visibility conventions (e.g., capitalization in Go, `public` keyword in Java/C#, `export` in JS/TS).
- Python parser uses AST analysis while others rely on regex pattern matching.
- Parsers focus on extracting public or exported declarations for API documentation purposes.