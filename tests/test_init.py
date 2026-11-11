"""Tests for deterministic zero-LLM ctx.init (init_project & uninit_project)."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ctx.init import (
    CTX_DIR,
    CTX_HOOK_END,
    CTX_HOOK_START,
    InitError,
    init_project,
    uninit_project,
)


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@local"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], capture_output=True, check=True)
    (path / "app.py").write_text("def main() -> int:\n    return 0\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], capture_output=True, check=True)
    return path


def test_init_requires_git_repo_and_force_to_reinit(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(InitError, match="Not a git repository"):
        init_project(plain)

    repo = _make_git_repo(tmp_path / "repo")
    res = init_project(repo)
    assert res["hooks_installed"] == []
    assert res["mode"] == "tier2"
    assert (repo / CTX_DIR / "CONTEXT-0.md").is_file()
    assert (repo / CTX_DIR / "CONTEXT-1.md").is_file()
    assert (repo / CTX_DIR / "CONTEXT.md").is_file()
    assert (repo / CTX_DIR / "metadata.json").is_file()
    assert ".ctx/" in (repo / ".gitignore").read_text(encoding="utf-8")
    assert not (repo / ".git" / "hooks" / "post-commit").exists()

    with pytest.raises(InitError, match="Already initialized"):
        init_project(repo)

    res_force = init_project(repo, force=True)
    assert res_force["force"] is True


def test_init_and_uninit_strip_legacy_ctx_hook_blocks_while_preserving_user_hooks(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "legacy_hook_repo")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Hook with both user commands and a legacy ctx block -> user command preserved
    post_commit = hooks_dir / "post-commit"
    post_commit.write_text(
        f"#!/bin/sh\necho 'custom user hook'\n{CTX_HOOK_START}\nctx _hook --trigger post-commit --root .\n{CTX_HOOK_END}\n",
        encoding="utf-8",
    )
    post_commit.chmod(0o755)

    # Hook containing ONLY a legacy ctx block -> deleted cleanly
    post_merge = hooks_dir / "post-merge"
    post_merge.write_text(
        f"#!/bin/sh\n{CTX_HOOK_START}\nctx _hook --trigger post-merge --root .\n{CTX_HOOK_END}\n",
        encoding="utf-8",
    )
    post_merge.chmod(0o755)

    init_project(repo)
    assert post_commit.is_file()
    pc_text = post_commit.read_text(encoding="utf-8")
    assert "custom user hook" in pc_text
    assert CTX_HOOK_START not in pc_text
    assert not post_merge.exists()

    # Uninit removes .ctx/ and cleans .gitignore
    un_res = uninit_project(repo)
    assert un_res["ctx_dir_removed"] is True
    assert not (repo / CTX_DIR).exists()
    gitignore_text = (repo / ".gitignore").read_text(encoding="utf-8") if (repo / ".gitignore").exists() else ""
    assert ".ctx/" not in gitignore_text

    with pytest.raises(InitError, match="Not initialized"):
        uninit_project(repo)
