"""Tests for deterministic zero-LLM ctx.config."""

from __future__ import annotations

from pathlib import Path

import click
import pytest

from ctx.config import (
    Config,
    load_config,
    resolve_configured_extensions,
    resolve_project_anchor,
)
from ctx.hasher import normalize_extensions


def test_default_config_and_normalized_extensions() -> None:
    cfg = Config()
    assert cfg.max_depth is None
    assert cfg.extensions is None

    cfg2 = Config(max_depth=4, extensions=["py", " .TS ", ".py", ""])
    assert cfg2.max_depth == 4
    assert normalize_extensions(cfg2.extensions) == {".py", ".ts"}


def test_load_config_precedence_file_env_and_cli_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ctxconfig").write_text(
        "max_depth: 5\nextensions:\n  - .py\n  - .go\n",
        encoding="utf-8",
    )
    cfg_file = load_config(tmp_path)
    assert cfg_file.max_depth == 5
    assert cfg_file.extensions == [".py", ".go"]

    monkeypatch.setenv("CTX_MAX_DEPTH", "3")
    monkeypatch.setenv("CTX_EXTENSIONS", ".rs, ts")
    cfg_env = load_config(tmp_path)
    assert cfg_env.max_depth == 3
    assert normalize_extensions(cfg_env.extensions) == {".rs", ".ts"}

    cfg_cli = load_config(tmp_path, max_depth=1, extensions=[".py"])
    assert cfg_cli.max_depth == 1
    assert cfg_cli.extensions == [".py"]


def test_load_config_invalid_yaml_and_invalid_max_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ctxconfig").write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(click.UsageError, match="mapping"):
        load_config(tmp_path)

    (tmp_path / ".ctxconfig").write_text("max_depth: -1\n", encoding="utf-8")
    with pytest.raises(click.UsageError, match="non-negative"):
        load_config(tmp_path)

    (tmp_path / ".ctxconfig").write_text("max_depth: 2\n", encoding="utf-8")
    monkeypatch.setenv("CTX_MAX_DEPTH", "not-an-int")
    with pytest.raises(ValueError):
        load_config(tmp_path)


def test_resolve_project_anchor_and_configured_extensions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".ctxconfig").write_text("extensions: ['.py', '.md']\n", encoding="utf-8")
    nested = repo / "src" / "sub"
    nested.mkdir(parents=True)

    assert resolve_project_anchor(nested) == repo.resolve()
    assert resolve_configured_extensions(nested) == [".py", ".md"]
