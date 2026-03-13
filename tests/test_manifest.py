"""Tests for ctx.manifest — CONTEXT.md read/write/parse.

Test cases to implement:
    - test_write_and_read_roundtrip: write a manifest, read it back, verify all fields.
    - test_read_missing_manifest: reading from dir without CONTEXT.md returns None.
    - test_frontmatter_fields: verify all frontmatter fields are correctly serialized/parsed.
    - test_body_preserved: markdown body survives write/read cycle exactly.
    - test_timestamp_format: generated timestamp is valid ISO 8601 UTC.
"""
