"""Tests for ctx.config — config file, env var, and CLI resolution."""

from __future__ import annotations

import click
import pytest
import yaml

from ctx.config import load_config


def _clear_ctx_env(monkeypatch) -> None:
    for name in ("CTX_PROVIDER", "CTX_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _write_ctxconfig(path, data: dict) -> None:
    (path / ".ctxconfig").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_load_config_defaults(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")

    config = load_config(tmp_path)

    assert config.provider == "anthropic"
    assert config.model == "claude-haiku-4-5-20251001"
    assert config.api_key == "anthropic-test-key"
    assert config.max_file_tokens == 8000
    assert config.max_depth is None
    assert config.extensions is None


def test_load_config_reads_nearest_parent_ctxconfig(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    root_dir = tmp_path / "root"
    nested_dir = root_dir / "project" / "src"
    nested_dir.mkdir(parents=True)

    _write_ctxconfig(root_dir, {"provider": "anthropic", "model": "root-model"})
    _write_ctxconfig(
        root_dir / "project",
        {
            "provider": "openai",
            "model": "gpt-5-mini",
            "max_file_tokens": 1234,
            "max_depth": 2,
            "extensions": [".py", ".md"],
        },
    )
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    config = load_config(nested_dir)

    assert config.provider == "openai"
    assert config.model == "gpt-5-mini"
    assert config.api_key == "openai-test-key"
    assert config.max_file_tokens == 1234
    assert config.max_depth == 2
    assert config.extensions == [".py", ".md"]


def test_load_config_env_overrides_file(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    _write_ctxconfig(tmp_path, {"provider": "anthropic", "model": "file-model", "max_depth": 1})
    monkeypatch.setenv("CTX_PROVIDER", "openai")
    monkeypatch.setenv("CTX_MODEL", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    config = load_config(tmp_path)

    assert config.provider == "openai"
    assert config.model == "env-model"
    assert config.max_depth == 1
    assert config.api_key == "openai-test-key"


def test_load_config_cli_overrides_env(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    _write_ctxconfig(tmp_path, {"provider": "anthropic", "model": "file-model"})
    monkeypatch.setenv("CTX_PROVIDER", "anthropic")
    monkeypatch.setenv("CTX_MODEL", "env-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    config = load_config(tmp_path, provider="openai", model="cli-model", max_depth=5)

    assert config.provider == "openai"
    assert config.model == "cli-model"
    assert config.max_depth == 5
    assert config.api_key == "openai-test-key"


def test_load_config_missing_api_key(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)

    with pytest.raises(click.UsageError, match="ANTHROPIC_API_KEY"):
        load_config(tmp_path)
