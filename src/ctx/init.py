"""ctx init — deterministic zero-LLM .ctx/ repository bootstrap & teardown.

Bootstraps deterministic .ctx/ structural & architectural maps in a git repo with
zero LLM calls and zero background git hooks:
  - Extracts AST/parser skeleton (ctx.skeleton.extract_skeleton)
  - Writes .ctx/{CONTEXT-0.md, CONTEXT-1.md, CONTEXT.md, metadata.json, .gitignore}
  - Adds .ctx/ to root .gitignore
  - Strips any legacy ctx git hook blocks on --force reinit or uninit
"""

from __future__ import annotations

import getpass
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ctx import __version__
from ctx.lock import (
    CtxLock,
    LockHeldError,
    LockSupersededError,
    assert_lock_ownership_for_path,
    fenced_mkdir,
    fenced_replace,
    fenced_unlink,
    lock_publication_fence_for_path,
    save_json_atomic,
    write_text_atomic,
)

HOOK_NAMES = ("post-commit", "post-checkout", "post-merge")
CTX_HOOK_START = "# >>> ctx-hook-start"
CTX_HOOK_END = "# <<< ctx-hook-end"
CTX_DIR = ".ctx"
METADATA_FILE = "metadata.json"
PID_FILE = ".ctx/hook.pid"
LEGACY_PID_FILE = ".ctx-hook.pid"

EXPORT_TIERS = [
    ("CONTEXT.md", None),
    ("CONTEXT-1.md", 1),
    ("CONTEXT-0.md", 0),
]


class InitError(Exception):
    """Raised when init/uninit encounters a user-facing error."""


def init_project(
    root: Path,
    *,
    force: bool = False,
    tier2: bool = True,
) -> dict:
    """Bootstrap deterministic .ctx/ structural maps in a git repository."""
    _ = tier2  # Preserved for caller compatibility; deterministic .ctx/ is the sole mode.
    root = root.resolve()

    git_dir = root / ".git"
    if not git_dir.exists():
        raise InitError(f"Not a git repository: {root}")

    ctx_dir = root / CTX_DIR
    if ctx_dir.is_dir() and not force:
        raise InitError(
            f"Already initialized: {ctx_dir} exists. Use --force to reinitialize."
        )

    from ctx.skeleton import (
        extract_skeleton,
        render_context_0,
        render_context_1,
        render_context_full,
    )

    metadata = _build_metadata(root)
    gitignore_path = root / ".gitignore"

    with CtxLock(root, command="init"):
        if ctx_dir.is_dir() and not force:
            raise InitError(
                f"Already initialized: {ctx_dir} exists. Use --force to reinitialize."
            )
        prior_gitignore = gitignore_path.read_bytes() if gitignore_path.exists() else None
        prior_ctx_snapshot = _snapshot_dir(ctx_dir)
        try:
            _add_to_gitignore(root, CTX_DIR + "/")
            if not _other_worktrees_share_hooks(root):
                _remove_legacy_hooks(root)
            skeleton = extract_skeleton(root)
            fenced_mkdir(ctx_dir, parents=True, exist_ok=True)
            write_text_atomic(ctx_dir / ".gitignore", "*\n")
            rendered_c0 = render_context_0(skeleton)
            rendered_c1 = render_context_1(skeleton)
            rendered_full = render_context_full(skeleton)
            write_text_atomic(ctx_dir / "CONTEXT-0.md", rendered_c0)
            write_text_atomic(ctx_dir / "CONTEXT-1.md", rendered_c1)
            write_text_atomic(ctx_dir / "CONTEXT.md", rendered_full)
            metadata["mode"] = "tier2"
            metadata["structural_hash"] = skeleton.structural_hash
            metadata["boundary_doc_hash"] = skeleton.boundary_doc_hash
            save_json_atomic(ctx_dir / METADATA_FILE, metadata)
            manifests_refreshed = len(skeleton.subsystems)
        except LockSupersededError:
            raise
        except Exception:
            _restore_dir_snapshot(ctx_dir, prior_ctx_snapshot)
            _restore_gitignore(gitignore_path, prior_gitignore)
            raise

    return {
        "root": str(root),
        "ctx_dir": str(ctx_dir),
        "hooks_installed": [],
        "manifests_refreshed": manifests_refreshed,
        "exports": [name for name, _ in EXPORT_TIERS],
        "metadata": metadata,
        "force": force,
        "mode": "tier2",
    }


def uninit_project(root: Path) -> dict:
    """Remove .ctx/ infrastructure and any legacy ctx git hook blocks from a repository."""
    root = root.resolve()
    ctx_dir = root / CTX_DIR

    if not ctx_dir.is_dir():
        raise InitError(f"Not initialized: {ctx_dir} does not exist.")

    try:
        with CtxLock(root, command="uninit"):
            if not ctx_dir.is_dir():
                raise InitError(f"Not initialized: {ctx_dir} does not exist.")

            assert_lock_ownership_for_path(root)
            if _other_worktrees_share_hooks(root):
                hooks_removed: list[str] = []
            else:
                hooks_removed = _remove_legacy_hooks(root)

            _rmtree(ctx_dir)
            _remove_from_gitignore(root, CTX_DIR + "/")

            for rel_pid in (PID_FILE, LEGACY_PID_FILE):
                fenced_unlink(root / rel_pid, missing_ok=True, fence_path=root)
    except LockHeldError as exc:
        raise InitError(
            f"Cannot uninitialize while another ctx write operation holds the lock: {exc}"
        ) from exc

    return {
        "root": str(root),
        "hooks_removed": hooks_removed,
        "ctx_dir_removed": True,
        "gitignore_cleaned": True,
    }


def _build_metadata(root: Path) -> dict:
    """Build deterministic metadata.json content."""
    repo_id = hashlib.sha256(str(root).encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "initialized_at": now,
        "initialized_by": getpass.getuser(),
        "ctx_version": __version__,
        "repo_id": f"sha256:{repo_id}",
        "last_refresh": now,
        "python_executable": sys.executable,
        "hooks_installed": [],
    }


def _write_bytes_atomic(
    path: Path,
    data: bytes,
    *,
    mode: int | None = None,
    fence_path: Path | None = None,
) -> None:
    """Write raw bytes atomically via a same-directory temporary file and kernel-fenced os.replace."""
    check_path = fence_path or path
    assert_lock_ownership_for_path(check_path)
    fenced_mkdir(path.parent, parents=True, exist_ok=True, fence_path=check_path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if mode is not None and os.name != "nt":
            os.chmod(tmp, mode)
        fenced_replace(tmp, path, fence_path=check_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _restore_gitignore(gitignore_path: Path, prior_gitignore: bytes | None) -> None:
    """Restore root .gitignore byte-for-byte inside an active CtxLock transaction."""
    if prior_gitignore is None:
        fenced_unlink(gitignore_path, missing_ok=True)
    else:
        _write_bytes_atomic(gitignore_path, prior_gitignore)


def _snapshot_dir(dir_path: Path) -> dict[Path, bytes] | None:
    """Capture an in-memory byte snapshot of all files under *dir_path*, or None if absent."""
    if not dir_path.is_dir():
        return None
    snapshot: dict[Path, bytes] = {}
    for file_path in dir_path.rglob("*"):
        if file_path.is_file():
            snapshot[file_path.relative_to(dir_path)] = file_path.read_bytes()
    return snapshot


def _restore_dir_snapshot(dir_path: Path, snapshot: dict[Path, bytes] | None) -> None:
    """Restore *dir_path* byte-for-byte to *snapshot* (removing *dir_path* when snapshot is None)."""
    assert_lock_ownership_for_path(dir_path)
    if snapshot is None:
        if dir_path.exists():
            _rmtree(dir_path)
        return

    fenced_mkdir(dir_path, parents=True, exist_ok=True)
    for existing in list(dir_path.rglob("*")):
        if existing.is_file() and existing.relative_to(dir_path) not in snapshot:
            fenced_unlink(existing, missing_ok=True)
    for rel_path, raw_bytes in snapshot.items():
        _write_bytes_atomic(dir_path / rel_path, raw_bytes)


def _resolve_hooks_dir(root: Path) -> Path:
    """Resolve the active git hooks directory, supporting worktrees and core.hooksPath."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidate = Path(result.stdout.strip())
            return candidate if candidate.is_absolute() else (root / candidate).resolve()
    except (subprocess.SubprocessError, OSError):
        pass

    git_entry = root / ".git"
    if git_entry.is_file():
        try:
            first_line = git_entry.read_text(encoding="utf-8").splitlines()[0].strip()
            if first_line.lower().startswith("gitdir:"):
                raw_gitdir = Path(first_line.split(":", 1)[1].strip())
                resolved_gitdir = raw_gitdir if raw_gitdir.is_absolute() else (root / raw_gitdir).resolve()
                return resolved_gitdir / "hooks"
        except (OSError, IndexError):
            pass

    return git_entry / "hooks"


def _other_worktrees_share_hooks(root: Path) -> bool:
    """Return True if another initialized git worktree shares the same hooks directory."""
    try:
        my_hooks = _resolve_hooks_dir(root).resolve()
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return False
        resolved_root = root.resolve()
        for line in proc.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            wt_path = Path(line[len("worktree ") :].strip()).resolve()
            if wt_path == resolved_root:
                continue
            if (wt_path / CTX_DIR / METADATA_FILE).is_file():
                if _resolve_hooks_dir(wt_path).resolve() == my_hooks:
                    return True
    except (subprocess.SubprocessError, OSError):
        return False
    return False


def _remove_legacy_hooks(root: Path) -> list[str]:
    """Remove legacy ctx hook blocks from git hooks if present."""
    assert_lock_ownership_for_path(root)
    hooks_dir = _resolve_hooks_dir(root)
    removed: list[str] = []

    for hook_name in HOOK_NAMES:
        assert_lock_ownership_for_path(root)
        hook_path = hooks_dir / hook_name
        if not hook_path.exists():
            continue

        prior_mode = hook_path.stat().st_mode
        content = hook_path.read_text(encoding="utf-8")
        if CTX_HOOK_START not in content or CTX_HOOK_END not in content:
            continue

        start = content.index(CTX_HOOK_START)
        end = content.index(CTX_HOOK_END) + len(CTX_HOOK_END)
        if end < len(content) and content[end] == "\n":
            end += 1

        remaining = (content[:start] + content[end:]).strip()
        if not remaining or remaining == "#!/bin/sh":
            fenced_unlink(hook_path, missing_ok=True, fence_path=root)
        else:
            _write_bytes_atomic(
                hook_path,
                (remaining + "\n").encode("utf-8"),
                mode=(prior_mode | 0o111),
                fence_path=root,
            )
        removed.append(hook_name)

    return removed


def _add_to_gitignore(root: Path, entry: str) -> None:
    """Add an entry to root .gitignore if not already present."""
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = content.splitlines()
        if entry in lines or entry.rstrip("/") in lines:
            return
        if not content.endswith("\n"):
            content += "\n"
        content += entry + "\n"
    else:
        content = entry + "\n"
    write_text_atomic(gitignore, content)


def _remove_from_gitignore(root: Path, entry: str) -> None:
    """Remove an entry from root .gitignore."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return
    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()
    filtered = [line for line in lines if line != entry and line != entry.rstrip("/")]
    if len(filtered) == len(lines):
        return
    write_text_atomic(gitignore, "\n".join(filtered) + "\n" if filtered else "")


def _rmtree(path: Path) -> None:
    """Remove a directory tree while holding the kernel publication fence."""

    def _on_error(func, fpath, _exc_info):
        os.chmod(fpath, 0o777)
        func(fpath)

    with lock_publication_fence_for_path(path):
        if path.exists():
            shutil.rmtree(path, onerror=_on_error)
