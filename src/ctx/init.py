"""ctx init — make directory mapping inevitable.

Bootstraps self-maintaining .ctx/ infrastructure in a git repo:
  - Generates initial manifests (api.refresh)
  - Creates .ctx/ export layer with depth-tiered exports
  - Installs git hooks (post-commit, post-checkout, post-merge)
  - Writes metadata.json, hook_log.json, .ctx/.gitignore
  - Updates root .gitignore

Architecture:
  init_project()   → one-time setup: .ctx/ + hooks + metadata
  uninit_project()  → reverse: remove hooks + .ctx/ + .gitignore entry
  run_hook()        → hook entrypoint: refresh + export + telemetry (background)

Hook lifecycle:
  [git commit/checkout/merge]
        │
        ▼
  [hook script: #!/bin/sh]
        │
        ▼
  [python -m ctx _hook --trigger <type>]  (background, detached)
        │
        ├─ PID debounce check (skip if another hook is running)
        ├─ ctx refresh . (quiet)
        ├─ export at depths 0, 1, full → .ctx/
        ├─ update metadata.json last_refresh
        └─ append to hook_log.json
"""

from __future__ import annotations

import getpass
import hashlib
import logging
import os
import subprocess
import sys
import threading
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from ctx import __version__
from ctx.lock import (
    CtxLock,
    LockHeldError,
    LockSupersededError,
    assert_lock_ownership_for_path,
    release_os_lock,
    try_acquire_os_lock,
)
from ctx.stats_board import load_json_safe, save_json_atomic, write_text_atomic

logger = logging.getLogger(__name__)

HOOK_NAMES = ("post-commit", "post-checkout", "post-merge")
CTX_HOOK_START = "# >>> ctx-hook-start"
CTX_HOOK_END = "# <<< ctx-hook-end"
CTX_DIR = ".ctx"
METADATA_FILE = "metadata.json"
HOOK_LOG_FILE = "hook_log.json"
PID_FILE = ".ctx/hook.pid"
LEGACY_PID_FILE = ".ctx-hook.pid"
MAX_HOOK_LOG_ENTRIES = 200

# ── Depth-tiered export config ──────────────────────────────────────
EXPORT_TIERS = [
    ("CONTEXT.md", None),       # full tree
    ("CONTEXT-1.md", 1),        # depth 1
    ("CONTEXT-0.md", 0),        # root only
]


# ── Public API ──────────────────────────────────────────────────────

def init_project(
    root: Path,
    *,
    force: bool = False,
    tier2: bool = False,
) -> dict:
    """Bootstrap .ctx/ infrastructure in a git repo.

    Returns a dict describing what was created for CLI output.
    """
    root = root.resolve()

    # 1. Validate: is this a git repo (including git worktrees/submodules where .git is a file)?
    git_dir = root / ".git"
    if not git_dir.exists():
        raise InitError(f"Not a git repository: {root}")

    # 2. Fast pre-check (revalidated under CtxLock before any snapshot or mutation)
    ctx_dir = root / CTX_DIR
    if ctx_dir.is_dir() and not force:
        raise InitError(
            f"Already initialized: {ctx_dir} exists. Use --force to reinitialize."
        )

    metadata = _build_metadata(root)
    gitignore_path = root / ".gitignore"
    hooks_installed: list[str] = []

    if tier2:
        from ctx.skeleton import (
            extract_skeleton,
            render_context_0,
            render_context_1,
            render_context_full,
        )

        with CtxLock(root, command="init"):
            if ctx_dir.is_dir() and not force:
                raise InitError(
                    f"Already initialized: {ctx_dir} exists. Use --force to reinitialize."
                )
            prior_gitignore = gitignore_path.read_bytes() if gitignore_path.exists() else None
            prior_ctx_snapshot = _snapshot_dir(ctx_dir)
            hooks_dir, missing_hook_dirs, prior_hooks = _snapshot_hooks(root)
            try:
                _add_to_gitignore(root, CTX_DIR + "/")
                hooks_installed = _install_hooks(root)
                skeleton = extract_skeleton(root)
                rendered_c0 = render_context_0(skeleton)
                rendered_c1 = render_context_1(skeleton)
                rendered_full = render_context_full(skeleton)
                assert_lock_ownership_for_path(ctx_dir)
                ctx_dir.mkdir(exist_ok=True)
                write_text_atomic(ctx_dir / ".gitignore", "*\n")
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
                _restore_hooks(root, hooks_dir, missing_hook_dirs, prior_hooks)
                _restore_dir_snapshot(ctx_dir, prior_ctx_snapshot)
                _restore_gitignore(gitignore_path, prior_gitignore)
                raise
    else:
        finalized = False
        tx_mutated = False
        prior_gitignore: bytes | None = None
        prior_ctx_snapshot: dict[Path, bytes] | None = None
        hooks_dir_ref: Path | None = None
        missing_hook_dirs: list[Path] = []
        prior_hooks: dict[str, tuple[bytes, int] | None] = {}

        def _begin_standard_ctx_locked() -> None:
            nonlocal tx_mutated, prior_gitignore, prior_ctx_snapshot
            nonlocal hooks_dir_ref, missing_hook_dirs, prior_hooks, hooks_installed
            if ctx_dir.is_dir() and not force:
                raise InitError(
                    f"Already initialized: {ctx_dir} exists. Use --force to reinitialize."
                )
            prior_gitignore = gitignore_path.read_bytes() if gitignore_path.exists() else None
            prior_ctx_snapshot = _snapshot_dir(ctx_dir)
            hooks_dir_ref, missing_hook_dirs, prior_hooks = _snapshot_hooks(root)
            tx_mutated = True
            _add_to_gitignore(root, CTX_DIR + "/")
            hooks_installed = _install_hooks(root)

        def _rollback_standard_ctx_locked() -> None:
            if not tx_mutated:
                return
            assert hooks_dir_ref is not None
            _restore_hooks(root, hooks_dir_ref, missing_hook_dirs, prior_hooks)
            _restore_dir_snapshot(ctx_dir, prior_ctx_snapshot)
            _restore_gitignore(gitignore_path, prior_gitignore)

        def _finalize_standard_ctx_locked() -> None:
            nonlocal finalized
            rendered_exports = _render_ctx_exports(root)
            assert_lock_ownership_for_path(ctx_dir)
            ctx_dir.mkdir(exist_ok=True)
            write_text_atomic(ctx_dir / ".gitignore", "*\n")
            _add_to_gitignore(root, CTX_DIR + "/")
            for filename, content in rendered_exports:
                write_text_atomic(ctx_dir / filename, content)
            metadata["mode"] = "standard"
            metadata["last_refresh"] = datetime.now(timezone.utc).isoformat()
            save_json_atomic(ctx_dir / METADATA_FILE, metadata)
            finalized = True

        from ctx.api import refresh

        refresh_result = refresh(
            root,
            force=force,
            _force_tier1=True,
            _on_locked_begin=_begin_standard_ctx_locked,
            _on_locked_success=_finalize_standard_ctx_locked,
            _on_locked_rollback=_rollback_standard_ctx_locked,
        )

        # Fallback for unit tests that mock ctx.api.refresh without invoking locked callbacks
        if not finalized:
            if refresh_result.errors:
                raise InitError(
                    f"Initial manifest refresh failed: {refresh_result.errors[0]}"
                )
            with CtxLock(root, command="init"):
                _begin_standard_ctx_locked()
                try:
                    _finalize_standard_ctx_locked()
                except LockSupersededError:
                    raise
                except Exception:
                    _rollback_standard_ctx_locked()
                    raise
        manifests_refreshed = refresh_result.dirs_processed

    result = {
        "root": str(root),
        "ctx_dir": str(ctx_dir),
        "hooks_installed": hooks_installed,
        "manifests_refreshed": manifests_refreshed,
        "exports": [name for name, _ in EXPORT_TIERS],
        "metadata": metadata,
        "force": force,
    }
    if tier2:
        result["mode"] = "tier2"
    return result


def uninit_project(root: Path, *, wait_timeout: float = 2.0) -> dict:
    """Remove .ctx/ infrastructure and hooks from a git repo.

    Coordinates with active background hooks via the persistent .ctx-cache/.hook.guard
    kernel lock and with active writers via CtxLock so teardown never unlinks an open
    guard inode or races with in-flight exports.
    """
    root = root.resolve()
    ctx_dir = root / CTX_DIR

    if not ctx_dir.is_dir():
        raise InitError(f"Not initialized: {ctx_dir} does not exist.")

    # Release any hook descriptor held inside the current Python process first.
    _release_pid(root)

    hook_fd = _acquire_hook_guard_for_teardown(root, timeout_seconds=wait_timeout)
    if hook_fd is None:
        raise InitError(
            "Cannot uninitialize while a background ctx hook is running; retry shortly."
        )

    try:
        try:
            with CtxLock(root, command="uninit"):
                if not ctx_dir.is_dir():
                    raise InitError(f"Not initialized: {ctx_dir} does not exist.")

                assert_lock_ownership_for_path(root)
                # 1. Remove ctx blocks from hooks unless another initialized worktree shares this hooks dir
                if _other_worktrees_share_hooks(root):
                    hooks_removed: list[str] = []
                else:
                    hooks_removed = _remove_hooks(root)

                # 2. Remove .ctx/ directory (the persistent hook guard lives in .ctx-cache/.hook.guard)
                assert_lock_ownership_for_path(ctx_dir)
                _rmtree(ctx_dir)

                # 3. Remove .ctx/ from root .gitignore
                assert_lock_ownership_for_path(root)
                _remove_from_gitignore(root, CTX_DIR + "/")

                # 4. Remove PID files if present (current + legacy)
                for rel_pid in (PID_FILE, LEGACY_PID_FILE):
                    assert_lock_ownership_for_path(root)
                    pid_file = root / rel_pid
                    if pid_file.exists():
                        pid_file.unlink(missing_ok=True)
        except LockHeldError as exc:
            raise InitError(
                f"Cannot uninitialize while another ctx write operation holds the lock: {exc}"
            ) from exc
    finally:
        release_os_lock(hook_fd)

    return {
        "root": str(root),
        "hooks_removed": hooks_removed,
        "ctx_dir_removed": True,
        "gitignore_cleaned": True,
    }


def run_hook(root: Path, trigger: str) -> None:
    """Hook entrypoint: refresh + export + telemetry.

    Called by git hooks via: python -m ctx _hook --trigger <type>
    Runs in background. Never raises — logs failures to hook_log.json.
    """
    root = root.resolve()
    ctx_dir = root / CTX_DIR
    meta_path = ctx_dir / METADATA_FILE
    start = _time.monotonic()
    success = True
    error_msg = ""
    superseded = False

    if not meta_path.is_file():
        return

    # PID debounce: skip if another hook (or uninit teardown) holds the persistent kernel guard
    if not _acquire_pid(root):
        logger.debug("ctx hook: another hook is running, skipping")
        return

    try:
        if not meta_path.is_file():
            return

        meta = load_json_safe(meta_path, {})

        if isinstance(meta, dict) and meta.get("mode") == "tier2":
            from ctx.api import _refresh_tier2

            _refresh_tier2(root, touch_last_refresh=True, _from_hook=True)
        else:
            # Quiet refresh
            from ctx.api import refresh
            refresh(root)

            # Re-export at all depth tiers and update metadata under CtxLock
            with CtxLock(root, command="hook"):
                latest_meta = load_json_safe(meta_path, {}) if meta_path.is_file() else None
                if meta_path.is_file() and isinstance(latest_meta, dict) and latest_meta.get("mode") != "tier2":
                    _populate_ctx_dir(root, ctx_dir)
                    latest_meta["last_refresh"] = datetime.now(timezone.utc).isoformat()
                    save_json_atomic(meta_path, latest_meta)

    except LockSupersededError as exc:
        success = False
        superseded = True
        error_msg = str(exc)
        logger.warning("ctx hook superseded after stale lock timeout: %s", exc)
    except Exception as exc:
        success = False
        error_msg = str(exc)
        logger.warning("ctx hook failed: %s", exc)
    finally:
        _release_pid(root)

        # Append telemetry only while project remains initialized and this hook was not superseded
        if not superseded and meta_path.is_file():
            elapsed_ms = round((_time.monotonic() - start) * 1000)
            _append_hook_log(ctx_dir, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trigger": trigger,
                "duration_ms": elapsed_ms,
                "success": success,
                "error": error_msg if not success else None,
            })


# ── Error class ─────────────────────────────────────────────────────

class InitError(Exception):
    """Raised when init/uninit encounters a user-facing error."""


# ── Internal helpers ────────────────────────────────────────────────

def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write raw bytes atomically via a same-directory temporary file and os.replace."""
    import tempfile

    assert_lock_ownership_for_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        assert_lock_ownership_for_path(path)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _restore_gitignore(gitignore_path: Path, prior_gitignore: bytes | None) -> None:
    """Restore root .gitignore byte-for-byte inside an active CtxLock transaction."""
    assert_lock_ownership_for_path(gitignore_path)
    if prior_gitignore is None:
        gitignore_path.unlink(missing_ok=True)
    else:
        _write_bytes_atomic(gitignore_path, prior_gitignore)


def _snapshot_hooks(root: Path) -> tuple[Path, list[Path], dict[str, tuple[bytes, int] | None]]:
    """Capture prior state of git hook files and any not-yet-created hook directories."""
    hooks_dir = _resolve_hooks_dir(root)
    missing_dirs: list[Path] = []
    probe = hooks_dir
    while not probe.exists():
        missing_dirs.append(probe)
        if probe.parent == probe:
            break
        probe = probe.parent
    prior_files: dict[str, tuple[bytes, int] | None] = {}
    for hook_name in HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        if hook_path.is_file():
            prior_files[hook_name] = (hook_path.read_bytes(), hook_path.stat().st_mode)
        else:
            prior_files[hook_name] = None
    return hooks_dir, missing_dirs, prior_files


def _restore_hooks(
    root: Path,
    hooks_dir: Path,
    missing_dirs: list[Path],
    prior_files: dict[str, tuple[bytes, int] | None],
) -> None:
    """Restore git hook files and remove any hook directories created during a failed init."""
    assert_lock_ownership_for_path(root)
    for hook_name, prior in prior_files.items():
        hook_path = hooks_dir / hook_name
        if prior is None:
            hook_path.unlink(missing_ok=True)
        else:
            raw_bytes, mode = prior
            _write_bytes_atomic(hook_path, raw_bytes)
            if os.name != "nt":
                try:
                    hook_path.chmod(mode)
                except OSError:
                    pass
    for created_dir in missing_dirs:
        try:
            if created_dir.is_dir() and not any(created_dir.iterdir()):
                created_dir.rmdir()
        except OSError:
            break


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

    dir_path.mkdir(parents=True, exist_ok=True)
    for existing in list(dir_path.rglob("*")):
        if existing.is_file() and existing.relative_to(dir_path) not in snapshot:
            assert_lock_ownership_for_path(existing)
            existing.unlink(missing_ok=True)
    for rel_path, raw_bytes in snapshot.items():
        _write_bytes_atomic(dir_path / rel_path, raw_bytes)


def _render_ctx_exports(root: Path) -> list[tuple[str, str]]:
    """Render all depth-tiered Tier 1 exports in memory before mutating .ctx/ on disk."""
    from ctx.api import export_context

    rendered: list[tuple[str, str]] = []
    for filename, depth in EXPORT_TIERS:
        result = export_context(root, depth=depth, _force_tier1=True)
        rendered.append((filename, result.content))
    return rendered


def _populate_ctx_dir(root: Path, ctx_dir: Path) -> None:
    """Stage and write depth-tiered Tier 1 exports atomically into .ctx/ with rollback on failure."""
    prior_snapshot = _snapshot_dir(ctx_dir)
    rendered = _render_ctx_exports(root)
    try:
        assert_lock_ownership_for_path(ctx_dir)
        ctx_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in rendered:
            write_text_atomic(ctx_dir / filename, content)
    except LockSupersededError:
        raise
    except Exception:
        _restore_dir_snapshot(ctx_dir, prior_snapshot)
        raise


def _build_metadata(root: Path) -> dict:
    """Build metadata.json content."""
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
        "hooks_installed": list(HOOK_NAMES),
    }


def _generate_hook_script(root: Path) -> str:
    """Generate the shell script block that ctx hooks run.

    Resolves the active checkout/worktree root dynamically via `git rev-parse --show-toplevel`
    so linked git worktrees sharing a common hooks directory refresh their own `.ctx/`
    and skip uninitialized checkouts cleanly.
    """
    python_path = sys.executable.replace("\\", "/")

    return f"""\
{CTX_HOOK_START}
# Installed by ctx init ({__version__}) — do not edit this block manually.
# To remove: run ctx uninit, or delete lines between ctx-hook-start/end markers.
_CTX_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -d "$_CTX_ROOT/.ctx" ]; then
_CTX_PYTHON="{python_path}"
if [ ! -x "$_CTX_PYTHON" ]; then
  _CTX_PYTHON="python3"
fi
"$_CTX_PYTHON" -m ctx _hook --trigger "$0" --root "$_CTX_ROOT" &
fi
{CTX_HOOK_END}"""


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


def _install_hooks(root: Path) -> list[str]:
    """Install ctx hook blocks into git hook files.

    Returns list of hook names that were installed.
    """
    assert_lock_ownership_for_path(root)
    hooks_dir = _resolve_hooks_dir(root)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    hook_block = _generate_hook_script(root)

    for hook_name in HOOK_NAMES:
        assert_lock_ownership_for_path(root)
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            prior_mode = hook_path.stat().st_mode
            existing = hook_path.read_text(encoding="utf-8")
            if CTX_HOOK_START in existing:
                # Update existing ctx block in place
                _update_ctx_block(hook_path, existing, hook_block, mode=prior_mode)
            else:
                # Chain: append ctx block to existing hook
                _chain_hook(hook_path, existing, hook_block, mode=prior_mode)
        else:
            # Create new hook file
            content = "#!/bin/sh\n" + hook_block + "\n"
            write_text_atomic(hook_path, content)
            _make_executable(hook_path)
        installed.append(hook_name)

    return installed


def _update_ctx_block(hook_path: Path, existing: str, new_block: str, *, mode: int | None = None) -> None:
    """Replace the ctx block in an existing hook file."""
    start = existing.index(CTX_HOOK_START)
    end = existing.index(CTX_HOOK_END) + len(CTX_HOOK_END)
    # Consume trailing newline if present
    if end < len(existing) and existing[end] == "\n":
        end += 1
    updated = existing[:start] + new_block + "\n" + existing[end:]
    write_text_atomic(hook_path, updated)
    if os.name != "nt":
        hook_path.chmod((mode if mode is not None else hook_path.stat().st_mode) | 0o111)


def _chain_hook(hook_path: Path, existing: str, hook_block: str, *, mode: int | None = None) -> None:
    """Append ctx block to an existing non-ctx hook."""
    if not existing.endswith("\n"):
        existing += "\n"
    write_text_atomic(hook_path, existing + hook_block + "\n")
    if os.name != "nt":
        hook_path.chmod((mode if mode is not None else hook_path.stat().st_mode) | 0o111)


def _remove_hooks(root: Path) -> list[str]:
    """Remove ctx blocks from git hooks. Returns names of modified hooks."""
    assert_lock_ownership_for_path(root)
    hooks_dir = _resolve_hooks_dir(root)
    removed = []

    for hook_name in HOOK_NAMES:
        assert_lock_ownership_for_path(root)
        hook_path = hooks_dir / hook_name
        if not hook_path.exists():
            continue

        prior_mode = hook_path.stat().st_mode
        content = hook_path.read_text(encoding="utf-8")
        if CTX_HOOK_START not in content:
            continue

        # Remove ctx block
        start = content.index(CTX_HOOK_START)
        end = content.index(CTX_HOOK_END) + len(CTX_HOOK_END)
        if end < len(content) and content[end] == "\n":
            end += 1

        remaining = content[:start] + content[end:]
        remaining = remaining.strip()

        if not remaining or remaining == "#!/bin/sh":
            # Hook was ctx-only, delete the file
            hook_path.unlink()
        else:
            # Preserve non-ctx content
            write_text_atomic(hook_path, remaining + "\n")
            if os.name != "nt":
                hook_path.chmod(prior_mode | 0o111)

        removed.append(hook_name)

    return removed


def _make_executable(path: Path) -> None:
    """Make a file executable (no-op on Windows, git handles it)."""
    if os.name != "nt":
        path.chmod(path.stat().st_mode | 0o111)


def _add_to_gitignore(root: Path, entry: str) -> None:
    """Add an entry to root .gitignore if not already present."""
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = content.splitlines()
        if entry in lines or entry.rstrip("/") in lines:
            return  # Already present
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
        return  # Nothing to remove
    write_text_atomic(gitignore, "\n".join(filtered) + "\n" if filtered else "")


def _rmtree(path: Path) -> None:
    """Remove a directory tree. Handles read-only files on Windows."""
    import shutil

    assert_lock_ownership_for_path(path)

    def _on_error(func, fpath, exc_info):
        os.chmod(fpath, 0o777)
        func(fpath)

    shutil.rmtree(path, onerror=_on_error)


# ── PID debounce ────────────────────────────────────────────────────

HOOK_GUARD_FILE = ".ctx-cache/.hook.guard"
_HELD_HOOK_FDS: dict[Path, tuple[int, bool]] = {}
_HELD_HOOK_FDS_LOCK = threading.Lock()


def _acquire_hook_guard_for_teardown(root: Path, *, timeout_seconds: float = 2.0) -> int | None:
    """Acquire the persistent hook kernel guard (.ctx-cache/.hook.guard) before teardown."""
    guard_path = root.resolve() / HOOK_GUARD_FILE
    deadline = _time.monotonic() + max(0.0, timeout_seconds)
    while True:
        os_fd = try_acquire_os_lock(guard_path)
        if os_fd is not None:
            return os_fd
        if _time.monotonic() >= deadline:
            return None
        _time.sleep(0.02)


def _acquire_pid(root: Path) -> bool:
    """Acquire exclusive hook execution ownership backed by an OS kernel lock on .ctx-cache/.hook.guard."""
    resolved_root = root.resolve()
    pid_path = resolved_root / PID_FILE
    guard_path = resolved_root / HOOK_GUARD_FILE

    os_fd = try_acquire_os_lock(guard_path)
    if os_fd is None:
        return False

    try:
        if pid_path.is_file():
            try:
                stored_pid = int(pid_path.read_text(encoding="utf-8").strip())
                if _pid_alive(stored_pid):
                    release_os_lock(os_fd)
                    return False
            except (ValueError, OSError):
                pass

        created_ctx_dir = not pid_path.parent.exists()
        write_text_atomic(pid_path, str(os.getpid()))
        with _HELD_HOOK_FDS_LOCK:
            prev_entry = _HELD_HOOK_FDS.pop(pid_path, None)
            _HELD_HOOK_FDS[pid_path] = (os_fd, created_ctx_dir)
        if prev_entry is not None:
            release_os_lock(prev_entry[0])
        return True
    except OSError:
        release_os_lock(os_fd)
        return False


def _release_pid(root: Path) -> None:
    """Release the hook PID file while holding the OS kernel guard lock, then unlock."""
    resolved_root = root.resolve()
    pid_path = resolved_root / PID_FILE
    with _HELD_HOOK_FDS_LOCK:
        entry = _HELD_HOOK_FDS.pop(pid_path, None)
    os_fd = entry[0] if entry is not None else None
    created_ctx_dir = entry[1] if entry is not None else False

    try:
        if os_fd is not None:
            pid_path.unlink(missing_ok=True)
        elif pid_path.exists():
            stored_pid = int(pid_path.read_text(encoding="utf-8").strip())
            if stored_pid == os.getpid():
                pid_path.unlink(missing_ok=True)
        if created_ctx_dir and pid_path.parent.is_dir() and not any(pid_path.parent.iterdir()):
            pid_path.parent.rmdir()
    except (ValueError, OSError):
        pass
    finally:
        if os_fd is not None:
            release_os_lock(os_fd)


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    if os.name == "nt":
        # Windows: use tasklist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except (subprocess.SubprocessError, OSError):
            return False
    else:
        # POSIX: signal 0 checks existence
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# ── Hook telemetry ──────────────────────────────────────────────────

def _append_hook_log(ctx_dir: Path, entry: dict) -> None:
    """Append an entry to hook_log.json with bounded retention."""
    log_path = ctx_dir / HOOK_LOG_FILE
    try:
        data = load_json_safe(log_path, {"runs": []})
        if "runs" not in data or not isinstance(data["runs"], list):
            data = {"runs": []}
        data["runs"].append(entry)
        if len(data["runs"]) > MAX_HOOK_LOG_ENTRIES:
            data["runs"] = data["runs"][-MAX_HOOK_LOG_ENTRIES:]
        save_json_atomic(log_path, data)
    except Exception as exc:
        # Never let telemetry failure crash the hook
        logger.debug("Failed to write hook log: %s", exc)
