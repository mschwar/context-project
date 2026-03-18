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

import os
import tempfile
from dataclasses import asdict, dataclass
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
    manifest_path = path / "CONTEXT.md"
    if not manifest_path.exists():
        return None

    text = manifest_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Invalid manifest frontmatter in {manifest_path}")

    closing_index = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if closing_index is None:
        raise ValueError(f"Invalid manifest frontmatter in {manifest_path}")

    frontmatter_data = yaml.safe_load("".join(lines[1:closing_index])) or {}
    if not isinstance(frontmatter_data, dict):
        raise ValueError(f"Invalid manifest frontmatter in {manifest_path}")

    generated = frontmatter_data.get("generated", "")
    if isinstance(generated, datetime):
        generated = generated.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    elif generated is None:
        generated = ""
    else:
        generated = str(generated)

    frontmatter = ManifestFrontmatter(
        generated=generated,
        generator=str(frontmatter_data.get("generator", f"ctx/{__version__}") or ""),
        model=str(frontmatter_data.get("model", "") or ""),
        content_hash=str(frontmatter_data.get("content_hash", "") or ""),
        files=int(frontmatter_data.get("files", 0) or 0),
        dirs=int(frontmatter_data.get("dirs", 0) or 0),
        tokens_total=int(frontmatter_data.get("tokens_total", 0) or 0),
    )
    body = "".join(lines[closing_index + 1 :])
    return Manifest(frontmatter=frontmatter, body=body)


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
    frontmatter = ManifestFrontmatter(
        generated=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        model=model,
        content_hash=content_hash,
        files=files,
        dirs=dirs,
        tokens_total=tokens_total,
    )
    yaml_body = yaml.safe_dump(asdict(frontmatter), sort_keys=False, default_flow_style=False)
    content = f"---\n{yaml_body}---\n{body}"
    target = path / "CONTEXT.md"
    fd, tmp_path = tempfile.mkstemp(
        prefix=".CONTEXT.md.",
        suffix=".tmp",
        dir=str(path),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, str(target))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
