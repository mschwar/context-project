from pathlib import Path
import subprocess
from typing import List

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
    try:
        changed_files_str: set[str] = set()
        for command in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "diff", "--name-only", "--cached"],
        ):
            result = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files_str.update(f for f in result.stdout.strip().splitlines() if f)
        return [repo_path / f for f in sorted(changed_files_str)]
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError("Git executable not found. Is Git installed and in your PATH?")
