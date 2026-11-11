"""End-to-end zero-LLM CLI coverage on the sample fixture project."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from click.testing import CliRunner

from ctx.cli import cli


def _copy_sample_project(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "sample_project"
    destination = tmp_path / "sample_project"
    shutil.copytree(source, destination)
    subprocess.run(["git", "init", str(destination)], capture_output=True, check=True)
    return destination


def test_deterministic_end_to_end_init_check_export_impact_and_refresh(tmp_path: Path) -> None:
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    res_init = runner.invoke(cli, ["init", str(root), "--output", "json"])
    assert res_init.exit_code == 0, res_init.output
    init_env = json.loads(res_init.output)
    assert init_env["status"] == "success"
    assert init_env["data"]["hooks_installed"] == []
    assert not (root / "CONTEXT.md").exists()
    assert (root / ".ctx" / "CONTEXT-0.md").is_file()
    assert (root / ".ctx" / "CONTEXT-1.md").is_file()
    assert (root / ".ctx" / "CONTEXT.md").is_file()

    res_check = runner.invoke(cli, ["check", str(root), "--verify", "--check-exit", "--output", "json"])
    assert res_check.exit_code == 0, res_check.output
    assert json.loads(res_check.output)["data"]["summary"]["invalid"] == 0

    res_cap = runner.invoke(cli, ["export", str(root), "--capsule", "--output", "json"])
    assert res_cap.exit_code == 0, res_cap.output
    cap_data = json.loads(res_cap.output)["data"]
    assert cap_data["total_files"] >= 2
    assert "Python" in cap_data["languages"]

    # Add a new public symbol -> check marks .ctx/ stale -> refresh restores freshness with 0 LLM tokens
    (root / "src" / "new_mod.py").write_text("def exported_fn() -> int:\n    return 42\n", encoding="utf-8")
    res_stale = runner.invoke(cli, ["check", str(root), "--check-exit", "--output", "json"])
    assert res_stale.exit_code == 1

    res_refresh = runner.invoke(cli, ["refresh", str(root), "--output", "json"])
    assert res_refresh.exit_code == 0, res_refresh.output
    ref_env = json.loads(res_refresh.output)
    assert ref_env["metadata"]["tokens_used"] == 0
    assert ref_env["data"]["dirs_processed"] >= 1
    assert "exported_fn" in (root / ".ctx" / "CONTEXT.md").read_text(encoding="utf-8")

    res_fresh = runner.invoke(cli, ["check", str(root), "--verify", "--check-exit"])
    assert res_fresh.exit_code == 0, res_fresh.output
