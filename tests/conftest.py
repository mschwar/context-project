"""Shared pytest fixtures for filesystem-backed tests."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Provide a workspace-local temporary directory.

    The sandbox blocks pytest's default Windows temp root, so tests create
    per-test directories under the repository instead.
    """

    base_dir = Path(__file__).resolve().parents[1] / ".tmp" / "test-work"
    base_dir.mkdir(parents=True, exist_ok=True)

    path = base_dir / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
