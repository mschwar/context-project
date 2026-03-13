"""Tests for ctx.cli — Click command wiring and output."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from click.testing import CliRunner

from ctx.config import Config
from ctx.generator import GenerateStats


def test_init_command_wires_dependencies_and_prints_summary(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key", max_depth=3)
    fake_spec = object()
    fake_client = object()
    calls: dict[str, object] = {}

    def fake_load_config(target_path: Path, **kwargs) -> Config:
        calls["load_config"] = (target_path, kwargs)
        return fake_config

    def fake_load_ignore_patterns(target_path: Path):
        calls["load_ignore_patterns"] = target_path
        return fake_spec

    def fake_create_client(config: Config):
        calls["create_client"] = config
        return fake_client

    def fake_generate_tree(root: Path, config: Config, client: object, spec: object, *, progress):
        calls["generate_tree"] = (root, config, client, spec)
        progress(root / "docs", 1, 2)
        progress(root, 2, 2)
        return GenerateStats(
            dirs_processed=2,
            files_processed=4,
            tokens_used=99,
            errors=["docs: synthetic failure"],
        )

    monkeypatch.setattr(cli_module, "load_config", fake_load_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", fake_load_ignore_patterns)
    monkeypatch.setattr(cli_module, "create_client", fake_create_client)
    monkeypatch.setattr(cli_module, "generate_tree", fake_generate_tree)

    result = runner.invoke(
        cli_module.cli,
        ["init", str(tmp_path), "--provider", "openai", "--model", "gpt-test", "--max-depth", "3"],
    )

    assert result.exit_code == 0
    assert calls["load_config"] == (
        tmp_path,
        {"provider": "openai", "model": "gpt-test", "max_depth": 3},
    )
    assert calls["load_ignore_patterns"] == tmp_path
    assert calls["create_client"] == fake_config
    assert calls["generate_tree"] == (tmp_path, fake_config, fake_client, fake_spec)
    assert f"ctx init: generating manifests for {tmp_path}" in result.output
    assert "  [1/2] Processing docs" in result.output
    assert "  [2/2] Processing" in result.output
    assert "Directories processed: 2" in result.output
    assert "Files processed: 4" in result.output
    assert "Tokens used: 99" in result.output
    assert "Errors: 1" in result.output
    assert "docs: synthetic failure" in result.output


def test_update_command_wires_dependencies_and_prints_summary(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    fake_spec = object()
    fake_client = object()
    calls: dict[str, object] = {}

    def fake_load_config(target_path: Path, **kwargs) -> Config:
        calls["load_config"] = (target_path, kwargs)
        return fake_config

    def fake_load_ignore_patterns(target_path: Path):
        calls["load_ignore_patterns"] = target_path
        return fake_spec

    def fake_create_client(config: Config):
        calls["create_client"] = config
        return fake_client

    def fake_update_tree(root: Path, config: Config, client: object, spec: object, *, progress):
        calls["update_tree"] = (root, config, client, spec)
        progress(root, 1, 1)
        return GenerateStats(dirs_processed=1, dirs_skipped=2, tokens_used=42)

    monkeypatch.setattr(cli_module, "load_config", fake_load_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", fake_load_ignore_patterns)
    monkeypatch.setattr(cli_module, "create_client", fake_create_client)
    monkeypatch.setattr(cli_module, "update_tree", fake_update_tree)

    result = runner.invoke(
        cli_module.cli,
        ["update", str(tmp_path), "--provider", "anthropic", "--model", "claude-test"],
    )

    assert result.exit_code == 0
    assert calls["load_config"] == (
        tmp_path,
        {"provider": "anthropic", "model": "claude-test"},
    )
    assert calls["load_ignore_patterns"] == tmp_path
    assert calls["create_client"] == fake_config
    assert calls["update_tree"] == (tmp_path, fake_config, fake_client, fake_spec)
    assert f"ctx update: refreshing manifests for {tmp_path}" in result.output
    assert "  [1/1] Processing" in result.output
    assert "Directories refreshed: 1" in result.output
    assert "Directories skipped: 2" in result.output
    assert "Tokens used: 42" in result.output
    assert "Errors: 0" in result.output


def test_status_command_prints_table_and_summary(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    fake_spec = object()
    calls: dict[str, object] = {}

    def fake_load_ignore_patterns(target_path: Path):
        calls["load_ignore_patterns"] = target_path
        return fake_spec

    def fake_get_status(root: Path, spec: object, target_root: Path):
        calls["get_status"] = (root, spec, target_root)
        return [
            {"path": ".", "status": "fresh"},
            {"path": "src", "status": "stale"},
            {"path": "docs", "status": "missing"},
        ]

    monkeypatch.setattr(cli_module, "load_ignore_patterns", fake_load_ignore_patterns)
    monkeypatch.setattr(cli_module, "get_status", fake_get_status)

    result = runner.invoke(cli_module.cli, ["status", str(tmp_path)])

    assert result.exit_code == 0
    assert calls["load_ignore_patterns"] == tmp_path
    assert calls["get_status"] == (tmp_path, fake_spec, tmp_path)
    assert "STATUS   PATH" in result.output
    assert "fresh    ." in result.output
    assert "stale    ./src" in result.output
    assert "missing  ./docs" in result.output
    assert "1 fresh, 1 stale, 1 missing" in result.output


def test_version_command_outputs_version() -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    result = runner.invoke(cli_module.cli, ["--version"])

    assert result.exit_code == 0
    assert "ctx, version 0.1.0" in result.output
