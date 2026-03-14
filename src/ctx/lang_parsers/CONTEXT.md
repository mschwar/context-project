---
generated: '2026-03-14T23:44:36Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:bf2816c76b7fee82911972b22438a5f43ad45c26fcadf13c9051bfa187c3ad13
files: 8
dirs: 0
tokens_total: 3714
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract public APIs and structural elements from source code files.

## Files

- **csharp_parser.py** — Extracts public types, methods, and properties from C# files using regex patterns.
- **go_parser.py** — Extracts exported functions, types, constants, and variables from Go files by capitalization.
- **java_parser.py** — Extracts public types and methods from Java files using regex patterns and annotation stripping.
- **js_ts_parser.py** — Extracts exported functions, classes, interfaces, and types from JavaScript/TypeScript files.
- **kotlin_parser.py** — Extracts top-level functions, classes, interfaces, objects, and enums from Kotlin files.
- **python_parser.py** — Parses Python files using AST to extract top-level classes and functions.
- **ruby_parser.py** — Extracts method, class, and module definitions from Ruby files using regex patterns.
- **rust_parser.py** — Extracts public functions, structs, enums, traits, and modules from Rust files.

## Subdirectories

- None

## Notes

- Each parser is tailored to its language's syntax and visibility conventions (e.g., capitalization in Go, public modifiers in Java/C#, AST analysis in Python).
- Parsers focus on extracting public or top-level definitions suitable for API documentation and context generation.