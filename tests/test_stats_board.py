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


def test_run_record_fields(tmp_path) -> None:
    config = _make_config()
    result = _make_result(cache_hits=30, cache_misses=10, tokens_used=4000)

    record = _build_run_record(result, config)

    expected_keys = {
        "ts", "dirs_processed", "dirs_skipped", "files_processed",
        "tokens_used", "tokens_saved", "est_cost_usd", "cost_saved_usd",
        "cache_hits", "cache_misses", "strategy", "errors",
        "budget_exhausted", "provider", "model",
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
