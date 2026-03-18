"""Tests for unified API module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

import ctx.api as api_module
import ctx.git as git_module
from ctx.api import ConfirmationRequiredError
from ctx.config import Config, MissingApiKeyError
from ctx.generator import GenerateStats
from ctx.manifest import Manifest, ManifestFrontmatter


@dataclass
class _Entry:
    path: Path
    relative_path: str
    status: str
    tokens_total: int | None = None
    error: str | None = None
    frontmatter: object | None = object()


class _NoopLock:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> "_NoopLock":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _patch_runtime(monkeypatch, *, provider: str = "openai") -> None:
    config = Config(provider=provider, model="test-model", api_key="test-key")
    monkeypatch.setattr(api_module, "_build_generation_runtime", lambda *a, **kw: (config, object(), object()))
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)


def test_refresh_full_strategy_when_no_manifests(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: False)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "generate_tree", lambda *a, **kw: GenerateStats(dirs_processed=2, files_processed=5, tokens_used=10))

    result = api_module.refresh(tmp_path)

    assert result.strategy == "full"
    assert result.dirs_processed == 2


def test_refresh_incremental_strategy_when_manifests_exist(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "update_tree", lambda *a, **kw: GenerateStats(dirs_processed=1, dirs_skipped=2, tokens_used=4))

    result = api_module.refresh(tmp_path)

    assert result.strategy == "incremental"
    assert result.dirs_processed == 1


def test_refresh_smart_strategy_when_git_changed_files_exist(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [tmp_path / "src" / "x.py"])
    monkeypatch.setattr(api_module, "update_tree", lambda *a, **kw: GenerateStats(dirs_processed=3, tokens_used=7))

    result = api_module.refresh(tmp_path)

    assert result.strategy == "smart"
    assert result.dirs_processed == 3


def test_refresh_falls_back_to_incremental_when_git_is_unavailable(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(
        git_module,
        "get_changed_files",
        lambda _root: (_ for _ in ()).throw(RuntimeError("not a git repository")),
    )
    monkeypatch.setattr(api_module, "update_tree", lambda *a, **kw: GenerateStats(dirs_processed=1, dirs_skipped=2))

    result = api_module.refresh(tmp_path)

    assert result.strategy == "incremental"
    assert result.dirs_processed == 1


def test_refresh_force_uses_full_strategy(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [tmp_path / "src" / "x.py"])
    monkeypatch.setattr(api_module, "generate_tree", lambda *a, **kw: GenerateStats(dirs_processed=9))

    result = api_module.refresh(tmp_path, force=True)

    assert result.strategy == "full"
    assert result.dirs_processed == 9


def test_refresh_setup_detects_and_writes_config(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: False)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "detect_provider", lambda: ("openai", "gpt-test"))
    writes: list[tuple[Path, str, str | None, str | None]] = []
    monkeypatch.setattr(api_module, "write_default_config", lambda path, provider, model, base_url: writes.append((path, provider, model, base_url)))
    monkeypatch.setattr(api_module, "generate_tree", lambda *a, **kw: GenerateStats(dirs_processed=1))

    result = api_module.refresh(tmp_path, setup=True)

    assert writes
    assert result.setup_provider == "openai"
    assert result.config_written is True


def test_refresh_dry_run_uses_stale_check_without_llm(tmp_path, monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    stale_dirs = [tmp_path / "src", tmp_path / "tests"]
    monkeypatch.setattr(api_module, "check_stale_dirs", lambda *a, **kw: stale_dirs)

    result = api_module.refresh(tmp_path, dry_run=True)

    assert result.dirs_processed == 0
    assert result.dirs_skipped == 2
    assert result.stale_directories == ["src", "tests"]


def test_refresh_setup_and_watch_are_mutually_exclusive(tmp_path) -> None:
    with pytest.raises(ValueError):
        api_module.refresh(tmp_path, setup=True, watch=True)


def test_refresh_applies_max_tokens_per_run_guardrail(tmp_path, monkeypatch) -> None:
    captured_config: Config | None = None
    config = Config(provider="openai", model="test-model", api_key="test-key", max_tokens_per_run=5)

    def fake_runtime(*_args, **_kwargs):
        return config, object(), object()

    def fake_update_tree(_root, runtime_config, *_args, **_kwargs):
        nonlocal captured_config
        captured_config = runtime_config
        return GenerateStats(dirs_processed=1, tokens_used=5, budget_exhausted=True)

    monkeypatch.setattr(api_module, "_build_generation_runtime", fake_runtime)
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "update_tree", fake_update_tree)

    result = api_module.refresh(tmp_path)

    assert isinstance(captured_config, Config)
    assert captured_config.token_budget == 5
    assert result.budget_exhausted is True
    assert result.budget_guardrail is not None
    assert "Token budget guardrail reached" in result.budget_guardrail


def test_refresh_reraises_missing_api_key_with_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "_build_generation_runtime",
        lambda *_a, **_kw: (_ for _ in ()).throw(MissingApiKeyError("Missing required environment variable: OPENAI_API_KEY")),
    )
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: False)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])

    with pytest.raises(MissingApiKeyError, match="while loading provider 'openai'"):
        api_module.refresh(tmp_path, provider="openai")

    config_path = tmp_path / ".ctxconfig"
    monkeypatch.setattr(api_module, "_find_config_path", lambda _root: config_path)
    with pytest.raises(MissingApiKeyError, match=re.escape(f"while loading configuration from {config_path}")):
        api_module.refresh(tmp_path)


def test_refresh_applies_max_usd_per_run_guardrail(tmp_path, monkeypatch) -> None:
    config = Config(provider="anthropic", model="claude-3-sonnet", api_key="test-key", max_usd_per_run=0.001)
    monkeypatch.setattr(api_module, "_build_generation_runtime", lambda *_a, **_kw: (config, object(), object()))
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "update_tree", lambda *_a, **_kw: GenerateStats(dirs_processed=1, tokens_used=1000))

    result = api_module.refresh(tmp_path)

    assert result.budget_exhausted is True
    assert result.budget_guardrail is not None
    assert "USD budget guardrail reached" in result.budget_guardrail


def test_refresh_surfaces_local_batch_fallback_count(tmp_path, monkeypatch) -> None:
    config = Config(provider="ollama", model="llama3.2", api_key="not-needed", base_url="http://localhost:11434/v1")
    client = SimpleNamespace(local_batch_fallbacks=3)
    monkeypatch.setattr(api_module, "_build_generation_runtime", lambda *_a, **_kw: (config, object(), client))
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: True)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "update_tree", lambda *_a, **_kw: GenerateStats(dirs_processed=1))

    result = api_module.refresh(tmp_path)

    assert result.local_batch_fallbacks == 3


def test_refresh_auto_detects_local_provider_when_unconfigured(tmp_path, monkeypatch) -> None:
    runtime_calls: list[tuple] = []
    writes: list[tuple[Path, str, str | None, str | None]] = []

    def fake_runtime(root, **kwargs):
        runtime_calls.append((root, kwargs))
        if len(runtime_calls) == 1:
            raise MissingApiKeyError("Missing required environment variable: ANTHROPIC_API_KEY")
        config = Config(provider="ollama", model="llama3.2", api_key="not-needed", base_url="http://localhost:11434/v1")
        return config, object(), object()

    monkeypatch.setattr(api_module, "_build_generation_runtime", fake_runtime)
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)
    monkeypatch.setattr(api_module, "_find_config_path", lambda _root: None)
    monkeypatch.setattr(api_module, "_has_manifests", lambda _root: False)
    monkeypatch.setattr(git_module, "get_changed_files", lambda _root: [])
    monkeypatch.setattr(api_module, "detect_provider", lambda: ("ollama", "llama3.2"))
    monkeypatch.setattr(
        api_module,
        "write_default_config",
        lambda path, provider, model, base_url: writes.append((path, provider, model, base_url)),
    )
    monkeypatch.setattr(api_module, "generate_tree", lambda *_a, **_kw: GenerateStats(dirs_processed=1))

    result = api_module.refresh(tmp_path)

    assert len(runtime_calls) == 2
    assert writes == [(tmp_path, "ollama", "llama3.2", "http://localhost:11434/v1")]
    assert result.setup_provider == "ollama"
    assert result.config_written is True


def test_check_health_mode(tmp_path, monkeypatch) -> None:
    entries = [
        _Entry(path=tmp_path, relative_path=".", status="fresh"),
        _Entry(path=tmp_path / "src", relative_path="src", status="stale"),
        _Entry(path=tmp_path / "docs", relative_path="docs", status="missing"),
    ]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)

    result = api_module.check(tmp_path)

    assert result.mode == "health"
    assert result.summary["stale"] == 1
    assert result.summary["missing"] == 1


def test_check_verify_mode(tmp_path, monkeypatch) -> None:
    entries = [
        _Entry(path=tmp_path, relative_path=".", status="fresh"),
        _Entry(path=tmp_path / "bad", relative_path="bad", status="stale"),
    ]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)

    result = api_module.check(tmp_path, verify=True)

    assert result.mode == "verify"
    assert "invalid" in result.summary


def test_check_verify_mode_reports_invalid_manifest_bodies(tmp_path, monkeypatch) -> None:
    frontmatter = ManifestFrontmatter(
        generated="2026-03-18T00:00:00Z",
        generator="ctx/0.8.0",
        model="test-model",
        content_hash="sha256:test",
        files=0,
        dirs=0,
        tokens_total=10,
    )
    entries = [
        _Entry(path=tmp_path, relative_path=".", status="fresh", frontmatter=frontmatter),
    ]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)
    monkeypatch.setattr(api_module, "read_manifest", lambda _path: Manifest(frontmatter=frontmatter, body="# bad\n"))
    monkeypatch.setattr(api_module, "validate_manifest_body", lambda *_a, **_kw: ["Files section lists nonexistent entries: fake.py"])

    result = api_module.check(tmp_path, verify=True)

    assert result.summary["invalid_body"] == 1
    assert result.summary["invalid"] == 1
    assert result.directories == [
        {
            "path": ".",
            "status": "invalid_body",
            "issues": ["Files section lists nonexistent entries: fake.py"],
        }
    ]


def test_check_stats_mode(tmp_path, monkeypatch) -> None:
    entries = [
        _Entry(path=tmp_path, relative_path=".", status="fresh", tokens_total=10),
        _Entry(path=tmp_path / "src", relative_path="src", status="missing", tokens_total=None),
    ]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)

    result = api_module.check(tmp_path, stats=True, verbose=True)

    assert result.mode == "stats"
    assert result.summary["dirs"] == 2
    assert result.summary["tokens"] == 10


def test_check_diff_mode(tmp_path, monkeypatch) -> None:
    def fake_run(cmd, **_kwargs):
        class _R:
            def __init__(self, stdout: str) -> None:
                self.stdout = stdout
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return _R("src/CONTEXT.md\n")
        return _R("new/CONTEXT.md\n")

    monkeypatch.setattr(api_module.subprocess, "run", fake_run)

    result = api_module.check(tmp_path, diff=True)

    assert result.mode == "diff"
    assert result.summary["modified"] == 1
    assert result.summary["new"] == 1


def test_check_mode_mutual_exclusivity(tmp_path) -> None:
    with pytest.raises(ValueError):
        api_module.check(tmp_path, verify=True, stats=True)


def test_export_all(tmp_path, monkeypatch) -> None:
    manifest_dir = tmp_path / "src"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "CONTEXT.md").write_text("# src\n", encoding="utf-8")
    entries = [_Entry(path=manifest_dir, relative_path="src", status="fresh")]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)

    result = api_module.export_context(tmp_path, filter_mode="all")

    assert result.manifests_exported == 1
    assert "# src/CONTEXT.md" in result.content


def test_export_filter_stale(tmp_path, monkeypatch) -> None:
    stale_dir = tmp_path / "stale"
    fresh_dir = tmp_path / "fresh"
    stale_dir.mkdir()
    fresh_dir.mkdir()
    (stale_dir / "CONTEXT.md").write_text("# stale\n", encoding="utf-8")
    (fresh_dir / "CONTEXT.md").write_text("# fresh\n", encoding="utf-8")
    entries = [
        _Entry(path=stale_dir, relative_path="stale", status="stale"),
        _Entry(path=fresh_dir, relative_path="fresh", status="fresh"),
    ]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)

    result = api_module.export_context(tmp_path, filter_mode="stale")

    assert result.manifests_exported == 1
    assert "# stale/CONTEXT.md" in result.content
    assert "# fresh/CONTEXT.md" not in result.content


def test_export_respects_depth(tmp_path, monkeypatch) -> None:
    shallow = tmp_path / "a"
    deep = tmp_path / "a" / "b"
    shallow.mkdir(parents=True)
    deep.mkdir(parents=True)
    (shallow / "CONTEXT.md").write_text("# a\n", encoding="utf-8")
    (deep / "CONTEXT.md").write_text("# a/b\n", encoding="utf-8")
    entries = [
        _Entry(path=shallow, relative_path="a", status="fresh"),
        _Entry(path=deep, relative_path="a/b", status="fresh"),
    ]
    monkeypatch.setattr(api_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(api_module, "inspect_directory_health", lambda *_a, **_kw: entries)

    result = api_module.export_context(tmp_path, depth=1)

    assert "# a/CONTEXT.md" in result.content
    assert "# a/b/CONTEXT.md" not in result.content


def test_reset_basic(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "CtxLock", _NoopLock)
    ctx_file = tmp_path / "CONTEXT.md"
    ctx_file.write_text("# root\n", encoding="utf-8")

    result = api_module.reset(tmp_path, yes=True)

    assert result.manifests_removed == 1
    assert not ctx_file.exists()


def test_reset_dry_run(tmp_path) -> None:
    ctx_file = tmp_path / "CONTEXT.md"
    ctx_file.write_text("# root\n", encoding="utf-8")

    result = api_module.reset(tmp_path, dry_run=True, yes=False)

    assert result.manifests_removed == 0
    assert result.paths == ["CONTEXT.md"]
    assert ctx_file.exists()


def test_reset_requires_confirmation(tmp_path) -> None:
    with pytest.raises(ConfirmationRequiredError):
        api_module.reset(tmp_path, yes=False)
