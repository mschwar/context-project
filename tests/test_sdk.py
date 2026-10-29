"""Tests for ctx.sdk — zero-dependency reader for .ctx/ exports and metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctx.sdk import CtxProject, CtxProjectNotFoundError


def _seed_ctx_dir(root: Path) -> Path:
    ctx_dir = root / ".ctx"
    ctx_dir.mkdir(parents=True)
    (ctx_dir / "CONTEXT.md").write_text("# Full context\n", encoding="utf-8")
    (ctx_dir / "CONTEXT-1.md").write_text("# Depth 1 context\n", encoding="utf-8")
    (ctx_dir / "CONTEXT-0.md").write_text("# Depth 0 context\n", encoding="utf-8")
    (ctx_dir / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "initialized_at": "2026-10-29T00:00:00Z",
                "initialized_by": "prime",
                "ctx_version": "1.1.0",
                "repo_id": "sha256:abc123",
                "last_refresh": "2026-10-29T01:00:00Z",
                "python_executable": "/usr/bin/python3",
                "hooks_installed": ["post-commit", "post-checkout", "post-merge"],
                "mode": "tier2",
                "structural_hash": "sha256:struct1",
                "boundary_doc_hash": "sha256:doc1",
            }
        ),
        encoding="utf-8",
    )
    (ctx_dir / "hook_log.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "timestamp": "2026-10-29T01:00:00Z",
                        "trigger": "post-commit",
                        "duration_ms": 42,
                        "success": True,
                        "error": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return ctx_dir


def test_sdk_load_reads_exports_metadata_and_hooks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)
    _seed_ctx_dir(repo)

    project = CtxProject.load(nested)
    assert project.root == repo.resolve()
    assert project.context_full == "# Full context\n"
    assert project.context_depth_1 == "# Depth 1 context\n"
    assert project.context_depth_0 == "# Depth 0 context\n"
    assert project.get_export(None) == "# Full context\n"
    assert project.get_export(1) == "# Depth 1 context\n"
    assert project.get_export(0) == "# Depth 0 context\n"

    meta = project.metadata
    assert meta.repo_id == "sha256:abc123"
    assert meta.mode == "tier2"
    assert meta.structural_hash == "sha256:struct1"
    assert meta.boundary_doc_hash == "sha256:doc1"
    assert meta.hooks_installed == ["post-commit", "post-checkout", "post-merge"]

    hooks = project.hook_runs
    assert len(hooks) == 1
    assert hooks[0].trigger == "post-commit"
    assert hooks[0].duration_ms == 42
    assert hooks[0].success is True

    snapshot = project.to_dict()
    assert snapshot["available_tiers"] == {
        "CONTEXT.md": True,
        "CONTEXT-1.md": True,
        "CONTEXT-0.md": True,
    }


def test_sdk_load_raises_when_not_initialized(tmp_path: Path) -> None:
    with pytest.raises(CtxProjectNotFoundError, match="ctx init"):
        CtxProject.load(tmp_path, walk_parents=False)


def test_sdk_get_export_rejects_invalid_depth(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_ctx_dir(repo)
    project = CtxProject.load(repo, walk_parents=False)

    with pytest.raises(ValueError, match="Unsupported export depth tier"):
        project.get_export(2)
