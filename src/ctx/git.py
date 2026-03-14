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
        # --name-only: Show only names of changed files
        # HEAD: Compare against the latest commit
        # The output will be relative to the repository root.
        command = ["git", "diff", "--name-only", "HEAD"]
        result = subprocess.run(
            command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        # Split by lines, filter out empty lines, and convert to Path objects
        changed_files_str = result.stdout.strip().splitlines()
        changed_files = [repo_path / f for f in changed_files_str if f]
        return changed_files
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError("Git executable not found. Is Git installed and in your PATH?")
