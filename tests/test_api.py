"""Tests for deterministic zero-LLM ctx.api."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ctx import api
from ctx.init import init_project


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    (path / "AGENTS.md").write_text("# AGENTS\n\nRepo governance.\n", encoding="utf-8")
    pkg = path / "src" / "demo"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service.py").write_text("def compute(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    return path


def test_api_check_missing_before_init_and_fresh_after_init(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "repo")

    missing = api.check(repo)
    assert missing.mode == "health"
    assert missing.summary["missing"] == 1
    assert missing.summary["fresh"] == 0

    init_project(repo)
    fresh = api.check(repo)
    assert fresh.summary["fresh"] == 1
    assert fresh.summary["stale"] == 0
    assert fresh.summary["missing"] == 0

    verified = api.check(repo, verify=True)
    assert verified.mode == "verify"
    assert verified.summary["invalid"] == 0

    stats = api.check(repo, stats=True, verbose=True)
    assert stats.mode == "stats"
    assert stats.summary["covered"] == 1
    assert stats.summary["tokens"] > 0
    assert len(stats.directories) == 1

    with pytest.raises(ValueError, match="Only one check mode"):
        api.check(repo, verify=True, stats=True)


def test_api_refresh_skips_when_unchanged_and_updates_on_structural_drift(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    init_project(repo)

    skip_res = api.refresh(repo)
    assert skip_res.dirs_processed == 0
    assert skip_res.dirs_skipped >= 1
    assert skip_res.tokens_used == 0

    # Internal body edit without signature change does not mark .ctx/ stale
    (repo / "src" / "demo" / "service.py").write_text(
        "def compute(x: int) -> int:\n    y = x * 2\n    return y - x + 1\n",
        encoding="utf-8",
    )
    assert api.check(repo).summary["fresh"] == 1

    # Public signature addition marks .ctx/ stale -> dry_run reports ["."] -> refresh updates
    (repo / "src" / "demo" / "service.py").write_text(
        "def compute(x: int) -> int:\n    return x + 1\n\ndef new_public_api() -> str:\n    return 'v2'\n",
        encoding="utf-8",
    )
    assert api.check(repo).summary["stale"] == 1
    assert api.check(repo, diff=True).summary["stale"] == 1

    dry = api.refresh(repo, dry_run=True)
    assert dry.stale_directories == ["."]
    assert dry.dirs_processed == 0

    updated = api.refresh(repo)
    assert updated.dirs_processed >= 1
    assert api.check(repo, verify=True).summary["invalid"] == 0
    assert "new_public_api" in (repo / ".ctx" / "CONTEXT-1.md").read_text(encoding="utf-8")


def test_api_export_context_initialized_and_zero_setup_on_the_fly(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "uninit_repo")

    # Zero-setup export renders deterministic skeleton on the fly!
    on_the_fly = api.export_context(repo, depth=0)
    assert on_the_fly.manifests_exported == 1
    assert "Architecture & Authority Map (CONTEXT-0)" in on_the_fly.content

    missing_exp = api.export_context(repo, filter_mode="missing")
    assert missing_exp.manifests_exported == 1
    assert "[MISSING]" in missing_exp.content

    init_project(repo)
    exp1 = api.export_context(repo, depth=1)
    assert exp1.manifests_exported == 1
    assert "tier: CONTEXT-1" in exp1.content

    stale_none = api.export_context(repo, filter_mode="stale")
    assert stale_none.manifests_exported == 0


def test_api_reset_removes_legacy_manifests_and_preserves_ctx_dir(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "reset_repo")
    init_project(repo)
    (repo / "CONTEXT.md").write_text("# legacy root\n", encoding="utf-8")
    (repo / "src" / "CONTEXT.md").write_text("# legacy src\n", encoding="utf-8")

    with pytest.raises(api.ConfirmationRequiredError):
        api.reset(repo, yes=False)

    dry = api.reset(repo, dry_run=True)
    assert dry.manifests_removed == 0
    assert set(dry.paths) == {"CONTEXT.md", "src/CONTEXT.md"}

    removed = api.reset(repo, yes=True)
    assert removed.manifests_removed == 2
    assert not (repo / "CONTEXT.md").exists()
    assert (repo / ".ctx" / "CONTEXT.md").is_file()


def test_api_capsule_and_impact(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "cap_repo")
    (repo / "src" / "demo" / "caller.py").write_text(
        "from demo.service import compute\n\ndef invoke() -> int:\n    return compute(2)\n",
        encoding="utf-8",
    )

    cap = api.build_fleet_capsule(repo, depth=1)
    assert cap.repo_name == "cap_repo"
    assert cap.languages["Python"] >= 2

    impact = api.analyze_impact(repo, "src/demo/service.py")
    assert "src/demo/caller.py" in impact.direct_inbound_dependents
