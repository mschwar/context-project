"""Shared pytest fixtures for filesystem-backed tests."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_process_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear ambient env that makes local test runs machine-dependent."""

    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "CTX_PROVIDER",
        "CTX_MODEL",
        "CTX_BASE_URL",
        "CTX_MAX_FILE_TOKENS",
        "CTX_MAX_DEPTH",
        "CTX_TOKEN_BUDGET",
        "CTX_MAX_TOKENS_PER_RUN",
        "CTX_MAX_USD_PER_RUN",
        "CTX_BATCH_SIZE",
        "CTX_CACHE_PATH",
        "CTX_MAX_CACHE_ENTRIES",
        "CTX_WATCH_DEBOUNCE",
        "CTX_EXTENSIONS",
        "CTX_OUTPUT",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    temp_root = Path(__file__).resolve().parents[1] / ".tmp" / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TEMP", os.fspath(temp_root))
    monkeypatch.setenv("TMP", os.fspath(temp_root))

    yield


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
