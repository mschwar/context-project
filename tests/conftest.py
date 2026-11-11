"""Shared pytest fixtures for filesystem-backed tests."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import shutil
import uuid

import pytest


@pytest.fixture(autouse=True)
def _isolate_process_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear ambient env that makes local test runs machine-dependent."""
    for name in (
        "CTX_MAX_DEPTH",
        "CTX_EXTENSIONS",
        "CTX_OUTPUT",
    ):
        monkeypatch.delenv(name, raising=False)

    temp_root = Path(__file__).resolve().parents[1] / ".tmp" / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TEMP", os.fspath(temp_root))
    monkeypatch.setenv("TMP", os.fspath(temp_root))

    repo_root = Path(__file__).resolve().parents[1].resolve()
    test_work_root = (repo_root / ".tmp" / "test-work").resolve()

    def _isolated_config_dirs(start_dir: Path) -> list[Path]:
        resolved = start_dir.resolve()
        dirs: list[Path] = []
        for directory in (resolved, *resolved.parents):
            if directory == test_work_root:
                break
            if resolved.is_relative_to(repo_root) and not directory.is_relative_to(repo_root):
                break
            dirs.append(directory)
        return dirs or [start_dir]

    monkeypatch.setattr("ctx.config._iter_config_dirs", _isolated_config_dirs)

    yield


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Provide a workspace-local temporary directory."""
    base_dir = Path(__file__).resolve().parents[1] / ".tmp" / "test-work"
    base_dir.mkdir(parents=True, exist_ok=True)

    path = base_dir / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
