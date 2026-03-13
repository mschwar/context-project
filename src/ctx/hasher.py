"""Content hashing for staleness detection.

All hashes are SHA-256, hex-encoded, prefixed with "sha256:".
Example: "sha256:e3b0c44298fc1c149afbf4c8996fb924..."

Directory hash = hash of sorted(child_name:child_hash) pairs.
This means a directory hash changes if and only if its contents change.
"""

from __future__ import annotations

from pathlib import Path

import pathspec


def hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents.

    Args:
        path: Absolute path to the file.

    Returns:
        Hash string like "sha256:abc123...".

    Implementation:
        1. Read file in binary mode, chunked (8KB chunks).
        2. Feed chunks to hashlib.sha256().
        3. Return f"sha256:{digest.hexdigest()}".
        4. On read error (permission, encoding), return "sha256:error".
    """
    raise NotImplementedError


def hash_directory(
    path: Path,
    spec: pathspec.PathSpec,
    target_root: Path,
) -> str:
    """Compute a stable hash for a directory based on its children's hashes.

    Args:
        path: Absolute path to the directory.
        spec: Ignore spec (skip ignored children).
        target_root: Root for relative path computation in ignore matching.

    Returns:
        Hash string like "sha256:def456...".

    Implementation:
        1. List immediate children (files + dirs), sorted by name.
        2. Filter out ignored paths using spec.
        3. For each child: if file, hash_file(); if dir, hash_directory() (recursive).
        4. Build string: "childname:childhash\\n" for each child, sorted.
        5. SHA-256 that combined string.
        6. Return f"sha256:{hexdigest}".
    """
    raise NotImplementedError


def is_stale(manifest_hash: str, current_hash: str) -> bool:
    """Compare stored content_hash from a CONTEXT.md against the current hash.

    Returns True if they differ (manifest is stale).
    """
    return manifest_hash != current_hash
