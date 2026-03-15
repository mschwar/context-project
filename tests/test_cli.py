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


def test_stats_basic(tmp_path) -> None:
    """ctx stats should report covered/missing/stale counts."""
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # covered dir with manifest
    covered = root / "covered"
    covered.mkdir()
    (covered / "CONTEXT.md").write_text(
        "---\ntokens_total: 42\n---\n# Covered\n", encoding="utf-8"
    )

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
    (dir1 / "CONTEXT.md").write_text(
        "---\ntokens_total: 100\n---\n# Alpha\n", encoding="utf-8"
    )

    # dir2 with a manifest
    dir2 = root / "beta"
    dir2.mkdir()
    (dir2 / "CONTEXT.md").write_text(
        "---\ntokens_total: 200\n---\n# Beta\n", encoding="utf-8"
    )

    result = runner.invoke(cli_module.cli, ["stats", "--verbose", str(root)])

    assert result.exit_code == 0
    assert "Directory" in result.output
    assert "status" in result.output
    assert "tokens" in result.output
    assert "alpha" in result.output
    assert "beta" in result.output
    assert "covered" in result.output


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
    """ctx export --filter stale should only export manifests older than a source file."""
    import os
    import time

    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    root = tmp_path / "project"
    root.mkdir()

    # fresh dir — manifest is newer than source file
    fresh_dir = root / "fresh"
    fresh_dir.mkdir()
    (fresh_dir / "main.py").write_text("x = 1", encoding="utf-8")
    fresh_manifest = fresh_dir / "CONTEXT.md"
    fresh_manifest.write_text("fresh content", encoding="utf-8")
    # Make source file older than manifest
    os.utime(str(fresh_dir / "main.py"), (time.time() - 20, time.time() - 20))
    os.utime(str(fresh_manifest), (time.time(), time.time()))

    # stale dir — manifest is older than source file
    stale_dir = root / "stale"
    stale_dir.mkdir()
    (stale_dir / "main.py").write_text("y = 2", encoding="utf-8")
    stale_manifest = stale_dir / "CONTEXT.md"
    stale_manifest.write_text("stale content", encoding="utf-8")
    # Make manifest older than source file
    os.utime(str(stale_manifest), (time.time() - 20, time.time() - 20))
    os.utime(str(stale_dir / "main.py"), (time.time(), time.time()))

    result = runner.invoke(cli_module.cli, ["export", "--filter", "stale", str(root)])

    assert result.exit_code == 0
    assert "stale content" in result.output
    assert "fresh content" not in result.output


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
