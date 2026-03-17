from pathlib import Path
import subprocess
from typing import List

UNSTAGED_CMD = ["git", "diff", "--name-only", "HEAD"]
STAGED_CMD = ["git", "diff", "--name-only", "--cached"]
UNBORN_UNSTAGED_CMD = ["git", "diff", "--name-only"]
UNTRACKED_CMD = ["git", "ls-files", "--others", "--exclude-standard"]


def is_unborn_head_error(stderr: str) -> bool:
    """Return True when git stderr indicates the repo has no commits yet."""
    normalized = (stderr or "").lower()
    return any(
        marker in normalized
        for marker in (
            "bad revision 'head'",
            "ambiguous argument 'head'",
            "unknown revision or path not in the working tree",
            "does not have any commits yet",
            "needed a single revision",
        )
    )


def get_changed_files(repo_path: Path) -> List[Path]:
    """
    Retrieves a list of files that have been changed in the git repository
    Since the last commit or are staged.

    Args:
        repo_path: The root path of the git repository.

    Returns:
        A list of Path objects for the changed files.

    Raises:
        RuntimeError: If the command fails or it's not a git repository.
    """
    def _collect(command_set: list[list[str]]) -> List[Path]:
        changed_files_str: set[str] = set()
        for command in command_set:
            result = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files_str.update(f for f in result.stdout.strip().splitlines() if f)
        return [repo_path / f for f in sorted(changed_files_str)]

    try:
        return _collect([UNSTAGED_CMD, STAGED_CMD])
    except subprocess.CalledProcessError as e:
        if list(e.cmd) == UNSTAGED_CMD and is_unborn_head_error(e.stderr):
            return _collect([UNBORN_UNSTAGED_CMD, STAGED_CMD, UNTRACKED_CMD])
        raise RuntimeError(f"Git command failed: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError("Git executable not found. Is Git installed and in your PATH?")
