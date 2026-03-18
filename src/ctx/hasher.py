"""Content hashing for staleness detection.

All hashes are SHA-256, hex-encoded, prefixed with "sha256:".
Example: "sha256:e3b0c44298fc1c149afbf4c8996fb924..."

Directory hash = hash of sorted(child_name:child_hash) pairs.
This means a directory hash changes if and only if its contents change.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pathspec

from ctx.ignore import should_ignore


logger = logging.getLogger(__name__)


def _sentinel_hash(label: str) -> str:
    return f"sha256:{hashlib.sha256(f'ctx:{label}'.encode('utf-8')).hexdigest()}"


ERROR_HASH = _sentinel_hash("error")
SYMLINK_LOOP_HASH = _sentinel_hash("symlink-loop")


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
        4. On read error, log and return a stable error sentinel hash.
    """
    try:
        payload = path.read_bytes()
    except OSError as exc:
        logger.warning("Failed to hash file %s: %s", path, exc)
        return ERROR_HASH

    # Normalize text line endings so manifest freshness is stable across
    # Windows (CRLF) and POSIX (LF) checkouts of the same git content.
    if b"\x00" not in payload:
        try:
            normalized = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            payload = normalized

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _path_identity(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except (OSError, RuntimeError):
        return str(path.absolute())


def _hash_directory(
    path: Path,
    spec: pathspec.PathSpec,
    target_root: Path,
    active_paths: set[str],
) -> str:
    identity = _path_identity(path)
    if identity in active_paths:
        logger.warning("Detected recursive symlink loop while hashing %s", path)
        return SYMLINK_LOOP_HASH

    active_paths.add(identity)
    try:
        try:
            children = sorted(path.iterdir(), key=lambda child: child.name)
        except OSError as exc:
            logger.warning("Failed to list directory %s: %s", path, exc)
            return ERROR_HASH

        combined: list[str] = []
        for child in children:
            if should_ignore(child, spec, target_root):
                continue

            try:
                is_directory = child.is_dir()
            except OSError as exc:
                logger.warning("Failed to inspect path %s: %s", child, exc)
                child_hash = ERROR_HASH
            else:
                if is_directory:
                    child_hash = _hash_directory(child, spec, target_root, active_paths)
                else:
                    child_hash = hash_file(child)

            combined.append(f"{child.name}:{child_hash}\n")

        digest = hashlib.sha256("".join(combined).encode("utf-8"))
        return f"sha256:{digest.hexdigest()}"
    finally:
        active_paths.remove(identity)


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
        4. Detect recursive directory cycles and substitute a stable sentinel hash.
        5. Build string: "childname:childhash\\n" for each child, sorted.
        6. SHA-256 that combined string.
        7. Return f"sha256:{hexdigest}".
    """
    return _hash_directory(path, spec, target_root, set())


def is_stale(manifest_hash: str, current_hash: str) -> bool:
    """Compare stored content_hash from a CONTEXT.md against the current hash.

    Returns True if they differ (manifest is stale).
    """
    return manifest_hash != current_hash
