"""CONTEXT.md read/write/parse.

File format:
    ---
    generated: 2026-03-13T10:00:00Z
    generator: ctx/0.1.0
    model: claude-haiku-4-5-20251001
    content_hash: sha256:abc123...
    files: 12
    dirs: 3
    tokens_total: 48000
    ---
    # /path/to/directory

    One-line purpose summary.

    ## Files
    - **file.py** — summary
    - **data.bin** — [binary: type, 234KB]

    ## Subdirectories
    - **subdir/** — summary

    ## Notes
    - optional agent hints
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from ctx import __version__


@dataclass
class ManifestFrontmatter:
    """Parsed YAML frontmatter from a CONTEXT.md file."""

    generated: str = ""
    generator: str = f"ctx/{__version__}"
    model: str = ""
    content_hash: str = ""
    files: int = 0
    dirs: int = 0
    tokens_total: int = 0


@dataclass
class Manifest:
    """Full parsed CONTEXT.md."""

    frontmatter: ManifestFrontmatter
    body: str  # Everything after the frontmatter closing ---


def read_manifest(path: Path) -> Optional[Manifest]:
    """Read and parse an existing CONTEXT.md file.

    Args:
        path: Path to the directory (will look for path/CONTEXT.md).

    Returns:
        Parsed Manifest, or None if CONTEXT.md doesn't exist.

    Implementation:
        1. Check if path / "CONTEXT.md" exists. Return None if not.
        2. Read the file as UTF-8.
        3. Split on "---" to extract frontmatter YAML and body.
        4. yaml.safe_load the frontmatter into ManifestFrontmatter fields.
        5. Return Manifest(frontmatter, body).
    """
    raise NotImplementedError


def write_manifest(
    path: Path,
    *,
    model: str,
    content_hash: str,
    files: int,
    dirs: int,
    tokens_total: int,
    body: str,
) -> None:
    """Write a CONTEXT.md file to a directory.

    Args:
        path: Directory to write CONTEXT.md into.
        model: Model ID used for generation.
        content_hash: Current content hash of the directory.
        files: Number of files in this directory.
        dirs: Number of subdirectories.
        tokens_total: Estimated total tokens across all files.
        body: Markdown body (everything after frontmatter).

    Implementation:
        1. Build ManifestFrontmatter with current timestamp (UTC ISO), generator version, etc.
        2. Serialize frontmatter to YAML.
        3. Write: "---\\n" + yaml + "---\\n" + body to path / "CONTEXT.md".
        4. Use UTF-8 encoding.
    """
    raise NotImplementedError
