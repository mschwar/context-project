"""Tests for ctx.cli — Click command wiring and output."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from click.testing import CliRunner

import shutil

from ctx import __version__
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
    assert f"ctx, version {__version__}" in result.output


# --- dry-run ---


def _copy_sample_project(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "sample_project"
    destination = tmp_path / "sample_project"
    shutil.copytree(source, destination)
    return destination


def test_update_dry_run_lists_stale_dirs_without_llm(tmp_path) -> None:
    """--dry-run should list stale dirs and not invoke any LLM client."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    # Remove any pre-existing CONTEXT.md files so dirs are stale
    for ctx_file in root.rglob("CONTEXT.md"):
        ctx_file.unlink()

    result = runner.invoke(cli_module.cli, ["update", str(root), "--dry-run"])

    assert result.exit_code == 0
    assert "would be regenerated" in result.output
    # No CONTEXT.md files should have been written
    assert not any(root.rglob("CONTEXT.md"))


def test_update_dry_run_reports_nothing_when_fresh(tmp_path, monkeypatch) -> None:
    """--dry-run should say nothing to regenerate when all manifests are fresh."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    # Fake check_stale_dirs returning empty list
    monkeypatch.setattr(cli_module, "check_stale_dirs", lambda *a, **kw: [])
    # Fake load_config to avoid needing API key
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: Config(api_key="fake"))

    result = runner.invoke(cli_module.cli, ["update", str(root), "--dry-run"])

    assert result.exit_code == 0
    assert "fresh" in result.output.lower() or "nothing" in result.output.lower()


def test_update_surfaces_budget_warning_when_exhausted(tmp_path, monkeypatch) -> None:
    """CLI should print a warning when token budget is exhausted."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key", token_budget=1)
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "update_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=1, dirs_skipped=2, tokens_used=1, budget_exhausted=True),
    )

    result = runner.invoke(cli_module.cli, ["update", str(root)])

    assert "budget" in result.output.lower()


# --- init --overwrite ---


def test_init_no_overwrite_calls_update_tree(tmp_path, monkeypatch) -> None:
    """ctx init --no-overwrite should delegate to update_tree (skip fresh manifests)."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())

    calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: calls.append("generate") or GenerateStats(),
    )
    monkeypatch.setattr(
        cli_module,
        "update_tree",
        lambda *a, **kw: calls.append("update") or GenerateStats(),
    )

    result = runner.invoke(cli_module.cli, ["init", "--no-overwrite", str(root)])

    assert result.exit_code == 0
    assert calls == ["update"]
    assert "incremental" in result.output.lower()


def test_init_default_overwrite_calls_generate_tree(tmp_path, monkeypatch) -> None:
    """ctx init (default) should call generate_tree."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())

    calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: calls.append("generate") or GenerateStats(),
    )

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 0
    assert calls == ["generate"]


# --- ctx diff ---


def test_diff_no_changes(tmp_path, monkeypatch) -> None:
    """ctx diff should report nothing when no CONTEXT.md files are changed."""
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", str(root)])

    assert result.exit_code == 0
    assert "No CONTEXT.md files changed" in result.output


def test_diff_reports_modified_files(tmp_path, monkeypatch) -> None:
    """ctx diff should list modified and new CONTEXT.md files."""
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1

        class R:
            returncode = 0

        r = R()
        if call_count == 1:
            r.stdout = "src/CONTEXT.md\n"
        else:
            r.stdout = "new_dir/CONTEXT.md\n"
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", str(root)])

    assert result.exit_code == 0
    assert "2 CONTEXT.md files changed" in result.output
    assert "[mod]" in result.output
    assert "[new]" in result.output
