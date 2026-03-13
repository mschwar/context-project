"""Tests for ctx.manifest — CONTEXT.md read/write/parse."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ctx import __version__
from ctx.manifest import read_manifest, write_manifest


BODY = """# /sample/project

One-line purpose summary.

## Files
- **main.py** — entrypoint

## Notes
- preserves markdown exactly
---
"""


def test_write_and_read_roundtrip(tmp_path) -> None:
    write_manifest(
        tmp_path,
        model="claude-haiku-4-5-20251001",
        content_hash="sha256:abc123",
        files=2,
        dirs=1,
        tokens_total=321,
        body=BODY,
    )

    manifest = read_manifest(tmp_path)

    assert manifest is not None
    assert manifest.frontmatter.model == "claude-haiku-4-5-20251001"
    assert manifest.frontmatter.content_hash == "sha256:abc123"
    assert manifest.frontmatter.files == 2
    assert manifest.frontmatter.dirs == 1
    assert manifest.frontmatter.tokens_total == 321
    assert manifest.body == BODY


def test_read_missing_manifest(tmp_path) -> None:
    assert read_manifest(tmp_path) is None


def test_frontmatter_fields(tmp_path) -> None:
    write_manifest(
        tmp_path,
        model="gpt-5-mini",
        content_hash="sha256:def456",
        files=12,
        dirs=3,
        tokens_total=48000,
        body="# /tmp\n",
    )

    manifest = read_manifest(tmp_path)
    raw_text = (tmp_path / "CONTEXT.md").read_text(encoding="utf-8")

    assert manifest is not None
    assert manifest.frontmatter.generator == f"ctx/{__version__}"
    assert manifest.frontmatter.model == "gpt-5-mini"
    assert manifest.frontmatter.content_hash == "sha256:def456"
    assert manifest.frontmatter.files == 12
    assert manifest.frontmatter.dirs == 3
    assert manifest.frontmatter.tokens_total == 48000
    assert f"generator: ctx/{__version__}" in raw_text


def test_body_preserved(tmp_path) -> None:
    body = "# /tmp\n\nParagraph one.\n\n---\n\nParagraph two.\n"

    write_manifest(
        tmp_path,
        model="claude-haiku-4-5-20251001",
        content_hash="sha256:body",
        files=1,
        dirs=0,
        tokens_total=5,
        body=body,
    )

    manifest = read_manifest(tmp_path)

    assert manifest is not None
    assert manifest.body == body


def test_timestamp_format(tmp_path) -> None:
    write_manifest(
        tmp_path,
        model="claude-haiku-4-5-20251001",
        content_hash="sha256:time",
        files=1,
        dirs=0,
        tokens_total=5,
        body="# /tmp\n",
    )

    manifest = read_manifest(tmp_path)

    assert manifest is not None
    assert manifest.frontmatter.generated.endswith("Z")
    parsed = datetime.fromisoformat(manifest.frontmatter.generated.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc


def test_read_manifest_rejects_missing_opening_delimiter(tmp_path) -> None:
    (tmp_path / "CONTEXT.md").write_text("generated: nope\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid manifest frontmatter"):
        read_manifest(tmp_path)


def test_read_manifest_rejects_missing_closing_delimiter(tmp_path) -> None:
    (tmp_path / "CONTEXT.md").write_text("---\ngenerated: nope\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid manifest frontmatter"):
        read_manifest(tmp_path)
