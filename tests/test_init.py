"""Tests for ctx.init — ctx init / uninit / hook runtime.

23 test cases covering:
  - init happy path (#1-4)
  - init edge cases (#5-9)
  - uninit (#10-13)
  - hook runtime (#14-16)
  - file content (#17-18)
  - PID debounce (#19)
  - E2E roundtrip (#20)
  - Added during eng review (#21-23)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ctx.init import (
    InitError,
    init_project,
    uninit_project,
    run_hook,
    CTX_DIR,
    CTX_HOOK_START,
    CTX_HOOK_END,
    HOOK_NAMES,
    METADATA_FILE,
    HOOK_LOG_FILE,
    PID_FILE,
    _acquire_pid,
    _release_pid,
    _pid_alive,
    _generate_hook_script,
    _add_to_gitignore,
    _remove_from_gitignore,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _make_git_repo(path: Path) -> Path:
    """Create a minimal git repo with one committed file."""
    path.mkdir(exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path), capture_output=True, check=True,
    )
    # Create a file so refresh has something to process
    (path / "hello.py").write_text("# hello world\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "."], cwd=str(path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), capture_output=True, check=True,
    )
    return path


def _mock_refresh(root, **kwargs):
    """Mock api.refresh to avoid LLM calls."""
    from ctx.api import RefreshResult
    # Write a minimal CONTEXT.md so export has something to read
    context_path = root / "CONTEXT.md"
    if not context_path.exists():
        context_path.write_text(
            "---\ngenerated: '2026-01-01T00:00:00Z'\ngenerator: ctx/1.0.0\n"
            "content_hash: 'sha256:abc'\nfiles: 1\ndirs: 0\ntokens_total: 100\n---\n"
            "# test\n\nTest directory.\n\n## Files\n- **hello.py** — hello world\n",
            encoding="utf-8",
        )
    return RefreshResult(
        dirs_processed=1,
        dirs_skipped=0,
        files_processed=1,
        tokens_used=100,
        errors=[],
        budget_exhausted=False,
        strategy="full",
        est_cost_usd=0.001,
        stale_directories=[],
    )


# ── Test 1: init creates .ctx/ with all expected files ──────────────

def test_init_creates_ctx_dir(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        result = init_project(repo)

    ctx_dir = repo / CTX_DIR
    assert ctx_dir.is_dir()
    assert (ctx_dir / "CONTEXT.md").exists()
    assert (ctx_dir / "CONTEXT-1.md").exists()
    assert (ctx_dir / "CONTEXT-0.md").exists()
    assert (ctx_dir / METADATA_FILE).exists()
    assert (ctx_dir / ".gitignore").exists()
    assert result["ctx_dir"] == str(ctx_dir)


# ── Test 2: init generates all 3 depth-tiered exports ───────────────

def test_init_generates_depth_tiered_exports(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        result = init_project(repo)

    assert result["exports"] == ["CONTEXT.md", "CONTEXT-1.md", "CONTEXT-0.md"]
    for name in result["exports"]:
        content = (repo / CTX_DIR / name).read_text(encoding="utf-8")
        assert len(content) > 0


# ── Test 3: init writes metadata.json with correct fields ───────────

def test_init_writes_metadata(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    meta = json.loads((repo / CTX_DIR / METADATA_FILE).read_text(encoding="utf-8"))
    assert meta["schema_version"] == 1
    assert "initialized_at" in meta
    assert "initialized_by" in meta
    assert "ctx_version" in meta
    assert meta["repo_id"].startswith("sha256:")
    assert "last_refresh" in meta
    assert "python_executable" in meta
    assert meta["hooks_installed"] == list(HOOK_NAMES)


# ── Test 4: init installs all 3 hooks ───────────────────────────────

def test_init_installs_hooks(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        result = init_project(repo)

    hooks_dir = repo / ".git" / "hooks"
    for hook_name in HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        assert hook_path.exists(), f"{hook_name} not installed"
        content = hook_path.read_text(encoding="utf-8")
        assert CTX_HOOK_START in content
        assert CTX_HOOK_END in content
        assert "#!/bin/sh" in content

    assert set(result["hooks_installed"]) == set(HOOK_NAMES)


# ── Test 5: init --force reinitializes cleanly ───────────────────────

def test_init_force_reinitializes(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)
        # Should not raise with --force
        result = init_project(repo, force=True)

    assert result["force"] is True
    assert (repo / CTX_DIR / METADATA_FILE).exists()


# ── Test 6: init on non-git directory fails ──────────────────────────

def test_init_non_git_fails(tmp_path) -> None:
    non_git = tmp_path / "not-a-repo"
    non_git.mkdir()
    with pytest.raises(InitError, match="Not a git repository"):
        init_project(non_git)


# ── Test 7: init when already initialized fails ─────────────────────

def test_init_already_initialized_fails(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)
        with pytest.raises(InitError, match="Already initialized"):
            init_project(repo)


# ── Test 8: init with existing hooks chains correctly ────────────────

def test_init_chains_existing_hooks(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    # Pre-existing post-commit hook
    existing_hook = hooks_dir / "post-commit"
    existing_hook.write_text("#!/bin/sh\necho 'pre-existing hook'\n", encoding="utf-8")

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    content = existing_hook.read_text(encoding="utf-8")
    # Both the original and ctx block should be present
    assert "pre-existing hook" in content
    assert CTX_HOOK_START in content
    assert CTX_HOOK_END in content


# ── Test 9: init with existing ctx hooks updates in place ────────────

def test_init_updates_existing_ctx_hooks(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    # Manually add extra content to hook
    hook_path = repo / ".git" / "hooks" / "post-commit"
    content = hook_path.read_text(encoding="utf-8")
    hook_path.write_text(content + "echo 'extra'\n", encoding="utf-8")

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo, force=True)

    updated = hook_path.read_text(encoding="utf-8")
    # ctx block should be updated, extra content preserved
    assert CTX_HOOK_START in updated
    assert "extra" in updated
    # Only one ctx block
    assert updated.count(CTX_HOOK_START) == 1


# ── Test 10: uninit removes hooks and .ctx/ ──────────────────────────

def test_uninit_removes_all(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    result = uninit_project(repo)

    assert not (repo / CTX_DIR).exists()
    for hook_name in HOOK_NAMES:
        hook_path = repo / ".git" / "hooks" / hook_name
        # Hook files that were ctx-only should be deleted
        if hook_path.exists():
            content = hook_path.read_text(encoding="utf-8")
            assert CTX_HOOK_START not in content

    assert set(result["hooks_removed"]) == set(HOOK_NAMES)
    assert result["ctx_dir_removed"] is True


# ── Test 11: uninit when not initialized fails ───────────────────────

def test_uninit_not_initialized_fails(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with pytest.raises(InitError, match="Not initialized"):
        uninit_project(repo)


# ── Test 12: uninit preserves non-ctx hook content ───────────────────

def test_uninit_preserves_non_ctx_hooks(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    # Pre-existing hook
    existing_hook = hooks_dir / "post-commit"
    existing_hook.write_text("#!/bin/sh\necho 'keep me'\n", encoding="utf-8")

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    uninit_project(repo)

    # Pre-existing content should survive
    assert existing_hook.exists()
    content = existing_hook.read_text(encoding="utf-8")
    assert "keep me" in content
    assert CTX_HOOK_START not in content


# ── Test 13: uninit removes .ctx/ from root .gitignore ───────────────

def test_uninit_cleans_gitignore(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    gitignore = repo / ".gitignore"
    assert ".ctx/" in gitignore.read_text(encoding="utf-8")

    uninit_project(repo)

    if gitignore.exists():
        assert ".ctx/" not in gitignore.read_text(encoding="utf-8")


# ── Test 14: hook runs refresh in background ─────────────────────────

def test_hook_runs_refresh(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    ctx_dir = repo / CTX_DIR
    ctx_dir.mkdir()
    # Write minimal metadata so run_hook can update it
    meta = {"schema_version": 1, "last_refresh": "old"}
    (ctx_dir / METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")
    # Write a CONTEXT.md so export works
    _mock_refresh(repo)

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        run_hook(repo, "post-commit")

    # Verify metadata was updated
    updated_meta = json.loads((ctx_dir / METADATA_FILE).read_text(encoding="utf-8"))
    assert updated_meta["last_refresh"] != "old"


# ── Test 15: hook handles missing Python gracefully ──────────────────

def test_hook_script_has_python_fallback(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    script = _generate_hook_script(repo)
    assert 'if [ ! -x "$_CTX_PYTHON" ]' in script
    assert '_CTX_PYTHON="python3"' in script


# ── Test 16: hook telemetry writes to hook_log.json ──────────────────

def test_hook_writes_telemetry(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    ctx_dir = repo / CTX_DIR
    ctx_dir.mkdir()
    (ctx_dir / METADATA_FILE).write_text('{"schema_version": 1}', encoding="utf-8")
    _mock_refresh(repo)

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        run_hook(repo, "post-commit")

    log_path = ctx_dir / HOOK_LOG_FILE
    assert log_path.exists()
    log_data = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(log_data["runs"]) == 1
    entry = log_data["runs"][0]
    assert entry["trigger"] == "post-commit"
    assert entry["success"] is True
    assert "duration_ms" in entry
    assert "timestamp" in entry


# ── Test 17: .ctx/.gitignore contains * ──────────────────────────────

def test_ctx_gitignore_content(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    content = (repo / CTX_DIR / ".gitignore").read_text(encoding="utf-8")
    assert content.strip() == "*"


# ── Test 18: root .gitignore gets .ctx/ added (no dupes) ────────────

def test_root_gitignore_no_duplicates(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    # Pre-existing .gitignore with .ctx/
    (repo / ".gitignore").write_text("node_modules/\n.ctx/\n", encoding="utf-8")

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    content = (repo / ".gitignore").read_text(encoding="utf-8")
    assert content.count(".ctx/") == 1


# ── Test 19: PID debounce skips when another hook is running ─────────

def test_pid_debounce_skips_when_running(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    pid_path = repo / PID_FILE

    # Write our own PID to simulate a running hook
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    # Should not acquire — our own process is alive
    assert not _acquire_pid(repo)

    # Clean up
    pid_path.unlink()


# ── Test 20: Full init → commit → verify → uninit roundtrip ─────────

def test_full_roundtrip(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        # Init
        init_result = init_project(repo)
        assert (repo / CTX_DIR).is_dir()
        assert len(init_result["hooks_installed"]) == 3

        # Verify hook files exist
        for hook_name in HOOK_NAMES:
            assert (repo / ".git" / "hooks" / hook_name).exists()

        # Verify .gitignore updated
        assert ".ctx/" in (repo / ".gitignore").read_text(encoding="utf-8")

        # Uninit
        uninit_result = uninit_project(repo)
        assert not (repo / CTX_DIR).exists()
        assert len(uninit_result["hooks_removed"]) == 3

        # Verify hooks removed
        for hook_name in HOOK_NAMES:
            hook_path = repo / ".git" / "hooks" / hook_name
            if hook_path.exists():
                assert CTX_HOOK_START not in hook_path.read_text(encoding="utf-8")

        # Verify .gitignore cleaned
        gitignore = repo / ".gitignore"
        if gitignore.exists():
            assert ".ctx/" not in gitignore.read_text(encoding="utf-8")


# ── Test 21: Hook failure logs to hook_log.json with success=false ───

def test_hook_failure_logs_error(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    ctx_dir = repo / CTX_DIR
    ctx_dir.mkdir()
    (ctx_dir / METADATA_FILE).write_text('{"schema_version": 1}', encoding="utf-8")

    with patch("ctx.api.refresh", side_effect=RuntimeError("LLM provider down")):
        run_hook(repo, "post-commit")

    log_path = ctx_dir / HOOK_LOG_FILE
    assert log_path.exists()
    log_data = json.loads(log_path.read_text(encoding="utf-8"))
    entry = log_data["runs"][0]
    assert entry["success"] is False
    assert "LLM provider down" in entry["error"]
    assert entry["trigger"] == "post-commit"


# ── Test 22: init --force with chained hooks preserves non-ctx ───────

def test_init_force_preserves_chained_hooks(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    # Pre-existing hook
    existing = hooks_dir / "post-commit"
    existing.write_text("#!/bin/sh\necho 'original'\n", encoding="utf-8")

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo)

    # Verify chained
    content = existing.read_text(encoding="utf-8")
    assert "original" in content
    assert CTX_HOOK_START in content

    with patch("ctx.api.refresh", side_effect=lambda root, **kw: _mock_refresh(root, **kw)):
        init_project(repo, force=True)

    # After reinit, original content should still be there
    updated = existing.read_text(encoding="utf-8")
    assert "original" in updated
    assert CTX_HOOK_START in updated
    assert updated.count(CTX_HOOK_START) == 1


# ── Test 23: Stale PID file (dead process) allows hook to proceed ────

def test_stale_pid_allows_hook(tmp_path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    pid_path = repo / PID_FILE

    # Write a PID that definitely doesn't exist
    pid_path.write_text("99999999", encoding="utf-8")

    with patch("ctx.init._pid_alive", return_value=False):
        acquired = _acquire_pid(repo)

    assert acquired

    # Clean up
    if pid_path.exists():
        pid_path.unlink()
