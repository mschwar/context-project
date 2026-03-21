"""Tests for ctx.stats_board — persistent run-stats ledger."""

from __future__ import annotations

import json
import stat
import platform
from pathlib import Path

import pytest

from ctx.api import RefreshResult
from ctx.config import Config
from ctx.stats_board import (
    _build_run_record,
    _global_stats_path,
    _load_json_safe,
    _run_stats_path,
    _save_json_atomic,
    _update_global,
    read_board,
    read_global_board,
    record_run,
)


def _make_result(**kwargs) -> RefreshResult:
    defaults = dict(
        dirs_processed=10,
        dirs_skipped=2,
        files_processed=50,
        tokens_used=10000,
        errors=[],
        budget_exhausted=False,
        strategy="incremental",
        est_cost_usd=0.008,
        stale_directories=[],
        cache_hits=20,
        cache_misses=10,
    )
    defaults.update(kwargs)
    return RefreshResult(**defaults)


def _make_config(**kwargs) -> Config:
    defaults = dict(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="test-key")
    defaults.update(kwargs)
    return Config(**defaults)


def test_record_run_creates_per_repo_file(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    cache_dir = root / ".ctx-cache"
    cache_dir.mkdir()
    config = _make_config(cache_path=str(cache_dir / "llm_cache.json"))
    result = _make_result()

    record_run(root, result, config)

    stats_file = cache_dir / "run_stats.json"
    assert stats_file.exists()
    data = json.loads(stats_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["runs"]) == 1
    assert data["runs"][0]["dirs_processed"] == 10


def test_record_run_appends_on_second_call(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()
    result = _make_result()

    record_run(root, result, config)
    record_run(root, result, config)

    stats_file = root / ".ctx-cache" / "run_stats.json"
    data = json.loads(stats_file.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2


def test_record_run_updates_global_file(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    global_path = tmp_path / "global_stats.json"
    config = _make_config()
    result = _make_result()

    # Patch _global_stats_path via monkeypatching at module level is complex;
    # instead call _update_global directly with a tmp path.
    record = _build_run_record(result, config)
    _update_global(global_path, str(root.resolve()), record)

    data = json.loads(global_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert str(root.resolve()) in data["repos"]
    assert data["totals"]["total_runs"] == 1
    assert data["totals"]["repos_touched"] == 1


def test_record_run_never_raises_on_corrupt_file(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    cache_dir = root / ".ctx-cache"
    cache_dir.mkdir()
    stats_file = cache_dir / "run_stats.json"
    stats_file.write_text("not valid json {{{{", encoding="utf-8")

    config = _make_config()
    result = _make_result()

    # Should not raise
    record_run(root, result, config)

    # File should be overwritten with fresh data
    data = json.loads(stats_file.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 1


@pytest.mark.skipif(platform.system() == "Windows", reason="chmod not reliable on Windows")
def test_record_run_never_raises_on_unwritable_dir(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    cache_dir = root / ".ctx-cache"
    cache_dir.mkdir()
    cache_dir.chmod(stat.S_IREAD | stat.S_IEXEC)

    config = _make_config()
    result = _make_result()

    try:
        # Should not raise
        record_run(root, result, config)
    finally:
        cache_dir.chmod(stat.S_IRWXU)


def test_record_run_skips_on_dry_run(tmp_path, monkeypatch) -> None:
    import ctx.api as api_module
    import ctx.git as git_module
    from ctx.generator import GenerateStats

    calls = []

    def fake_record(root, result, config):
        calls.append((root, result, config))

    monkeypatch.setattr("ctx.stats_board.record_run", fake_record, raising=False)

    config = Config(provider="openai", model="test-model", api_key="test-key")

    class _NoopLock:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *e): pass

    monkeypatch.setattr(api_module, "_build_generation_runtime", lambda *a, **kw: (config, object(), object()))
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "update_tree", lambda *a, **kw: GenerateStats(dirs_processed=0, tokens_used=0))

    api_module.refresh(tmp_path, dry_run=True)

    assert calls == []


def test_read_board_empty(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()

    board = read_board(root, config)

    assert board["aggregate"]["run_count"] == 0
    assert board["aggregate"]["total_tokens_used"] == 0
    assert board["recent_runs"] == []


def test_read_board_aggregate(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()

    for i in range(3):
        record_run(root, _make_result(tokens_used=1000 * (i + 1), cache_hits=5, cache_misses=5), config)

    board = read_board(root, config)

    assert board["aggregate"]["run_count"] == 3
    assert board["aggregate"]["total_tokens_used"] == 1000 + 2000 + 3000
    hr = board["aggregate"]["cache_hit_rate"]
    assert 0.0 < hr <= 1.0


def test_read_global_board_multi_repo(tmp_path) -> None:
    global_path = tmp_path / "global_stats.json"
    config = _make_config()

    result = _make_result(tokens_used=5000)
    record_a = _build_run_record(result, config)
    record_b = _build_run_record(_make_result(tokens_used=8000), config)

    _update_global(global_path, "/repo/a", record_a)
    _update_global(global_path, "/repo/b", record_b)

    board = read_global_board(global_path=global_path)

    assert board["totals"]["repos_touched"] == 2
    assert board["totals"]["total_runs"] == 2
    assert "/repo/a" in board["repos"]
    assert "/repo/b" in board["repos"]


def test_run_record_fields_old(tmp_path) -> None:
    config = _make_config()
    result = _make_result(cache_hits=30, cache_misses=10, tokens_used=4000)

    record = _build_run_record(result, config)

    expected_keys = {
        "ts", "dirs_processed", "dirs_skipped", "files_processed",
        "tokens_used", "tokens_saved", "est_cost_usd", "cost_saved_usd",
        "cache_hits", "cache_misses", "strategy", "errors",
        "error_types", "budget_exhausted", "provider", "model",
    }
    assert expected_keys.issubset(set(record.keys()))
    assert record["cache_hits"] == 30
    assert record["cache_misses"] == 10
    assert record["provider"] == "anthropic"


def test_tokens_saved_estimation() -> None:
    config = _make_config()
    # 20 hits, 10 misses, 3000 tokens_used
    # avg_per_miss = 3000 / 10 = 300
    # tokens_saved = round(300 * 20) = 6000
    result = _make_result(cache_hits=20, cache_misses=10, tokens_used=3000)

    record = _build_run_record(result, config)

    # hits / (hits + misses) * tokens_used = 20/30 * 3000 = 2000
    assert record["tokens_saved"] == round((20 / 30) * 3000)


def test_run_record_fields(tmp_path) -> None:
    config = _make_config()
    result = _make_result(cache_hits=30, cache_misses=10, tokens_used=4000)

    record = _build_run_record(result, config)

    expected_keys = {
        "ts", "dirs_processed", "dirs_skipped", "files_processed",
        "tokens_used", "tokens_saved", "est_cost_usd", "cost_saved_usd",
        "cache_hits", "cache_misses", "strategy", "errors",
        "error_types", "budget_exhausted", "provider", "model",
    }
    assert expected_keys.issubset(set(record.keys()))
    assert record["cache_hits"] == 30
    assert record["cache_misses"] == 10
    assert record["provider"] == "anthropic"


def test_atomic_write_is_safe(tmp_path) -> None:
    target = tmp_path / "out.json"
    data = {"schema_version": 1, "runs": [{"ts": "2026-01-01T00:00:00.000Z"}]}

    _save_json_atomic(target, data)

    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == data
    # No temp files left
    leftover = [f for f in tmp_path.iterdir() if f != target]
    assert leftover == []


def test_classify_errors_transient() -> None:
    from ctx.stats_board import _classify_errors
    errors = [
        "[transient, retries exhausted] Connection reset",
        "[transient, retries exhausted] Timeout",
        "Some other error",
    ]
    result = _classify_errors(errors)
    assert result["transient"] == 2
    assert result["other"] == 1
    assert result["timeout"] == 0


def test_classify_errors_all_types() -> None:
    from ctx.stats_board import _classify_errors
    errors = [
        "[transient, retries exhausted] blah",
        "Connection timeout after 60s",
        "Rate limit exceeded",
        "Budget exhausted",
        "Unknown failure",
    ]
    result = _classify_errors(errors)
    assert result["transient"] == 1
    assert result["timeout"] == 1
    assert result["rate_limit"] == 1
    assert result["budget"] == 1
    assert result["other"] == 1


def test_classify_errors_empty() -> None:
    from ctx.stats_board import _classify_errors
    assert _classify_errors([]) == {"transient": 0, "timeout": 0, "rate_limit": 0, "budget": 0, "other": 0}


def test_build_run_record_includes_error_types() -> None:
    config = _make_config()
    result = _make_result(errors=["[transient, retries exhausted] blah", "Unknown"])
    record = _build_run_record(result, config)
    assert "error_types" in record
    assert record["error_types"]["transient"] == 1
    assert record["error_types"]["other"] == 1


def test_read_board_per_model(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()
    record_run(root, _make_result(tokens_used=1000), config)
    config2 = _make_config(provider="openai", model="gpt-4o")
    record_run(root, _make_result(tokens_used=2000), config2)

    board = read_board(root, config)
    assert "per_model" in board
    assert "anthropic/claude-haiku-4-5-20251001" in board["per_model"]
    assert "openai/gpt-4o" in board["per_model"]
    assert board["per_model"]["anthropic/claude-haiku-4-5-20251001"]["run_count"] == 1
    assert board["per_model"]["openai/gpt-4o"]["run_count"] == 1


def test_read_board_since_filter(tmp_path) -> None:
    from ctx.stats_board import _save_json_atomic, _run_stats_path
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()

    # Manually write runs with specific timestamps
    old_run = {
        "ts": "2020-01-01T00:00:00.000Z",
        "dirs_processed": 5, "dirs_skipped": 0, "files_processed": 10,
        "tokens_used": 1000, "tokens_saved": 0, "est_cost_usd": 0.001,
        "cost_saved_usd": 0.0, "cache_hits": 0, "cache_misses": 10,
        "strategy": "full", "errors": 0, "budget_exhausted": False,
        "provider": "anthropic", "model": "test",
    }
    new_run = dict(old_run)
    new_run["ts"] = "2099-01-01T00:00:00.000Z"
    new_run["tokens_used"] = 2000

    stats_path = _run_stats_path(root, config)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json_atomic(stats_path, {"schema_version": 1, "runs": [old_run, new_run]})

    # Without filter: both runs
    board = read_board(root, config)
    assert board["aggregate"]["run_count"] == 2

    # With filter: only the future run
    board = read_board(root, config, since="2098-01-01")
    assert board["aggregate"]["run_count"] == 1
    assert board["aggregate"]["total_tokens_used"] == 2000


def test_read_board_since_relative(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()

    # Write a run with current timestamp (should be included with "7d" filter)
    record_run(root, _make_result(), config)

    board = read_board(root, config, since="7d")
    assert board["aggregate"]["run_count"] == 1


def test_read_trend(tmp_path) -> None:
    from ctx.stats_board import read_trend
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()
    record_run(root, _make_result(cache_hits=8, cache_misses=2), config)
    record_run(root, _make_result(cache_hits=5, cache_misses=5), config)

    trend = read_trend(root, config, count=10)
    assert len(trend) == 2
    assert "est_cost_usd" in trend[0]
    assert "cache_hit_rate" in trend[0]
    assert trend[0]["cache_hit_rate"] == 0.8


def test_read_trend_empty(tmp_path) -> None:
    from ctx.stats_board import read_trend
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()
    assert read_trend(root, config) == []


def test_record_run_logs_on_failure(tmp_path, monkeypatch, caplog) -> None:
    """record_run should log a warning when it fails, not silently swallow."""
    import ctx.stats_board as sb
    root = tmp_path / "repo"
    root.mkdir()
    config = _make_config()

    def boom(*a, **kw):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(sb, "_build_run_record", boom)

    import logging
    with caplog.at_level(logging.WARNING, logger="ctx.stats_board"):
        record_run(root, _make_result(), config)
    assert "disk exploded" in caplog.text


def test_global_retry_on_failure(tmp_path, monkeypatch) -> None:
    """_update_global should retry on OSError."""
    import ctx.stats_board as sb
    attempts = []
    original_save = sb._save_json_atomic

    def flaky_save(path, data):
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("busy")
        return original_save(path, data)

    monkeypatch.setattr(sb, "_save_json_atomic", flaky_save)
    monkeypatch.setattr(sb, "_GLOBAL_WRITE_BACKOFF_SECONDS", 0.001)  # fast for tests

    from ctx.stats_board import _update_global, _build_run_record
    config = _make_config()
    record = _build_run_record(_make_result(), config)
    global_path = tmp_path / "global.json"

    _update_global(global_path, "/test", record)
    assert len(attempts) == 3  # failed twice, succeeded on third
    assert global_path.exists()
