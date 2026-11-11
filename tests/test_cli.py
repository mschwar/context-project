"""Tests for deterministic zero-LLM Click CLI (`ctx.cli`)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

from ctx.cli import cli


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    (path / "AGENTS.md").write_text("# AGENTS\n\nRules.\n", encoding="utf-8")
    pkg = path / "src" / "pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("def core_fn() -> int:\n    return 1\n", encoding="utf-8")
    (pkg / "cli_mod.py").write_text(
        "from pkg.core import core_fn\n\ndef entry() -> int:\n    return core_fn()\n",
        encoding="utf-8",
    )
    return path


def test_cli_init_check_refresh_and_uninit_human_and_json(tmp_path: Path) -> None:
    runner = CliRunner()
    repo = _make_git_repo(tmp_path / "repo")

    # Missing before init
    res_missing = runner.invoke(cli, ["check", str(repo), "--check-exit"])
    assert res_missing.exit_code == 1

    # Init in human mode
    res_init = runner.invoke(cli, ["init", str(repo)])
    assert res_init.exit_code == 0, res_init.output
    assert "Initialized ctx" in res_init.output

    # Check health, verify, stats, diff
    assert runner.invoke(cli, ["check", str(repo), "--check-exit"]).exit_code == 0
    assert runner.invoke(cli, ["check", str(repo), "--verify"]).exit_code == 0
    res_stats = runner.invoke(cli, ["check", str(repo), "--stats", "--verbose"])
    assert res_stats.exit_code == 0
    assert "covered: 1" in res_stats.output
    assert runner.invoke(cli, ["check", str(repo), "--diff", "--stat"]).exit_code == 0

    # Refresh dry-run and no-op refresh
    res_dry = runner.invoke(cli, ["refresh", str(repo), "--dry-run"])
    assert res_dry.exit_code == 0
    assert "All .ctx/ maps are fresh" in res_dry.output

    res_ref = runner.invoke(cli, ["refresh", str(repo), "--output", "json"])
    assert res_ref.exit_code == 0
    env_ref = json.loads(res_ref.output)
    assert env_ref["status"] == "success"
    assert env_ref["data"]["dirs_processed"] == 0

    # Uninit
    res_uninit = runner.invoke(cli, ["uninit", str(repo), "--output", "json"])
    assert res_uninit.exit_code == 0
    assert json.loads(res_uninit.output)["data"]["ctx_dir_removed"] is True


def test_cli_export_capsule_impact_and_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    repo = _make_git_repo(tmp_path / "repo")
    monkeypatch.chdir(tmp_path)

    # Export --capsule --output json does NOT write a file named "json"
    res_cap = runner.invoke(cli, ["export", str(repo), "--capsule", "--output", "json"])
    assert res_cap.exit_code == 0
    assert not (tmp_path / "json").exists()
    cap_env = json.loads(res_cap.output)
    assert cap_env["data"]["repo_name"] == "repo"

    # Impact in human & JSON modes
    res_imp = runner.invoke(cli, ["impact", "src/pkg/core.py", str(repo)])
    assert res_imp.exit_code == 0
    assert "src/pkg/cli_mod.py" in res_imp.output

    res_imp_bad = runner.invoke(cli, ["impact", "nonexistent_target_xyz", str(repo), "--output", "json"])
    assert res_imp_bad.exit_code == 1
    assert json.loads(res_imp_bad.output)["errors"][0]["code"] == "invalid_target"

    # Reset requires --yes in JSON mode
    (repo / "CONTEXT.md").write_text("# legacy\n", encoding="utf-8")
    res_reset_no_yes = runner.invoke(cli, ["reset", str(repo), "--output", "json"])
    assert res_reset_no_yes.exit_code == 1
    assert json.loads(res_reset_no_yes.output)["errors"][0]["code"] == "confirmation_required"

    res_reset_yes = runner.invoke(cli, ["reset", str(repo), "--yes", "--output", "json"])
    assert res_reset_yes.exit_code == 0
    assert json.loads(res_reset_yes.output)["data"]["manifests_removed"] == 1
