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
import json
import logging
import os
import signal
import subprocess
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from ctx import __version__
from ctx.stats_board import load_json_safe, save_json_atomic

logger = logging.getLogger(__name__)

HOOK_NAMES = ("post-commit", "post-checkout", "post-merge")
CTX_HOOK_START = "# >>> ctx-hook-start"
CTX_HOOK_END = "# <<< ctx-hook-end"
CTX_DIR = ".ctx"
METADATA_FILE = "metadata.json"
HOOK_LOG_FILE = "hook_log.json"
PID_FILE = ".ctx-hook.pid"

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
) -> dict:
    """Bootstrap .ctx/ infrastructure in a git repo.

    Returns a dict describing what was created for CLI output.
    """
    root = root.resolve()

    # 1. Validate: is this a git repo?
    git_dir = root / ".git"
    if not git_dir.is_dir():
        raise InitError(f"Not a git repository: {root}")

    # 2. Already initialized?
    ctx_dir = root / CTX_DIR
    if ctx_dir.is_dir() and not force:
        raise InitError(
            f"Already initialized: {ctx_dir} exists. Use --force to reinitialize."
        )

    # 3. Generate initial manifests via api.refresh
    from ctx.api import refresh
    refresh_result = refresh(root, force=force)

    # 4. Create .ctx/ export layer
    ctx_dir.mkdir(exist_ok=True)
    _populate_ctx_dir(root, ctx_dir)

    # 5. Write metadata.json
    metadata = _build_metadata(root)
    save_json_atomic(ctx_dir / METADATA_FILE, metadata)

    # 6. Write .ctx/.gitignore (ignore everything in .ctx/)
    (ctx_dir / ".gitignore").write_text("*\n", encoding="utf-8")

    # 7. Update root .gitignore
    _add_to_gitignore(root, CTX_DIR + "/")

    # 8. Install git hooks
    hooks_installed = _install_hooks(root)

    return {
        "root": str(root),
        "ctx_dir": str(ctx_dir),
        "hooks_installed": hooks_installed,
        "manifests_refreshed": refresh_result.dirs_processed,
        "exports": [name for name, _ in EXPORT_TIERS],
        "metadata": metadata,
        "force": force,
    }


def uninit_project(root: Path) -> dict:
    """Remove .ctx/ infrastructure and hooks from a git repo.

    Returns a dict describing what was removed for CLI output.
    """
    root = root.resolve()
    ctx_dir = root / CTX_DIR

    if not ctx_dir.is_dir():
        raise InitError(f"Not initialized: {ctx_dir} does not exist.")

    # 1. Remove ctx blocks from hooks
    hooks_removed = _remove_hooks(root)

    # 2. Remove .ctx/ directory
    _rmtree(ctx_dir)

    # 3. Remove .ctx/ from root .gitignore
    _remove_from_gitignore(root, CTX_DIR + "/")

    # 4. Remove PID file if present
    pid_file = root / PID_FILE
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

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
    start = _time.monotonic()
    success = True
    error_msg = ""

    # PID debounce: skip if another hook is already running
    if not _acquire_pid(root):
        logger.debug("ctx hook: another hook is running, skipping")
        return

    try:
        # Quiet refresh
        from ctx.api import refresh
        refresh(root)

        # Re-export at all depth tiers
        _populate_ctx_dir(root, ctx_dir)

        # Update last_refresh in metadata
        meta_path = ctx_dir / METADATA_FILE
        if meta_path.exists():
            meta = load_json_safe(meta_path, {})
            meta["last_refresh"] = datetime.now(timezone.utc).isoformat()
            save_json_atomic(meta_path, meta)

    except Exception as exc:
        success = False
        error_msg = str(exc)
        logger.warning("ctx hook failed: %s", exc)
    finally:
        _release_pid(root)

        # Append telemetry
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

def _populate_ctx_dir(root: Path, ctx_dir: Path) -> None:
    """Write depth-tiered exports into .ctx/."""
    from ctx.api import export_context

    for filename, depth in EXPORT_TIERS:
        result = export_context(root, depth=depth)
        (ctx_dir / filename).write_text(result.content, encoding="utf-8")


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

    Uses the current Python interpreter path with python3 fallback.
    Runs in background (&) and detaches from the git process.
    """
    python_path = sys.executable.replace("\\", "/")
    root_str = str(root).replace("\\", "/")

    return f"""\
{CTX_HOOK_START}
# Installed by ctx init ({__version__}) — do not edit this block manually.
# To remove: run ctx uninit, or delete lines between ctx-hook-start/end markers.
_CTX_PYTHON="{python_path}"
if [ ! -x "$_CTX_PYTHON" ]; then
  _CTX_PYTHON="python3"
fi
"$_CTX_PYTHON" -m ctx _hook --trigger "$0" --root "{root_str}" &
{CTX_HOOK_END}"""


def _install_hooks(root: Path) -> list[str]:
    """Install ctx hook blocks into git hook files.

    Returns list of hook names that were installed.
    """
    hooks_dir = root / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    installed = []
    hook_block = _generate_hook_script(root)

    for hook_name in HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            existing = hook_path.read_text(encoding="utf-8")
            if CTX_HOOK_START in existing:
                # Update existing ctx block in place
                _update_ctx_block(hook_path, existing, hook_block)
            else:
                # Chain: append ctx block to existing hook
                _chain_hook(hook_path, existing, hook_block)
        else:
            # Create new hook file
            content = "#!/bin/sh\n" + hook_block + "\n"
            hook_path.write_text(content, encoding="utf-8")
            _make_executable(hook_path)
        installed.append(hook_name)

    return installed


def _update_ctx_block(hook_path: Path, existing: str, new_block: str) -> None:
    """Replace the ctx block in an existing hook file."""
    start = existing.index(CTX_HOOK_START)
    end = existing.index(CTX_HOOK_END) + len(CTX_HOOK_END)
    # Consume trailing newline if present
    if end < len(existing) and existing[end] == "\n":
        end += 1
    updated = existing[:start] + new_block + "\n" + existing[end:]
    hook_path.write_text(updated, encoding="utf-8")


def _chain_hook(hook_path: Path, existing: str, hook_block: str) -> None:
    """Append ctx block to an existing non-ctx hook."""
    if not existing.endswith("\n"):
        existing += "\n"
    hook_path.write_text(existing + hook_block + "\n", encoding="utf-8")


def _remove_hooks(root: Path) -> list[str]:
    """Remove ctx blocks from git hooks. Returns names of modified hooks."""
    hooks_dir = root / ".git" / "hooks"
    removed = []

    for hook_name in HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        if not hook_path.exists():
            continue

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
            hook_path.write_text(remaining + "\n", encoding="utf-8")

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
    gitignore.write_text(content, encoding="utf-8")


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
    gitignore.write_text("\n".join(filtered) + "\n" if filtered else "", encoding="utf-8")


def _rmtree(path: Path) -> None:
    """Remove a directory tree. Handles read-only files on Windows."""
    import shutil

    def _on_error(func, fpath, exc_info):
        os.chmod(fpath, 0o777)
        func(fpath)

    shutil.rmtree(path, onerror=_on_error)


# ── PID debounce ────────────────────────────────────────────────────

def _acquire_pid(root: Path) -> bool:
    """Try to claim the PID file. Returns True if acquired."""
    pid_path = root / PID_FILE
    if pid_path.exists():
        try:
            stored_pid = int(pid_path.read_text(encoding="utf-8").strip())
            if _pid_alive(stored_pid):
                return False  # Another hook is running
        except (ValueError, OSError):
            pass  # Stale or corrupt PID file, proceed
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_pid(root: Path) -> None:
    """Release the PID file."""
    pid_path = root / PID_FILE
    try:
        if pid_path.exists():
            stored_pid = int(pid_path.read_text(encoding="utf-8").strip())
            if stored_pid == os.getpid():
                pid_path.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


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
    """Append an entry to hook_log.json."""
    log_path = ctx_dir / HOOK_LOG_FILE
    try:
        data = load_json_safe(log_path, {"runs": []})
        if "runs" not in data or not isinstance(data["runs"], list):
            data = {"runs": []}
        data["runs"].append(entry)
        save_json_atomic(log_path, data)
    except Exception as exc:
        # Never let telemetry failure crash the hook
        logger.debug("Failed to write hook log: %s", exc)
