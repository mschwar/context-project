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
        progress(root / "docs", 1, 2, 50)
        progress(root, 2, 2, 99)
        return GenerateStats(
            dirs_processed=2,
            files_processed=4,
            tokens_used=99,
            errors=["docs: synthetic failure"],
        )

    monkeypatch.setattr(cli_module, "load_config", fake_load_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", fake_load_ignore_patterns)
    monkeypatch.setattr(cli_module, "create_client", fake_create_client)
    monkeypatch.setattr(cli_module, "generate_tree", fake_generate_tree)

    result = runner.invoke(
        cli_module.cli,
        ["init", str(tmp_path), "--provider", "openai", "--model", "gpt-test", "--max-depth", "3"],
    )

    assert result.exit_code == 1
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
        progress(root, 1, 1, 42)
        return GenerateStats(dirs_processed=1, dirs_skipped=2, tokens_used=42)

    monkeypatch.setattr(cli_module, "load_config", fake_load_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
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

    class _Health:
        def __init__(self, relative_path: str, status: str) -> None:
            self.relative_path = relative_path
            self.status = status

    def fake_inspect_directory_health(root: Path, spec: object, target_root: Path):
        calls["inspect_directory_health"] = (root, spec, target_root)
        return [
            _Health(".", "fresh"),
            _Health("src", "stale"),
            _Health("docs", "missing"),
        ]

    monkeypatch.setattr(cli_module, "load_ignore_patterns", fake_load_ignore_patterns)
    monkeypatch.setattr(cli_module, "inspect_directory_health", fake_inspect_directory_health)

    result = runner.invoke(cli_module.cli, ["status", str(tmp_path)])

    assert result.exit_code == 0
    assert calls["load_ignore_patterns"] == tmp_path
    assert calls["inspect_directory_health"] == (tmp_path, fake_spec, tmp_path)
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


def test_refresh_help_omits_hard_budget_guardrail_flags() -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    result = runner.invoke(cli_module.cli, ["refresh", "--help"])

    assert result.exit_code == 0
    assert "--max-tokens-per-run" not in result.output
    assert "--max-usd-per-run" not in result.output


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
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "update_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=1, dirs_skipped=2, tokens_used=1, budget_exhausted=True),
    )

    result = runner.invoke(cli_module.cli, ["update", str(root)])

    assert "budget" in result.output.lower()


def test_refresh_json_reports_budget_exhausted_code(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    budget_error = "Token budget guardrail reached: 5 tokens used (limit 5)."

    monkeypatch.setattr(
        cli_module.api,
        "refresh",
        lambda *_a, **_kw: cli_module.api.RefreshResult(
            dirs_processed=1,
            dirs_skipped=0,
            files_processed=1,
            tokens_used=5,
            errors=[budget_error],
            budget_exhausted=True,
            strategy="incremental",
            est_cost_usd=0.0,
            stale_directories=[],
            budget_guardrail=budget_error,
        ),
    )

    result = runner.invoke(cli_module.cli, ["refresh", str(tmp_path)], env={"CTX_OUTPUT": "json"})

    assert result.exit_code == 2
    assert '"code": "budget_exhausted"' in result.output


# --- init --overwrite ---


def test_init_no_overwrite_calls_update_tree(tmp_path, monkeypatch) -> None:
    """ctx init --no-overwrite should delegate to update_tree (skip fresh manifests)."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
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
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
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


def test_diff_since_flag_passes_ref_to_git(tmp_path, monkeypatch) -> None:
    """ctx diff --since <ref> should pass the ref to git diff."""
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        class R:
            stdout = ""
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--since", "main", str(root)])

    assert result.exit_code == 0
    assert any("main" in cmd for cmd in captured_cmds)
    assert "No CONTEXT.md files changed since main" in result.output


def test_diff_handles_unborn_head_without_fallback_warning(tmp_path, monkeypatch) -> None:
    """ctx diff should treat an empty repo as a first-class git state, not a git failure."""
    import subprocess

    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd == ["git", "diff", "--name-only", "HEAD", "--", "*/CONTEXT.md", "CONTEXT.md"]:
            raise subprocess.CalledProcessError(128, cmd, stderr="fatal: bad revision 'HEAD'")

        class R:
            returncode = 0

        r = R()
        if cmd == ["git", "diff", "--cached", "--name-only", "--", "*/CONTEXT.md", "CONTEXT.md"]:
            r.stdout = "src/CONTEXT.md\n"
        elif cmd == ["git", "ls-files", "--others", "--exclude-standard", "--", "*/CONTEXT.md", "CONTEXT.md"]:
            r.stdout = "tests/CONTEXT.md\n"
        else:
            r.stdout = ""
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", str(root)])

    assert result.exit_code == 0
    assert "[new] src/CONTEXT.md" in result.output
    assert "[new] tests/CONTEXT.md" in result.output
    assert "git not available" not in result.output


def test_diff_stat_handles_unborn_head(tmp_path, monkeypatch) -> None:
    """ctx diff --stat should count new manifests in repos without commits yet."""
    import subprocess

    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd == ["git", "diff", "--name-only", "HEAD", "--", "*/CONTEXT.md", "CONTEXT.md"]:
            raise subprocess.CalledProcessError(128, cmd, stderr="fatal: bad revision 'HEAD'")

        class R:
            returncode = 0

        r = R()
        if cmd == ["git", "diff", "--cached", "--name-only", "--", "*/CONTEXT.md", "CONTEXT.md"]:
            r.stdout = "src/CONTEXT.md\n"
        elif cmd == ["git", "ls-files", "--others", "--exclude-standard", "--", "*/CONTEXT.md", "CONTEXT.md"]:
            r.stdout = "tests/CONTEXT.md\n"
        else:
            r.stdout = ""
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--stat", str(root)])

    assert result.exit_code == 0
    assert "2 new" in result.output


# --- 16H: ctx diff --stat ---


def test_diff_stat_git_mode(tmp_path, monkeypatch) -> None:
    """ctx diff --stat should print summary count in git mode."""
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
            r.stdout = "src/CONTEXT.md\ndocs/CONTEXT.md\n"
        else:
            r.stdout = "new_dir/CONTEXT.md\n"
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--stat", str(root)])

    assert result.exit_code == 0
    assert "2 modified, 1 new" in result.output
    assert "[mod]" not in result.output  # no file list


def test_diff_stat_git_mode_no_changes(tmp_path, monkeypatch) -> None:
    """ctx diff --stat should report no changes when none exist."""
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

    result = runner.invoke(cli_module.cli, ["diff", "--stat", str(root)])

    assert result.exit_code == 0
    assert "No CONTEXT.md files changed" in result.output


def test_diff_stat_mtime_fallback(tmp_path, monkeypatch) -> None:
    """ctx diff --stat should work with mtime fallback."""
    import os
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = tmp_path / "project"
    root.mkdir()

    # Create a stale manifest
    stale_dir = root / "stale"
    stale_dir.mkdir()
    manifest = stale_dir / "CONTEXT.md"
    manifest.write_text("---\ntokens_total: 100\n---\n# Stale\n", encoding="utf-8")
    # Make manifest older than a source file
    old_time = 1000000000
    os.utime(manifest, (old_time, old_time))
    source_file = stale_dir / "main.py"
    source_file.write_text("x = 1", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--stat", str(root)])

    assert result.exit_code == 0
    assert "1 stale" in result.output
    assert "[stale]" not in result.output  # no file list


def test_diff_stat_with_since_flag(tmp_path, monkeypatch) -> None:
    """ctx diff --stat --since should work with custom ref."""
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        class R:
            stdout = "" if call_count == 1 else "src/CONTEXT.md\n"
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--stat", "--since", "v0.7.0", str(root)])

    assert result.exit_code == 0
    assert "1 new" in result.output


def test_diff_mtime_fallback(tmp_path, monkeypatch) -> None:
    """ctx diff falls back to mtime comparison when git is unavailable."""
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    # Create a directory with a source file newer than its CONTEXT.md
    project = tmp_path / "project"
    project.mkdir()
    manifest = project / "CONTEXT.md"
    manifest.write_text("# old", encoding="utf-8")
    src = project / "main.py"
    src.write_text("x = 1", encoding="utf-8")

    # Make src newer than manifest
    import os, time
    os.utime(str(manifest), (time.time() - 10, time.time() - 10))
    os.utime(str(src), (time.time(), time.time()))

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", str(project)])

    assert result.exit_code == 0
    assert "[stale]" in result.output
    assert "git not available" in result.output


# --- ctx diff --format json ---


def test_diff_format_json_git_path(tmp_path, monkeypatch) -> None:
    """ctx diff --format json should emit JSON with modified/new keys on git path."""
    import json
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
            # git diff --name-only: returns a modified file
            r.stdout = "src/CONTEXT.md\n"
        else:
            # git ls-files --others: returns a new file
            r.stdout = "new_dir/CONTEXT.md\n"
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--format", "json", str(root)])

    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert "modified" in data
    assert "new" in data
    assert "src/CONTEXT.md" in data["modified"]
    assert "new_dir/CONTEXT.md" in data["new"]


def test_diff_format_json_mtime_path(tmp_path, monkeypatch) -> None:
    """ctx diff --format json should emit JSON with stale key on mtime fallback path."""
    import json
    import subprocess
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    project = tmp_path / "project"
    project.mkdir()
    manifest = project / "CONTEXT.md"
    manifest.write_text("# old", encoding="utf-8")
    src = project / "main.py"
    src.write_text("x = 1", encoding="utf-8")

    import os, time
    os.utime(str(manifest), (time.time() - 10, time.time() - 10))
    os.utime(str(src), (time.time(), time.time()))

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--format", "json", str(project)])

    assert result.exit_code == 0
    # Warnings are written to stderr but CliRunner mixes them into output by default.
    # The JSON line is the last line of output.
    json_line = [line for line in result.output.splitlines() if line.startswith("{")]
    assert json_line, f"No JSON line found in output: {result.output!r}"
    data = json.loads(json_line[-1])
    assert "stale" in data
    assert isinstance(data["stale"], list)
    assert len(data["stale"]) >= 1


# --- ctx export ---


def test_export_stdout(tmp_path) -> None:
    """ctx export should concatenate CONTEXT.md files with headers to stdout."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root content", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub content", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", str(root)])

    assert result.exit_code == 0
    assert "# CONTEXT.md" in result.output
    assert "root content" in result.output
    assert "# sub/CONTEXT.md" in result.output
    assert "sub content" in result.output


def test_export_file(tmp_path) -> None:
    """ctx export --output should write concatenated manifests to a file."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root manifest", encoding="utf-8")

    out_file = tmp_path / "all.md"
    result = runner.invoke(cli_module.cli, ["export", str(root), "--output", str(out_file)])

    assert result.exit_code == 0
    assert "Exported" in result.output
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "root manifest" in content
    assert "# CONTEXT.md" in content


# --- ctx stats ---


def _write_stats_manifest(directory: Path, root: Path, *, tokens_total: int, body: str) -> None:
    """Write a valid manifest fixture for stats tests."""
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    from ctx.manifest import write_manifest

    spec = load_ignore_patterns(root)
    write_manifest(
        directory,
        model="test",
        content_hash=hash_directory(directory, spec, root),
        files=0,
        dirs=0,
        tokens_total=tokens_total,
        body=body,
    )


def test_stats_basic(tmp_path) -> None:
    """ctx stats should report covered/missing/stale counts."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # covered dir with manifest
    covered = root / "covered"
    covered.mkdir()
    _write_stats_manifest(covered, root, tokens_total=42, body="# Covered\n")

    # missing dir (no manifest)
    missing = root / "missing"
    missing.mkdir()
    (missing / "main.py").write_text("x = 1", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["stats", str(root)])

    assert result.exit_code == 0
    assert "dirs:" in result.output
    assert "covered:" in result.output
    assert "missing:" in result.output
    assert "stale:" in result.output
    assert "tokens:" in result.output
    # The missing dir should appear in missing count
    assert "1" in result.output  # at minimum 1 missing


def test_stats_no_manifests(tmp_path) -> None:
    """ctx stats with no CONTEXT.md files should report all dirs as missing."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "a").mkdir()
    (root / "b").mkdir()

    result = runner.invoke(cli_module.cli, ["stats", str(root)])

    assert result.exit_code == 0
    assert "covered: 0" in result.output
    assert "tokens:  0" in result.output


# --- 15.1: ctx stats --verbose ---


def test_stats_verbose_shows_per_dir_table(tmp_path) -> None:
    """ctx stats --verbose should show a per-directory breakdown table."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # dir1 with a manifest
    dir1 = root / "alpha"
    dir1.mkdir()
    _write_stats_manifest(dir1, root, tokens_total=100, body="# Alpha\n")

    # dir2 with a manifest
    dir2 = root / "beta"
    dir2.mkdir()
    _write_stats_manifest(dir2, root, tokens_total=200, body="# Beta\n")

    result = runner.invoke(cli_module.cli, ["stats", "--verbose", str(root)])

    assert result.exit_code == 0
    assert "Directory" in result.output
    assert "status" in result.output
    assert "tokens" in result.output
    assert "alpha" in result.output
    assert "beta" in result.output
    assert "covered" in result.output


# --- 16G: ctx stats --format json ---


def test_stats_format_json(tmp_path) -> None:
    """ctx stats --format json should output valid JSON with aggregate totals."""
    import json
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # covered dir with manifest
    covered = root / "covered"
    covered.mkdir()
    _write_stats_manifest(covered, root, tokens_total=42, body="# Covered\n")

    # missing dir (no manifest)
    missing = root / "missing"
    missing.mkdir()
    (missing / "main.py").write_text("x = 1", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["stats", "--format", "json", str(root)])

    assert result.exit_code == 0
    output = json.loads(result.output)
    
    assert "aggregate" in output
    agg = output["aggregate"]
    assert agg["dirs"] == 3  # root, covered, missing
    assert agg["covered"] == 1
    assert agg["missing"] == 2  # root + missing dir
    assert agg["tokens"] == 42
    assert "directories" not in output  # not verbose


def test_stats_format_json_verbose(tmp_path) -> None:
    """ctx stats --format json --verbose should include per-directory rows."""
    import json
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # dir1 with a manifest
    dir1 = root / "alpha"
    dir1.mkdir()
    _write_stats_manifest(dir1, root, tokens_total=100, body="# Alpha\n")

    # dir2 with a manifest
    dir2 = root / "beta"
    dir2.mkdir()
    _write_stats_manifest(dir2, root, tokens_total=200, body="# Beta\n")

    result = runner.invoke(cli_module.cli, ["stats", "--format", "json", "--verbose", str(root)])

    assert result.exit_code == 0
    output = json.loads(result.output)
    
    assert "aggregate" in output
    assert "directories" in output
    
    agg = output["aggregate"]
    assert agg["dirs"] == 3  # root, alpha, beta
    assert agg["covered"] == 2
    
    dirs = output["directories"]
    assert len(dirs) == 3  # root, alpha, beta
    
    # Find alpha and beta in the output
    alpha_dir = next((d for d in dirs if d["path"] == "alpha"), None)
    beta_dir = next((d for d in dirs if d["path"] == "beta"), None)
    assert alpha_dir is not None
    assert beta_dir is not None
    assert alpha_dir["status"] == "covered"
    assert beta_dir["status"] == "covered"
    assert alpha_dir["tokens"] == 100
    assert beta_dir["tokens"] == 200


def test_stats_format_json_values_match_text(tmp_path) -> None:
    """ctx stats JSON aggregate values should match text mode totals."""
    import json
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    covered = root / "covered"
    covered.mkdir()
    _write_stats_manifest(covered, root, tokens_total=500, body="# Covered\n")

    # Text output
    text_result = runner.invoke(cli_module.cli, ["stats", str(root)])
    json_result = runner.invoke(cli_module.cli, ["stats", "--format", "json", str(root)])

    assert text_result.exit_code == 0
    assert json_result.exit_code == 0
    
    json_output = json.loads(json_result.output)
    agg = json_output["aggregate"]
    
    # Parse text output to verify values match
    text_lines = text_result.output.splitlines()
    text_dirs = int(next(l for l in text_lines if l.startswith("dirs:")).split(":")[1].strip())
    text_covered = int(next(l for l in text_lines if l.startswith("covered:")).split(":")[1].strip())
    text_tokens = int(next(l for l in text_lines if l.startswith("tokens:")).split(":")[1].strip())
    
    assert agg["dirs"] == text_dirs
    assert agg["covered"] == text_covered
    assert agg["tokens"] == text_tokens


def test_stats_counts_stale_parents_via_hashes(tmp_path) -> None:
    """ctx stats should count parent directories stale when a child directory changes."""
    import json
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    from ctx.manifest import write_manifest

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    child = root / "src"
    root.mkdir()
    child.mkdir()
    (child / "main.py").write_text("print('v1')", encoding="utf-8")

    spec = load_ignore_patterns(root)
    write_manifest(
        child,
        model="test",
        content_hash=hash_directory(child, spec, root),
        files=1,
        dirs=0,
        tokens_total=10,
        body="# src\n",
    )
    write_manifest(
        root,
        model="test",
        content_hash=hash_directory(root, spec, root),
        files=0,
        dirs=1,
        tokens_total=20,
        body="# root\n",
    )

    (child / "main.py").write_text("print('v2')", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["stats", "--format", "json", str(root)])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["aggregate"]["covered"] == 2
    assert output["aggregate"]["stale"] == 2


def test_stats_treats_unreadable_manifest_state_as_stale(tmp_path, monkeypatch) -> None:
    """ctx stats should mark a covered directory stale if manifest loading races or fails."""
    import json
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    from ctx.manifest import write_manifest

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('ok')", encoding="utf-8")

    spec = load_ignore_patterns(root)
    write_manifest(
        root,
        model="test",
        content_hash=hash_directory(root, spec, root),
        files=1,
        dirs=0,
        tokens_total=10,
        body="# root\n",
    )

    class _Health:
        relative_path = "."
        status = "stale"
        tokens_total = None
        path = root

    monkeypatch.setattr(cli_module, "inspect_directory_health", lambda *args: [_Health()])

    result = runner.invoke(cli_module.cli, ["stats", "--format", "json", str(root)])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["aggregate"]["covered"] == 1
    assert output["aggregate"]["stale"] == 1
    assert output["aggregate"]["tokens"] == 0


# --- 15.2: ctx export --filter ---


def test_export_filter_all_default(tmp_path) -> None:
    """ctx export --filter all (default) should export all CONTEXT.md files."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root content", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub content", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", "--filter", "all", str(root)])

    assert result.exit_code == 0
    assert "root content" in result.output
    assert "sub content" in result.output


def test_export_filter_stale(tmp_path) -> None:
    """ctx export --filter stale should only export manifests with stale hashes."""

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    fresh_dir = root / "fresh"
    fresh_dir.mkdir()
    (fresh_dir / "main.py").write_text("x = 1", encoding="utf-8")
    _write_stats_manifest(fresh_dir, root, tokens_total=10, body="fresh content")

    stale_dir = root / "stale"
    stale_dir.mkdir()
    (stale_dir / "main.py").write_text("y = 2", encoding="utf-8")
    _write_stats_manifest(stale_dir, root, tokens_total=10, body="stale content")
    (stale_dir / "main.py").write_text("y = 3", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", "--filter", "stale", str(root)])

    assert result.exit_code == 0
    assert "stale content" in result.output
    assert "fresh content" not in result.output


def test_export_filter_stale_includes_parent_dirs_with_hash_drift(tmp_path) -> None:
    """ctx export --filter stale should include stale parents, not just changed leaf dirs."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    child = root / "src"
    root.mkdir()
    child.mkdir()
    (child / "main.py").write_text("print('v1')", encoding="utf-8")

    _write_stats_manifest(child, root, tokens_total=10, body="child manifest")
    _write_stats_manifest(root, root, tokens_total=20, body="root manifest")

    (child / "main.py").write_text("print('v2')", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", "--filter", "stale", str(root)])

    assert result.exit_code == 0
    assert "# CONTEXT.md" in result.output
    assert "# src/CONTEXT.md" in result.output


# --- 15.3: ctx diff --quiet ---


def test_diff_quiet_exits_0_when_clean(tmp_path, monkeypatch) -> None:
    """ctx diff --quiet should exit 0 and produce no output when no changes."""
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

    result = runner.invoke(cli_module.cli, ["diff", "--quiet", str(root)])

    assert result.exit_code == 0
    assert result.output == ""


def test_diff_quiet_exits_1_when_changes(tmp_path, monkeypatch) -> None:
    """ctx diff --quiet should exit 1 when changes are detected."""
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
            r.stdout = ""
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(cli_module.cli, ["diff", "--quiet", str(root)])

    assert result.exit_code == 1
    assert result.output == ""


# --- 15.5: ctx clean ---


def test_clean_removes_manifests_with_yes_flag(tmp_path) -> None:
    """ctx clean --yes should remove all CONTEXT.md files without prompting."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["clean", "--yes", str(root)])

    assert result.exit_code == 0
    assert "Removed 2 CONTEXT.md file(s)." in result.output
    assert not list(root.rglob("CONTEXT.md"))


def test_clean_aborts_without_confirmation(tmp_path) -> None:
    """ctx clean should abort when user answers 'n' to the confirmation prompt."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root", encoding="utf-8")

    # Provide 'n' as the user input
    result = runner.invoke(cli_module.cli, ["clean", str(root)], input="n\n")

    assert result.exit_code == 0
    assert "Aborted" in result.output
    # File should still exist
    assert (root / "CONTEXT.md").exists()


def test_clean_dry_run_lists_files_without_deleting(tmp_path) -> None:
    """ctx clean --dry-run should list files without deleting them."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["clean", "--dry-run", str(root)])

    assert result.exit_code == 0
    assert "2 CONTEXT.md file(s) would be deleted:" in result.output
    assert "CONTEXT.md" in result.output
    assert "sub/CONTEXT.md" in result.output
    # Files should still exist
    assert (root / "CONTEXT.md").exists()
    assert (sub / "CONTEXT.md").exists()


def test_clean_dry_run_no_files_found(tmp_path) -> None:
    """ctx clean --dry-run should report no files found when none exist."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    result = runner.invoke(cli_module.cli, ["clean", "--dry-run", str(root)])

    assert result.exit_code == 0
    assert "No CONTEXT.md files found." in result.output


# --- 15.6: ctx export --depth ---


def test_export_depth_0_only_root(tmp_path) -> None:
    """ctx export --depth 0 should only include root CONTEXT.md."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root content", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub content", encoding="utf-8")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "CONTEXT.md").write_text("deep content", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", "--depth", "0", str(root)])

    assert result.exit_code == 0
    assert "root content" in result.output
    assert "sub content" not in result.output
    assert "deep content" not in result.output


def test_export_depth_1_includes_one_level(tmp_path) -> None:
    """ctx export --depth 1 should include root and one level deep."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root content", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub content", encoding="utf-8")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "CONTEXT.md").write_text("deep content", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", "--depth", "1", str(root)])

    assert result.exit_code == 0
    assert "root content" in result.output
    assert "sub content" in result.output
    assert "deep content" not in result.output


def test_export_respects_ctxignore(tmp_path) -> None:
    """ctx export should exclude CONTEXT.md files in ignored directories."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root content", encoding="utf-8")

    # Create an ignored directory with a CONTEXT.md
    ignored = root / ".pytest_cache"
    ignored.mkdir()
    (ignored / "CONTEXT.md").write_text("ignored content", encoding="utf-8")

    # Create a normal subdirectory with a CONTEXT.md
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub content", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", str(root)])

    assert result.exit_code == 0
    assert "# CONTEXT.md" in result.output
    assert "root content" in result.output
    assert "# sub/CONTEXT.md" in result.output
    assert "sub content" in result.output
    # Ignored directory should not appear
    assert ".pytest_cache" not in result.output
    assert "ignored content" not in result.output


def test_export_respects_custom_ctxignore(tmp_path) -> None:
    """ctx export should respect custom .ctxignore patterns."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "CONTEXT.md").write_text("root content", encoding="utf-8")

    # Create a custom .ctxignore file
    (root / ".ctxignore").write_text("build/\n", encoding="utf-8")

    # Create an ignored directory with a CONTEXT.md
    build = root / "build"
    build.mkdir()
    (build / "CONTEXT.md").write_text("build content", encoding="utf-8")

    # Create a normal subdirectory with a CONTEXT.md
    sub = root / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("sub content", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["export", str(root)])

    assert result.exit_code == 0
    assert "# CONTEXT.md" in result.output
    assert "root content" in result.output
    assert "# sub/CONTEXT.md" in result.output
    assert "sub content" in result.output
    # Ignored directory should not appear
    assert "build/" not in result.output
    assert "build content" not in result.output


# --- 16E: ctx verify ---


def _write_verify_manifest(
    directory: Path,
    root: Path,
    *,
    body: str | None = None,
    purpose: str | None = None,
    tokens_total: int = 100,
) -> None:
    """Write a manifest fixture for verify tests."""
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns, should_ignore
    from ctx.manifest import write_manifest

    spec = load_ignore_patterns(root)
    if body is None:
        files = sorted(
            child.name
            for child in directory.iterdir()
            if child.is_file()
            and child.name != "CONTEXT.md"
            and not should_ignore(child, spec, root)
        )
        subdirs = sorted(
            child.name
            for child in directory.iterdir()
            if child.is_dir() and not should_ignore(child, spec, root)
        )
        lines = [
            f"# {directory.as_posix()}",
            "",
            purpose or f"{directory.name or directory.as_posix()} directory.",
            "",
            "## Files",
        ]
        if files:
            lines.extend(f"- **{name}** — Fixture summary for {name}" for name in files)
        else:
            lines.append("- None")
        lines.extend(["", "## Subdirectories"])
        if subdirs:
            lines.extend(f"- **{name}/** — Fixture summary for {name}" for name in subdirs)
        else:
            lines.append("- None")
        body = "\n".join(lines) + "\n"
        files_count = len(files)
        dirs_count = len(subdirs)
    else:
        files_count = sum(
            1
            for child in directory.iterdir()
            if child.is_file()
            and child.name != "CONTEXT.md"
            and not should_ignore(child, spec, root)
        )
        dirs_count = sum(
            1
            for child in directory.iterdir()
            if child.is_dir() and not should_ignore(child, spec, root)
        )
    write_manifest(
        directory,
        model="test",
        content_hash=hash_directory(directory, spec, root),
        files=files_count,
        dirs=dirs_count,
        tokens_total=tokens_total,
        body=body,
    )


def test_verify_all_valid_manifests(tmp_path) -> None:
    """ctx verify should exit 0 when all manifests are valid, fresh, and present."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    sub = root / "sub"
    sub.mkdir()
    _write_verify_manifest(sub, root, tokens_total=200)
    _write_verify_manifest(root, root, tokens_total=100)

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 0
    assert "All manifests are valid, present, and fresh." in result.output


def test_verify_missing_fields(tmp_path) -> None:
    """ctx verify should report missing required fields."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    # Missing 'model' and 'content_hash'
    (root / "CONTEXT.md").write_text(
        """---
generated: 2026-03-15T00:00:00Z
generator: ctx/0.8.0
files: 1
dirs: 0
tokens_total: 100
---
# Root manifest
""",
        encoding="utf-8",
    )

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Missing required fields:" in result.output
    assert "model, content_hash" in result.output or "content_hash, model" in result.output


def test_verify_malformed_frontmatter(tmp_path) -> None:
    """ctx verify should report malformed frontmatter separately."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    # Missing closing ---
    (root / "CONTEXT.md").write_text(
        """---
generated: 2026-03-15T00:00:00Z
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:abc123
files: 1
dirs: 0
tokens_total: 100
# No closing ---
""",
        encoding="utf-8",
    )

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Malformed frontmatter:" in result.output


def test_verify_mixed_valid_and_invalid(tmp_path) -> None:
    """ctx verify should report both malformed and missing fields."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # Malformed (no closing ---)
    malformed = root / "malformed"
    malformed.mkdir()
    (malformed / "CONTEXT.md").write_text(
        """---
generated: 2026-03-15T00:00:00Z
generator: ctx/0.8.0
model: claude-haiku-4-5-20251001
content_hash: sha256:def456
files: 1
dirs: 0
tokens_total: 100
# No closing ---
""",
        encoding="utf-8",
    )

    # Missing fields
    missing = root / "missing"
    missing.mkdir()
    (missing / "CONTEXT.md").write_text(
        """---
generated: 2026-03-15T00:00:00Z
generator: ctx/0.8.0
files: 1
---
# Missing model, content_hash, dirs, tokens_total
""",
        encoding="utf-8",
    )

    # Valid manifest written after child directories exist so the root hash is fresh.
    _write_verify_manifest(root, root)

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Malformed frontmatter:" in result.output
    assert "Missing required fields:" in result.output
    assert "Found 2 directory issue(s)." in result.output


def test_verify_respects_ctxignore(tmp_path) -> None:
    """ctx verify should skip manifests in ignored directories."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # Valid manifest at root
    _write_verify_manifest(root, root)

    # Invalid manifest in ignored directory
    ignored = root / ".pytest_cache"
    ignored.mkdir()
    (ignored / "CONTEXT.md").write_text(
        """---
# Missing all required fields
""",
        encoding="utf-8",
    )

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 0
    assert "All manifests are valid, present, and fresh." in result.output


def test_verify_no_manifests(tmp_path) -> None:
    """ctx verify should fail when directories are missing manifests."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "some_file.txt").write_text("hello", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Missing manifests:" in result.output
    assert "." in result.output


def test_verify_reports_stale_manifests(tmp_path) -> None:
    """ctx verify should fail when a manifest hash no longer matches current contents."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('v1')", encoding="utf-8")
    _write_verify_manifest(root, root)
    (root / "main.py").write_text("print('v2')", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Stale manifests:" in result.output
    assert "." in result.output


def test_verify_reports_missing_subdirectory_manifest(tmp_path) -> None:
    """ctx verify should fail when a child directory is missing its manifest."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    sub = root / "src"
    root.mkdir()
    sub.mkdir()
    _write_verify_manifest(root, root)

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Missing manifests:" in result.output
    assert "src" in result.output


def test_verify_format_json_reports_health_categories(tmp_path) -> None:
    """ctx verify --format json should emit machine-readable health output."""
    import json

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    stale = root / "stale"
    missing = root / "missing"
    root.mkdir()
    stale.mkdir()
    missing.mkdir()
    (stale / "main.py").write_text("print('v1')", encoding="utf-8")
    _write_verify_manifest(stale, root)
    _write_verify_manifest(root, root)
    (stale / "main.py").write_text("print('v2')", encoding="utf-8")

    result = runner.invoke(cli_module.cli, ["verify", "--format", "json", str(root)])

    assert result.exit_code == 1
    output = json.loads(result.output)
    assert output["aggregate"]["dirs"] == 3
    assert output["aggregate"]["invalid"] == 3
    assert "." in output["stale"]
    assert "stale" in output["stale"]
    assert "missing" in output["missing"]


def test_verify_reports_invalid_manifest_body(tmp_path) -> None:
    """ctx verify should fail when a manifest body disagrees with the filesystem."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()
    (root / "real.py").write_text("print('hi')\n", encoding="utf-8")
    _write_verify_manifest(
        root,
        root,
        body="\n".join(
            [
                f"# {root.as_posix()}",
                "",
                "Project root.",
                "",
                "## Files",
                "- **fake.py** — Hallucinated file",
                "",
                "## Subdirectories",
                "- None",
                "",
            ]
        ),
    )

    result = runner.invoke(cli_module.cli, ["verify", str(root)])

    assert result.exit_code == 1
    assert "Invalid manifest bodies:" in result.output
    assert "Files section is missing real entries: real.py" in result.output
    assert "Files section lists nonexistent entries: fake.py" in result.output


# --- Phase 17.1: non-zero exit on refresh errors ---


def test_init_exits_nonzero_when_errors(tmp_path, monkeypatch) -> None:
    """ctx init should exit 1 when any directory regeneration errors."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=1, errors=["src: [transient, retries exhausted] Connection error"]),
    )

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 1
    assert "Errors: 1" in result.output


def test_init_exits_zero_when_no_errors(tmp_path, monkeypatch) -> None:
    """ctx init should exit 0 when all directories complete without errors."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="openai", model="gpt-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=2, files_processed=4, tokens_used=50),
    )

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 0
    assert "Errors: 0" in result.output


def test_update_exits_nonzero_when_errors(tmp_path, monkeypatch) -> None:
    """ctx update should exit 1 when any directory regeneration errors."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "update_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=0, errors=["docs: [transient, retries exhausted] Connection error"]),
    )

    result = runner.invoke(cli_module.cli, ["update", str(root)])

    assert result.exit_code == 1
    assert "Errors: 1" in result.output


def test_update_exits_zero_when_no_errors(tmp_path, monkeypatch) -> None:
    """ctx update should exit 0 when all directories refresh without errors."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "update_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=3, dirs_skipped=1, tokens_used=120),
    )

    result = runner.invoke(cli_module.cli, ["update", str(root)])

    assert result.exit_code == 0
    assert "Errors: 0" in result.output


# --- Phase 17.2: setup --check connectivity probe ---


def test_setup_check_reports_ok_when_connectivity_succeeds(tmp_path, monkeypatch) -> None:
    """ctx setup --check should print preflight results and exit 0 when all checks pass."""
    from unittest.mock import patch
    from ctx.preflight import PreflightCheck, PreflightResult

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(name="connectivity", status="ok", detail="anthropic API reachable"),
        ],
        ready=True,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-abc")
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(cli_module.cli, ["setup", "--check", str(tmp_path)])

    assert result.exit_code == 0
    assert "[ OK ]" in result.output
    assert "Ready to run" in result.output


def test_setup_check_exits_nonzero_on_connectivity_failure(tmp_path, monkeypatch) -> None:
    """ctx setup --check should exit 1 when a preflight check fails."""
    from unittest.mock import patch
    from ctx.preflight import PreflightCheck, PreflightResult

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(
                name="connectivity",
                status="fail",
                detail="cannot reach anthropic API — Connection error.",
                fix="check your internet connection.",
            ),
        ],
        ready=False,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-abc")
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(cli_module.cli, ["setup", "--check", str(tmp_path)])

    assert result.exit_code == 1
    assert "[FAIL]" in result.output


def test_setup_check_shows_proxy_guidance_when_proxy_vars_set(tmp_path, monkeypatch) -> None:
    """ctx setup --check should include proxy info in the fix when connectivity fails with proxy vars."""
    from unittest.mock import patch
    from ctx.preflight import PreflightCheck, PreflightResult

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(
                name="connectivity",
                status="fail",
                detail="cannot reach anthropic API — Connection error: timed out.",
                fix="proxy env vars detected (HTTPS_PROXY). A broken proxy may be blocking requests.\n       Try unsetting: unset HTTPS_PROXY",
            ),
        ],
        ready=False,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-abc")
    monkeypatch.setenv("HTTPS_PROXY", "http://broken-proxy:8080")
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(cli_module.cli, ["setup", "--check", str(tmp_path)])

    assert result.exit_code == 1
    assert "HTTPS_PROXY" in result.output


def test_proxy_unset_hint_uses_powershell_commands_on_windows() -> None:
    """Windows proxy guidance should use PowerShell-friendly commands."""
    cli_module = import_module("ctx.cli")

    hint = cli_module._proxy_unset_hint(["HTTPS_PROXY", "ALL_PROXY"], platform_name="nt")

    assert "Remove-Item Env:HTTPS_PROXY" in hint
    assert "Remove-Item Env:ALL_PROXY" in hint
    assert "unset " not in hint


def test_proxy_unset_hint_uses_unset_on_posix() -> None:
    """POSIX proxy guidance should use unset syntax."""
    cli_module = import_module("ctx.cli")

    hint = cli_module._proxy_unset_hint(["HTTPS_PROXY", "ALL_PROXY"], platform_name="posix")

    assert hint == "unset HTTPS_PROXY ALL_PROXY"


def test_setup_check_skips_probe_for_local_providers(tmp_path, monkeypatch) -> None:
    """ctx setup --check should use _probe_local_models (not probe_provider_connectivity) for local providers."""
    from unittest.mock import patch
    from ctx.preflight import PreflightCheck, PreflightResult

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="ollama (Ollama running on localhost:11434)"),
            PreflightCheck(name="connectivity", status="ok", detail="ollama is running and has models loaded"),
        ],
        ready=True,
        provider="ollama",
        model="llama3.2",
    )

    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(cli_module.cli, ["setup", "--check", str(tmp_path)])

    assert result.exit_code == 0
    assert "[ OK ]" in result.output


# --- Phase 18.1: pre-flight connectivity check ---


def test_init_preflight_exits_on_connectivity_failure(tmp_path, monkeypatch) -> None:
    """ctx init should exit 1 before spending tokens if provider is unreachable."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: (False, "Connection error: refused"),
    )

    generate_calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: generate_calls.append("called") or GenerateStats(),
    )

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 1
    assert "Pre-flight check failed" in result.output
    assert not generate_calls  # LLM should never have been called


def test_update_preflight_exits_on_connectivity_failure(tmp_path, monkeypatch) -> None:
    """ctx update should exit 1 before spending tokens if provider is unreachable."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: (False, "Connection error: refused"),
    )

    update_calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "update_tree",
        lambda *a, **kw: update_calls.append("called") or GenerateStats(),
    )

    result = runner.invoke(cli_module.cli, ["update", str(root)])

    assert result.exit_code == 1
    assert "Pre-flight check failed" in result.output
    assert not update_calls  # LLM should never have been called


def test_preflight_skipped_for_local_providers(tmp_path, monkeypatch) -> None:
    """Pre-flight should not run for local providers (ollama, lmstudio)."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="ollama", model="llama3.2", api_key="not-needed", base_url="http://localhost:11434/v1")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())

    probe_calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: probe_calls.append(provider) or (True, None),
    )
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=1),
    )

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 0
    assert not probe_calls


def test_preflight_shows_proxy_guidance_on_failure(tmp_path, monkeypatch) -> None:
    """Pre-flight connectivity failure should mention active proxy env vars."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: (False, "Connection error: timed out"),
    )
    monkeypatch.setenv("ALL_PROXY", "http://broken:9999")

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 1
    assert "ALL_PROXY" in result.output


def test_preflight_passes_and_generation_proceeds(tmp_path, monkeypatch) -> None:
    """When pre-flight succeeds, generation should proceed normally."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: (True, None),
    )
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: GenerateStats(dirs_processed=2, files_processed=5, tokens_used=100),
    )

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 0
    assert "Directories processed: 2" in result.output


# --- Phase 18.2: proxy guidance in transient error tip ---


def test_transient_errors_show_proxy_guidance_when_proxy_set(tmp_path, monkeypatch) -> None:
    """Transient error tip should mention active proxy env vars."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: (True, None),
    )
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: GenerateStats(
            dirs_processed=1,
            errors=["src: [transient, retries exhausted] Connection error"],
        ),
    )
    monkeypatch.setenv("HTTPS_PROXY", "http://broken:8080")

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 1
    assert "HTTPS_PROXY" in result.output
    assert "broken proxy" in result.output.lower()


def test_transient_errors_no_proxy_guidance_when_no_proxy_set(tmp_path, monkeypatch) -> None:
    """Transient error tip should NOT mention proxies when none are set."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(
        cli_module,
        "probe_provider_connectivity",
        lambda provider, api_key, base_url=None: (True, None),
    )
    monkeypatch.setattr(
        cli_module,
        "generate_tree",
        lambda *a, **kw: GenerateStats(
            dirs_processed=1,
            errors=["src: [transient, retries exhausted] Connection error"],
        ),
    )
    # Ensure no proxy vars are set
    for v in cli_module.PROXY_ENV_VARS:
        monkeypatch.delenv(v, raising=False)

    result = runner.invoke(cli_module.cli, ["init", str(root)])

    assert result.exit_code == 1
    assert "Proxy env vars" not in result.output


# --- Phase 19: Real-World UX ---

def test_progress_callback_shows_tokens_and_elapsed() -> None:
    """Progress callback should display tokens and elapsed time."""
    import time
    cli_module = import_module("ctx.cli")
    
    # Use a time in the past to ensure elapsed > 0
    state = cli_module.ProgressState(start_time=time.time() - 0.1)
    callback = cli_module._progress_callback(state)
    
    # Simulate progress
    callback(Path("/test/src"), 1, 5, 1200)
    callback(Path("/test/docs"), 2, 5, 2500)
    
    # Elapsed should be increasing (at least 0.1s)
    assert state.elapsed() >= 0.05  # Allow some tolerance
    assert state.tokens_accumulated == 2500


def test_estimate_cost_anthropic_models() -> None:
    """Cost estimation for Anthropic models."""
    cli_module = import_module("ctx.cli")

    # Claude Opus 4 pricing (~$15/MTok)
    opus_cost = cli_module._estimate_cost(1_000_000, "anthropic", "claude-opus-4-20260301")
    assert 14.0 < opus_cost < 16.0

    # Claude Sonnet 4 pricing (~$3/MTok)
    sonnet_cost = cli_module._estimate_cost(1_000_000, "anthropic", "claude-sonnet-4-20260301")
    assert 2.5 < sonnet_cost < 3.5

    # Claude Haiku 4.5 pricing (~$0.80/MTok)
    haiku_cost = cli_module._estimate_cost(1_000_000, "anthropic", "claude-haiku-4-5-20251001")
    assert 0.7 < haiku_cost < 0.9

    # Claude 3 Haiku (legacy) pricing (~$0.25/MTok)
    haiku3_cost = cli_module._estimate_cost(1_000_000, "anthropic", "claude-3-haiku-20240307")
    assert 0.2 < haiku3_cost < 0.3

    # Default pricing for unknown anthropic model (~$0.80/MTok)
    default_cost = cli_module._estimate_cost(1_000_000, "anthropic", "claude-unknown")
    assert 0.7 < default_cost < 0.9


def test_estimate_cost_openai_models() -> None:
    """Cost estimation for OpenAI models."""
    cli_module = import_module("ctx.cli")
    
    # GPT-4 pricing (~$30/MTok)
    gpt4_cost = cli_module._estimate_cost(1_000_000, "openai", "gpt-4")
    assert 25.0 < gpt4_cost < 35.0
    
    # GPT-4o pricing (~$2.50/MTok)
    gpt4o_cost = cli_module._estimate_cost(1_000_000, "openai", "gpt-4o")
    assert 2.0 < gpt4o_cost < 3.0
    
    # GPT-3.5 pricing (~$0.50/MTok)
    gpt35_cost = cli_module._estimate_cost(1_000_000, "openai", "gpt-3.5-turbo")
    assert 0.4 < gpt35_cost < 0.6


def test_estimate_cost_local_providers() -> None:
    """Cost estimation for local providers should be $0."""
    cli_module = import_module("ctx.cli")
    
    ollama_cost = cli_module._estimate_cost(1_000_000, "ollama", "llama2")
    assert ollama_cost == 0.0
    
    lmstudio_cost = cli_module._estimate_cost(1_000_000, "lmstudio", "local-model")
    assert lmstudio_cost == 0.0


def test_estimate_cost_small_token_counts() -> None:
    """Cost estimation for small token counts."""
    cli_module = import_module("ctx.cli")
    
    # Small token count should produce small cost
    cost = cli_module._estimate_cost(1000, "anthropic", "claude-3-sonnet")
    assert 0.002 < cost < 0.004  # ~$0.003


def test_echo_cost_summary_format(tmp_path, monkeypatch, capsys) -> None:
    """Cost summary should be formatted correctly."""
    cli_module = import_module("ctx.cli")
    from click.testing import CliRunner
    
    runner = CliRunner()
    fake_config = Config(provider="anthropic", model="claude-3-sonnet", api_key="test-key")
    
    def fake_generate(root, config, client, spec, *, progress):
        progress(root, 1, 1, 50000)
        return GenerateStats(dirs_processed=1, tokens_used=50000)
    
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "generate_tree", fake_generate)
    
    result = runner.invoke(cli_module.cli, ["init", str(tmp_path)])
    
    assert result.exit_code == 0
    assert "Estimated cost:" in result.output
    # 50k tokens at $3/MTok = $0.15
    assert "$0.15" in result.output or "$0.1500" in result.output or "50,000 tokens" in result.output


def test_echo_cost_summary_local_provider(tmp_path, monkeypatch) -> None:
    """Cost summary for local provider should indicate $0."""
    cli_module = import_module("ctx.cli")
    from click.testing import CliRunner
    
    runner = CliRunner()
    fake_config = Config(provider="ollama", model="llama2", api_key="")
    
    def fake_generate(root, config, client, spec, *, progress):
        progress(root, 1, 1, 10000)
        return GenerateStats(dirs_processed=1, tokens_used=10000)
    
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "generate_tree", fake_generate)
    
    result = runner.invoke(cli_module.cli, ["init", str(tmp_path)])
    
    assert result.exit_code == 0
    assert "Estimated cost: $0.00 (local provider)" in result.output


def test_echo_cost_summary_zero_tokens(tmp_path, monkeypatch) -> None:
    """Cost summary should be skipped when no tokens used."""
    cli_module = import_module("ctx.cli")
    from click.testing import CliRunner
    
    runner = CliRunner()
    fake_config = Config(provider="anthropic", model="claude-test", api_key="test-key")
    
    def fake_generate(root, config, client, spec, *, progress):
        return GenerateStats(dirs_processed=0, tokens_used=0)
    
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "generate_tree", fake_generate)
    
    result = runner.invoke(cli_module.cli, ["init", str(tmp_path)])
    
    assert result.exit_code == 0
    assert "Estimated cost:" not in result.output


def test_format_elapsed_seconds_only() -> None:
    """Elapsed time under 60s should show as seconds."""
    cli_module = import_module("ctx.cli")
    
    assert cli_module._format_elapsed(0.5) == "0.5s"
    assert cli_module._format_elapsed(4.2) == "4.2s"
    assert cli_module._format_elapsed(59.9) == "59.9s"


def test_format_elapsed_minutes() -> None:
    """Elapsed time over 60s should show as minutes and seconds."""
    cli_module = import_module("ctx.cli")
    
    assert cli_module._format_elapsed(60.0) == "1m 0s"
    assert cli_module._format_elapsed(125.5) == "2m 5s"
    assert cli_module._format_elapsed(3600.0) == "60m 0s"


def test_update_command_shows_cost_summary(tmp_path, monkeypatch) -> None:
    """Update command should also show cost summary."""
    cli_module = import_module("ctx.cli")
    from click.testing import CliRunner
    
    runner = CliRunner()
    fake_config = Config(provider="openai", model="gpt-4o", api_key="test-key")
    
    def fake_update(root, config, client, spec, *, progress):
        progress(root, 1, 1, 25000)
        return GenerateStats(dirs_processed=1, dirs_skipped=2, tokens_used=25000)
    
    monkeypatch.setattr(cli_module, "load_config", lambda *a, **kw: fake_config)
    monkeypatch.setattr(cli_module, "load_ignore_patterns", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "create_client", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))
    monkeypatch.setattr(cli_module, "update_tree", fake_update)
    
    result = runner.invoke(cli_module.cli, ["update", str(tmp_path)])

    assert result.exit_code == 0
    assert "Estimated cost:" in result.output


# --- ctx stats --board ---


def _make_board_data(run_count: int = 3) -> dict:
    return {
        "schema_version": 1,
        "repo": "/some/repo",
        "aggregate": {
            "run_count": run_count,
            "total_dirs_processed": 100,
            "total_tokens_used": 50000,
            "total_tokens_saved": 20000,
            "total_cost_usd": 0.04,
            "total_cost_saved_usd": 0.016,
            "cache_hit_rate": 0.67,
        },
        "recent_runs": [
            {
                "ts": "2026-03-20T21:00:00.000Z",
                "dirs_processed": 18,
                "tokens_used": 15000,
                "tokens_saved": 6000,
                "est_cost_usd": 0.012,
                "cost_saved_usd": 0.005,
                "cache_hits": 20,
                "cache_misses": 10,
                "strategy": "incremental",
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
            }
        ],
    }


def _make_global_board_data() -> dict:
    return {
        "schema_version": 1,
        "repos": {
            "/repo/a": {"run_count": 5, "total_dirs_processed": 80, "total_cost_usd": 0.064},
        },
        "totals": {
            "repos_touched": 1,
            "total_runs": 5,
            "total_dirs_processed": 80,
            "total_tokens_used": 80000,
            "total_tokens_saved": 32000,
            "total_cost_usd": 0.064,
            "total_cost_saved_usd": 0.026,
        },
    }


def test_stats_board_human_mode(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    import ctx.stats_board as sb_module

    runner = CliRunner()

    monkeypatch.setattr(sb_module, "read_board", lambda root, config: _make_board_data())
    monkeypatch.setattr("ctx.cli.read_board", sb_module.read_board, raising=False)

    result = runner.invoke(cli_module.cli, ["stats", "--board", str(tmp_path)])

    assert result.exit_code == 0
    assert "Runs:" in result.output
    assert "Tokens used:" in result.output
    assert "Cost:" in result.output


def test_stats_board_global_mode(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    import ctx.stats_board as sb_module

    runner = CliRunner()

    monkeypatch.setattr(sb_module, "read_global_board", lambda **kw: _make_global_board_data())
    monkeypatch.setattr("ctx.cli.read_global_board", sb_module.read_global_board, raising=False)

    result = runner.invoke(cli_module.cli, ["stats", "--board", "--global", str(tmp_path)])

    assert result.exit_code == 0
    assert "Repos tracked:" in result.output


def test_stats_board_json_mode(tmp_path, monkeypatch) -> None:
    import json as _json
    cli_module = import_module("ctx.cli")
    import ctx.stats_board as sb_module

    runner = CliRunner()
    board = _make_board_data(run_count=7)
    monkeypatch.setattr(sb_module, "read_board", lambda root, config: board)
    monkeypatch.setattr("ctx.cli.read_board", sb_module.read_board, raising=False)

    result = runner.invoke(cli_module.cli, ["stats", "--board", "--format", "json", str(tmp_path)])

    assert result.exit_code == 0
    parsed = _json.loads(result.output)
    assert parsed["aggregate"]["run_count"] == 7


def test_stats_board_empty_state(tmp_path) -> None:
    cli_module = import_module("ctx.cli")

    runner = CliRunner()
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir()

    result = runner.invoke(cli_module.cli, ["stats", "--board", str(empty_dir)])

    assert result.exit_code == 0
    assert "No runs recorded yet." in result.output
