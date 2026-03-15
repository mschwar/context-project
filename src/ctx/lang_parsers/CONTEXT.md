---
generated: '2026-03-15T04:39:00Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:d19fb41304f33136a9352a92b332d5ddb714832fc91e348f38e0b460b1cff6a3
files: 11
dirs: 0
tokens_total: 5211
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract public APIs and structural elements from source files across multiple programming languages.

## Files

- **csharp_parser.py** — Extracts public types, methods, and properties from C# files using regex patterns.
- **elixir_parser.py** — Parses Elixir source files to extract public functions, modules, structs, types, specs, and callbacks.
- **go_parser.py** — Extracts exported functions, types, constants, and variables from Go files by capitalization.
- **java_parser.py** — Extracts public types and methods from Java files using regex patterns and annotation stripping.
- **js_ts_parser.py** — Extracts exported functions, classes, interfaces, and types from JavaScript/TypeScript files.
- **kotlin_parser.py** — Extracts top-level functions, classes, interfaces, objects, and enums from Kotlin files.
- **php_parser.py** — Parses PHP files to extract public functions, classes, interfaces, traits, and enums using regex patterns.
- **python_parser.py** — Parses Python files using AST to extract top-level classes and functions.
- **ruby_parser.py** — Extracts method, class, and module definitions from Ruby files using regex patterns.
- **rust_parser.py** — Extracts public functions, structs, enums, traits, and modules from Rust files.
- **swift_parser.py** — Parses Swift files to extract top-level functions, classes, structs, protocols, and enums using regex patterns.

## Subdirectories

- None

## Notes

- Each parser is tailored to its language's syntax and visibility conventions (e.g., capitalization in Go, public keyword in Java/C#, module exports in JavaScript/TypeScript).
- Parsers use a mix of regex-based and AST-based approaches depending on language complexity.
- These modules likely share a common interface for integration with the broader context-project system.