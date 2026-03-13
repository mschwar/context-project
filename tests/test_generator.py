"""Tests for ctx.generator — core generation engine.

Test cases to implement:
    - test_is_binary_file_text: .py, .md, .txt files detected as text.
    - test_is_binary_file_binary: .png, .exe, .xlsx files detected as binary.
    - test_format_binary_info: correct format string for various file types/sizes.
    - test_generate_tree_creates_manifests: mock LLM, run generate_tree on fixtures/sample_project,
      verify CONTEXT.md created in every directory.
    - test_generate_tree_bottom_up: verify deepest dirs processed before parents
      (mock LLM should see child summaries when processing parent).
    - test_update_tree_skips_fresh: generate, then update without changes — no LLM calls.
    - test_update_tree_regenerates_stale: generate, modify a file, update — only changed
      dir and its ancestors get regenerated.
    - test_get_status: create some manifests, delete one, modify a file — verify
      correct fresh/stale/missing classification.

Fixtures:
    Use tests/fixtures/sample_project/ which has:
        sample_project/
        ├── README.md
        ├── src/
        │   ├── main.py
        │   └── utils.py
        └── docs/
            └── guide.md
"""
