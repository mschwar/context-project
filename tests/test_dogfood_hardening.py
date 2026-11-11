"""Zero-LLM dogfood hardening regression tests."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys

from click.testing import CliRunner
from fastapi.testclient import TestClient
import pytest

from ctx import api
from ctx.init import init_project
from ctx.sdk import CtxProject
from ctx.server import app


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), capture_output=True, check=True)
    (path / "app.py").write_text("def main() -> int:\n    return 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(path), capture_output=True, check=True)
    return path


def test_subcommand_output_json_export_collision_and_check_exit_json_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    repo = _make_git_repo(tmp_path / "cli_repo")

    res_fail = runner.invoke(cli_module.cli, ["check", str(repo), "--check-exit", "--output", "json"])
    assert res_fail.exit_code == 1
    env_fail = json.loads(res_fail.output)
    assert env_fail["errors"][0]["code"] == "stale_manifests"

    res_env_fail = runner.invoke(
        cli_module.cli, ["check", str(repo), "--check-exit"], env={"CTX_OUTPUT": "json"}
    )
    assert res_env_fail.exit_code == 1

    monkeypatch.chdir(tmp_path)
    res_cap = runner.invoke(
        cli_module.cli, ["export", str(repo), "--depth", "1", "--capsule", "--output", "json"]
    )
    assert res_cap.exit_code == 0
    assert not (tmp_path / "json").exists()
    cap_env = json.loads(res_cap.output)
    assert cap_env["status"] == "success"
    assert cap_env["data"]["repo_name"] == "cli_repo"

    out_file = tmp_path / "capsule.json"
    res_out = runner.invoke(
        cli_module.cli, ["export", str(repo), "--depth", "1", "--capsule", "--out-file", str(out_file)]
    )
    assert res_out.exit_code == 0
    assert out_file.is_file()


def test_deterministic_check_export_reset_and_http_serve(tmp_path: Path) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    repo = _make_git_repo(tmp_path / "tier2_repo")
    (repo / "AGENTS.md").write_text("# AGENTS\n\nRepo rules.\n", encoding="utf-8")

    init_project(repo)

    health = api.check(repo, check_exit=True)
    assert health.summary["fresh"] == 1
    assert health.summary["stale"] == 0
    assert health.summary["missing"] == 0

    verified = api.check(repo, verify=True, check_exit=True)
    assert verified.summary["invalid"] == 0

    stats = api.check(repo, stats=True)
    assert stats.summary["covered"] == 1
    assert stats.summary["missing"] == 0

    exp1 = api.export_context(repo, depth=1)
    assert exp1.manifests_exported == 1
    assert "tier: CONTEXT-1" in exp1.content

    # Legacy CONTEXT.md sidecar cleaned by reset without deleting .ctx/CONTEXT.md
    (repo / "CONTEXT.md").write_text("# legacy\n", encoding="utf-8")
    reset_res = api.reset(repo, yes=True)
    assert reset_res.manifests_removed == 1
    assert not (repo / "CONTEXT.md").exists()
    assert (repo / ".ctx" / "CONTEXT.md").is_file()

    # HTTP server serves root .ctx/CONTEXT.md and blocks internal .ctx path
    app.state.served_root = repo.resolve()
    client = TestClient(app)
    for route in ("/mcp/context/.", "/mcp/context"):
        r = client.get(route)
        assert r.status_code == 200
        assert "mode: tier2" in r.json()["content"]
    assert client.get("/mcp/context/.ctx").status_code == 404

    (repo / "app.py").write_text(
        "def main() -> int:\n    return 0\n\ndef added_api() -> str:\n    return 'v2'\n",
        encoding="utf-8",
    )
    stale_check = runner.invoke(cli_module.cli, ["check", str(repo), "--check-exit", "--output", "json"])
    assert stale_check.exit_code == 1
    stale_env = json.loads(stale_check.output)
    assert stale_env["data"]["summary"]["stale"] == 1


def test_refresh_updates_ctx_exports_without_llm_keys_or_leaf_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_git_repo(tmp_path / "refresh_repo")
    (repo / "src").mkdir()
    (repo / "src" / "service.py").write_text("def alpha() -> int:\n    return 1\n", encoding="utf-8")
    init_project(repo)

    res_fresh = api.refresh(repo)
    assert res_fresh.strategy == "tier2"
    assert res_fresh.dirs_processed == 0
    assert res_fresh.dirs_skipped >= 1
    assert not (repo / "CONTEXT.md").exists()
    assert not (repo / "src" / "CONTEXT.md").exists()

    (repo / "src" / "service.py").write_text(
        "def alpha() -> int:\n    return 1\n\ndef beta_new_export() -> str:\n    return 'ok'\n",
        encoding="utf-8",
    )
    proj = CtxProject.load(repo, walk_parents=False)
    assert proj.is_stale() is True

    dry = api.refresh(repo, dry_run=True)
    assert dry.stale_directories == ["."]

    refreshed = api.refresh(repo)
    assert refreshed.dirs_processed >= 1
    assert not (repo / "CONTEXT.md").exists()
    assert proj.is_stale() is False
    assert "beta_new_export" in proj.get_context(depth=1)

    monkeypatch.setitem(sys.modules, "ctx.skeleton", None)
    assert proj.is_stale() is False
