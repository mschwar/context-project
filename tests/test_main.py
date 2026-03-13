"""Tests for module execution via ``python -m ctx``."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ctx import __version__


def test_python_module_invocation_reports_version() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    pythonpath_entries = [str(repo_root / "src")]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    result = subprocess.run(
        [sys.executable, "-m", "ctx", "--version"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"ctx, version {__version__}" in result.stdout
