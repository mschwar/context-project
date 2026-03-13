"""Tests for ctx.hasher — file and directory content hashing.

Test cases to implement:
    - test_hash_file_basic: hash a known file, verify deterministic output.
    - test_hash_file_empty: empty file produces a valid hash.
    - test_hash_file_binary: binary file hashes correctly.
    - test_hash_directory_basic: directory with files produces stable hash.
    - test_hash_directory_ignores_patterns: ignored files don't affect hash.
    - test_hash_directory_order_independent: same files in any OS order = same hash
      (because we sort by name).
    - test_is_stale_different: different hashes = stale.
    - test_is_stale_same: same hashes = not stale.
"""
