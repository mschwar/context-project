"""Compatibility tests for legacy command surfaces."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from click.testing import CliRunner


def test_help_shows_canonical_commands_only() -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    result = runner.invoke(cli_module.cli, ["--help"])

    assert result.exit_code == 0
    assert "refresh" in result.output
    assert "check" in result.output
    assert "export" in result.output
    assert "reset" in result.output
    assert "\n  init" in result.output  # init is now a visible command
    assert "\n  uninit" in result.output  # uninit is a new visible command
    assert "\n  update" not in result.output
    assert "\n  status" not in result.output
    assert "\n  clean" not in result.output


def test_init_is_no_longer_deprecated(tmp_path, monkeypatch) -> None:
    """ctx init is now a first-class command, not a deprecated alias."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    fake_result = {
        "root": str(tmp_path), "ctx_dir": str(tmp_path / ".ctx"),
        "hooks_installed": ["post-commit"], "manifests_refreshed": 1,
        "exports": ["CONTEXT.md"], "metadata": {}, "force": False,
    }
    monkeypatch.setattr("ctx.init.init_project", lambda *a, **kw: fake_result)

    result = runner.invoke(cli_module.cli, ["init", str(tmp_path)])

    assert result.exit_code == 0
    assert "deprecated" not in result.output
    assert "Initialized ctx" in result.output


def test_status_and_check_health_match(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    class _Health:
        def __init__(self, relative_path: str, status: str) -> None:
            self.path = tmp_path / relative_path
            self.relative_path = relative_path
            self.status = status
            self.tokens_total = 0
            self.error = None
            self.frontmatter = object()

    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *_a, **_kw: object())
    monkeypatch.setattr(
        cli_module,
        "inspect_directory_health",
        lambda *_a, **_kw: [_Health(".", "fresh"), _Health("src", "stale")],
    )
    monkeypatch.setattr(
        cli_module.api,
        "check",
        lambda *_a, **_kw: cli_module.api.CheckResult(
            mode="health",
            directories=[{"path": ".", "status": "fresh"}, {"path": "src", "status": "stale"}],
            summary={"total": 2, "fresh": 1, "stale": 1, "missing": 0},
        ),
    )

    status_result = runner.invoke(cli_module.cli, ["status", str(tmp_path)])
    check_result = runner.invoke(cli_module.cli, ["check", str(tmp_path)])

    assert status_result.exit_code == 0
    assert check_result.exit_code == 0
    assert "STATUS   PATH" in status_result.output
    assert "STATUS   PATH" in check_result.output


def test_legacy_clean_and_reset_dry_run_match(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    context_file = tmp_path / "CONTEXT.md"
    context_file.write_text("# root\n", encoding="utf-8")

    monkeypatch.setattr(
        cli_module.api,
        "reset",
        lambda *_a, **_kw: cli_module.api.ResetResult(manifests_removed=0, paths=["CONTEXT.md"]),
    )

    clean_result = runner.invoke(cli_module.cli, ["clean", str(tmp_path), "--dry-run"])
    reset_result = runner.invoke(cli_module.cli, ["reset", str(tmp_path), "--dry-run"])

    assert clean_result.exit_code == 0
    assert reset_result.exit_code == 0
    assert "would be deleted" in clean_result.output
    assert "would be deleted" in reset_result.output


def test_reset_json_mode_requires_yes(tmp_path) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    result = runner.invoke(
        cli_module.cli,
        ["reset", str(tmp_path)],
        env={"CTX_OUTPUT": "json"},
    )

    assert result.exit_code == 1
    assert "confirmation_required" in result.output
