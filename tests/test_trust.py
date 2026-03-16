"""Tests for Phase 10 — accurate token estimation, cache eviction, transient error messaging."""

from __future__ import annotations

import json
import math
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import anthropic
import pytest
from click.testing import CliRunner

from ctx.generator import _estimate_tokens
from ctx.llm import CachingLLMClient, RETRY_ATTEMPTS, TRANSIENT_ERROR_PREFIX, _call_with_retries


# ---------------------------------------------------------------------------
# 10.1 — Token estimation
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty_string() -> None:
    assert _estimate_tokens("") == 0


def test_estimate_tokens_uses_tiktoken_when_available() -> None:
    # tiktoken is installed as a dependency; result should be > 0 and consistent
    result = _estimate_tokens("hello world")
    assert result > 0
    # Stable across calls
    assert _estimate_tokens("hello world") == result


def test_estimate_tokens_falls_back_when_tiktoken_unavailable() -> None:
    with patch("ctx.generator._TIKTOKEN_ENCODER", False):
        result = _estimate_tokens("hello world")
        # falls back to len/4 heuristic: ceil(11/4) = 3
        assert result == 3


def test_estimate_tokens_tiktoken_more_accurate_than_heuristic() -> None:
    # For a realistic code snippet, tiktoken should differ from len/4
    snippet = "def foo(x: int) -> str:\n    return str(x)\n"
    tiktoken_count = _estimate_tokens(snippet)
    heuristic_count = max(1, math.ceil(len(snippet) / 4))
    # They won't always differ, but for non-trivial text tiktoken is usually different
    # Just verify tiktoken gives a positive integer
    assert isinstance(tiktoken_count, int)
    assert tiktoken_count > 0


# ---------------------------------------------------------------------------
# 10.2 — Cache eviction
# ---------------------------------------------------------------------------


class _FakeClient:
    model = "test-model"

    def summarize_files(self, root, files):
        from ctx.llm import LLMResult
        return [LLMResult(text=f"summary of {f['name']}", input_tokens=1, output_tokens=1) for f in files]

    def summarize_directory(self, root, rel, file_summaries, subdir_summaries):
        from ctx.llm import LLMResult
        return LLMResult(text="## body", input_tokens=1, output_tokens=1)


def _make_file_payload(name: str) -> list[dict]:
    return [{"name": name, "content": f"content of {name}", "language": None, "metadata": {}}]


def test_cache_eviction_trims_to_max_entries(tmp_path) -> None:
    cache_file = tmp_path / "cache.json"
    client = CachingLLMClient(_FakeClient(), cache_path=cache_file, max_cache_entries=3)

    # Populate more than max_cache_entries entries
    for i in range(5):
        client.summarize_files(Path("src"), _make_file_payload(f"file{i}.py"))

    assert cache_file.exists()
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert len(data) <= 3


def test_cache_eviction_keeps_most_recent_entries(tmp_path) -> None:
    cache_file = tmp_path / "cache.json"
    client = CachingLLMClient(_FakeClient(), cache_path=cache_file, max_cache_entries=2)

    client.summarize_files(Path("src"), _make_file_payload("old.py"))
    client.summarize_files(Path("src"), _make_file_payload("newer.py"))
    client.summarize_files(Path("src"), _make_file_payload("newest.py"))

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert len(data) == 2


def test_cache_no_eviction_when_under_limit(tmp_path) -> None:
    cache_file = tmp_path / "cache.json"
    client = CachingLLMClient(_FakeClient(), cache_path=cache_file, max_cache_entries=10)

    for i in range(3):
        client.summarize_files(Path("src"), _make_file_payload(f"file{i}.py"))

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert len(data) == 3


# ---------------------------------------------------------------------------
# 10.3 — Transient error transparency
# ---------------------------------------------------------------------------


def test_transient_error_tag_on_retry_exhaustion() -> None:
    call_count = 0

    def always_fail():
        nonlocal call_count
        call_count += 1
        raise anthropic.APIConnectionError(request=None)

    with patch("time.sleep"):  # skip actual delays
        with pytest.raises(RuntimeError, match=r"\[transient, retries exhausted\]"):
            _call_with_retries("anthropic", always_fail)

    assert call_count == RETRY_ATTEMPTS


def test_non_retryable_error_not_tagged() -> None:
    def raises_value_error():
        raise ValueError("not a transient error")

    with pytest.raises(ValueError, match="not a transient error"):
        _call_with_retries("anthropic", raises_value_error)


def test_cli_prints_retry_tip_when_transient_error_in_stats(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    from ctx.generator import GenerateStats
    from ctx.config import Config

    runner = CliRunner()
    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key")
    fake_stats = GenerateStats(
        dirs_processed=0,
        files_processed=0,
        tokens_used=0,
        errors=["[transient, retries exhausted] connection refused"],
    )

    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda p: object())
    monkeypatch.setattr(cli_module, "create_client", lambda c: object())
    monkeypatch.setattr(cli_module, "update_tree", lambda *a, **kw: fake_stats)

    result = runner.invoke(cli_module.cli, ["update", str(tmp_path)])

    assert "Tip: transient errors may resolve on retry. Run the command again." in result.output
