import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import subprocess

from ctx.git import get_changed_files

def test_get_changed_files_no_changes(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        changes = get_changed_files(tmp_path)
        assert changes == []
        mock_run.assert_called_once_with(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True
        )

def test_get_changed_files_with_changes(tmp_path):
    # Simulate a repository with some changed files
    # The actual files don't need to exist for this mock
    mock_result = MagicMock()
    mock_result.stdout = """src/file1.py
docs/README.md
"""
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        changes = get_changed_files(tmp_path)
        expected_changes = [tmp_path / "src" / "file1.py", tmp_path / "docs" / "README.md"]
        assert changes == expected_changes
        mock_run.assert_called_once() # Parameters checked in previous test

def test_get_changed_files_git_command_fails(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "fatal: not a git repository"
    mock_result.returncode = 1

    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["git", "diff"], stderr="fatal: not a git repository")) as mock_run:
        with pytest.raises(RuntimeError) as excinfo:
            get_changed_files(tmp_path)
        assert "Git command failed: fatal: not a git repository" in str(excinfo.value)
        mock_run.assert_called_once()

def test_get_changed_files_git_not_found(tmp_path):
    with patch("subprocess.run", side_effect=FileNotFoundError) as mock_run:
        with pytest.raises(RuntimeError) as excinfo:
            get_changed_files(tmp_path)
        assert "Git executable not found" in str(excinfo.value)
        mock_run.assert_called_once()
