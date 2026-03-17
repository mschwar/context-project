import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import subprocess

from ctx.git import (
    STAGED_CMD,
    UNBORN_UNSTAGED_CMD,
    UNSTAGED_CMD,
    UNTRACKED_CMD,
    get_changed_files,
    is_unborn_head_error,
)
COMMON_KWARGS = dict(capture_output=True, text=True, check=True)


def _mock_run(unstaged_stdout: str = "", staged_stdout: str = ""):
    """Return a side_effect function that returns appropriate mocks per call."""
    responses = {
        tuple(UNSTAGED_CMD): unstaged_stdout,
        tuple(STAGED_CMD): staged_stdout,
    }

    def side_effect(cmd, **kwargs):
        mock = MagicMock()
        mock.stdout = responses[tuple(cmd)]
        mock.stderr = ""
        mock.returncode = 0
        return mock

    return side_effect


def test_get_changed_files_no_changes(tmp_path):
    with patch("subprocess.run", side_effect=_mock_run()) as mock_run:
        changes = get_changed_files(tmp_path)
        assert changes == []
        assert mock_run.call_count == 2
        mock_run.assert_any_call(UNSTAGED_CMD, cwd=tmp_path, **COMMON_KWARGS)
        mock_run.assert_any_call(STAGED_CMD, cwd=tmp_path, **COMMON_KWARGS)


def test_get_changed_files_with_changes(tmp_path):
    with patch("subprocess.run", side_effect=_mock_run(
        unstaged_stdout="src/file1.py\ndocs/README.md\n",
    )) as mock_run:
        changes = get_changed_files(tmp_path)
        # Sorted alphabetically since we deduplicate via a set
        assert set(changes) == {tmp_path / "src" / "file1.py", tmp_path / "docs" / "README.md"}
        assert mock_run.call_count == 2


def test_get_changed_files_deduplicates_staged_and_unstaged(tmp_path):
    with patch("subprocess.run", side_effect=_mock_run(
        unstaged_stdout="src/file1.py\ndocs/README.md\n",
        staged_stdout="src/file1.py\nnew_file.py\n",
    )):
        changes = get_changed_files(tmp_path)
        assert set(changes) == {
            tmp_path / "src" / "file1.py",
            tmp_path / "docs" / "README.md",
            tmp_path / "new_file.py",
        }


def test_get_changed_files_git_command_fails(tmp_path):
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(
        1, UNSTAGED_CMD, stderr="fatal: not a git repository"
    )):
        with pytest.raises(RuntimeError) as excinfo:
            get_changed_files(tmp_path)
        assert "Git command failed: fatal: not a git repository" in str(excinfo.value)


def test_get_changed_files_git_not_found(tmp_path):
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError) as excinfo:
            get_changed_files(tmp_path)
        assert "Git executable not found" in str(excinfo.value)


def test_get_changed_files_handles_unborn_head(tmp_path):
    def side_effect(cmd, **kwargs):
        if cmd == UNSTAGED_CMD:
            raise subprocess.CalledProcessError(128, cmd, stderr="fatal: bad revision 'HEAD'")
        mock = MagicMock()
        outputs = {
            tuple(UNBORN_UNSTAGED_CMD): "tracked.py\n",
            tuple(STAGED_CMD): "tracked.py\nstaged.py\n",
            tuple(UNTRACKED_CMD): "untracked.py\n",
        }
        mock.stdout = outputs[tuple(cmd)]
        mock.stderr = ""
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=side_effect):
        changes = get_changed_files(tmp_path)

    assert changes == [
        tmp_path / "staged.py",
        tmp_path / "tracked.py",
        tmp_path / "untracked.py",
    ]


def test_is_unborn_head_error_matches_known_messages() -> None:
    assert is_unborn_head_error("fatal: bad revision 'HEAD'")
    assert is_unborn_head_error("fatal: ambiguous argument 'HEAD': unknown revision or path not in the working tree.")
    assert is_unborn_head_error("## No commits yet on main") is False
    assert not is_unborn_head_error("fatal: not a git repository")
