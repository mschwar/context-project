---
generated: '2026-03-15T03:50:22Z'
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:a6440416164a8adb368c67d2c1a0e1f68fe0d578e9423b7129db87f73f9cd27b
files: 10
dirs: 0
tokens_total: 4599
---
# C:/Users/Matty/Documents/context-project/src/ctx/lang_parsers

Language-specific parsers that extract public APIs and definitions from source code files across multiple programming languages.

## Files

- **csharp_parser.py** — Extracts public types, methods, and properties from C# files using regex patterns.
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

- Each parser is tailored to its language's syntax and visibility conventions (e.g., capitalization for Go, `public` keyword for Java/C#, regex for most others, AST for Python).
- Parsers focus on extracting public or exported definitions suitable for API documentation and context generation.