import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import MagicMock
from importlib import import_module

# Import app for TestClient directly
from ctx.server import app
# Import write_manifest for creating test data
from ctx.manifest import write_manifest

@pytest.fixture
def cli_runner():
    return CliRunner()

@pytest.fixture
def test_client():
    return TestClient(app)

def test_serve_command_calls_start_server(cli_runner, monkeypatch):
    cli_module = import_module("ctx.cli")
    mock_start_server = MagicMock()
    # Patch start_server in ctx.server module, as it's imported within the cli.serve function
    monkeypatch.setattr("ctx.server.start_server", mock_start_server)

    result = cli_runner.invoke(cli_module.cli, ["serve", "--host", "127.0.0.2", "--port", "8001"])

    assert result.exit_code == 0
    mock_start_server.assert_called_once_with(host="127.0.0.2", port=8001)
    assert "Starting ctx MCP server on http://127.0.0.2:8001" in result.output

def test_get_mcp_context_success(test_client, tmp_path):
    test_dir = tmp_path / "project" / "subdir"
    test_dir.mkdir(parents=True)
    manifest_body = """# Subdir
- file.py - a python file"""
    write_manifest(
        path=test_dir,
        model="test-model",
        content_hash="sha256:dummy_hash",
        files=1,
        dirs=0,
        tokens_total=20,
        body=manifest_body
    )

    response = test_client.get(f"/mcp/context/{test_dir.resolve()}")

    assert response.status_code == 200
    assert "content" in response.json()
    returned_content = response.json()["content"]
    assert "# Subdir" in returned_content
    assert "- file.py - a python file" in returned_content
    assert "content_hash: sha256:dummy_hash" in returned_content
    assert "model: test-model" in returned_content

def test_get_mcp_context_not_found(test_client, tmp_path):
    # Create the directory, but don't put a CONTEXT.md in it
    non_existent_manifest_dir = tmp_path / "dir_without_manifest"
    non_existent_manifest_dir.mkdir()
    response = test_client.get(f"/mcp/context/{non_existent_manifest_dir.resolve()}")
    assert response.status_code == 404
    assert "CONTEXT.md not found" in response.json()["detail"]

def test_get_mcp_context_not_a_directory(test_client, tmp_path):
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("hello")
    response = test_client.get(f"/mcp/context/{test_file.resolve()}")
    assert response.status_code == 404
    assert "is not a directory" in response.json()["detail"]
