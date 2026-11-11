"""Tests for the optional FastAPI HTTP server (`ctx.server`)."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner
from fastapi.testclient import TestClient
import pytest

from ctx.server import app


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def test_client(tmp_path):
    app.state.served_root = tmp_path.resolve()
    return TestClient(app)


def test_serve_command_calls_start_server(cli_runner, monkeypatch):
    cli_module = import_module("ctx.cli")
    mock_start_server = MagicMock()
    monkeypatch.setattr("ctx.server.start_server", mock_start_server)

    result = cli_runner.invoke(cli_module.cli, ["serve", "--host", "127.0.0.2", "--port", "8001"])

    assert result.exit_code == 0
    mock_start_server.assert_called_once()
    call_kwargs = mock_start_server.call_args[1]
    assert call_kwargs["host"] == "127.0.0.2"
    assert call_kwargs["port"] == 8001
    assert "root" in call_kwargs
    assert "Starting ctx HTTP server on http://127.0.0.2:8001" in result.output


def test_serve_command_with_explicit_path(cli_runner, monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    mock_start_server = MagicMock()
    monkeypatch.setattr("ctx.server.start_server", mock_start_server)

    serve_root = tmp_path / "project"
    serve_root.mkdir()

    result = cli_runner.invoke(cli_module.cli, ["serve", str(serve_root), "--port", "9000"])

    assert result.exit_code == 0
    mock_start_server.assert_called_once()
    call_kwargs = mock_start_server.call_args[1]
    assert call_kwargs["port"] == 9000
    assert call_kwargs["root"] == serve_root.resolve()
    assert f"Serving manifests from: {serve_root.resolve()}" in result.output


def test_serve_command_with_mcp_calls_stdio_server(cli_runner, monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    calls: dict[str, object] = {}

    class _DummyServer:
        def __init__(self, root: Path) -> None:
            calls["root"] = root

        def run(self) -> None:
            calls["ran"] = True

    monkeypatch.setattr("ctx.mcp_server.CtxMCPServer", _DummyServer)

    result = cli_runner.invoke(cli_module.cli, ["serve", str(tmp_path), "--mcp"])

    assert result.exit_code == 0
    assert calls["root"] == tmp_path.resolve()
    assert calls["ran"] is True
    assert result.output == ""


def test_get_mcp_context_serves_deterministic_ctx_map(test_client, tmp_path):
    ctx_dir = tmp_path / ".ctx"
    ctx_dir.mkdir(parents=True)
    (ctx_dir / "CONTEXT.md").write_text(
        "---\nmode: tier2\n---\n# repo — Architecture\n",
        encoding="utf-8",
    )

    for endpoint in ("/mcp/context", "/mcp/context/."):
        response = test_client.get(endpoint)
        assert response.status_code == 200
        assert "mode: tier2" in response.json()["content"]

    assert test_client.get("/mcp/context/.ctx").status_code == 404


def test_get_mcp_context_not_found_when_uninitialized(test_client, tmp_path):
    sub = tmp_path / "dir_without_manifest"
    sub.mkdir()
    response = test_client.get("/mcp/context/dir_without_manifest")
    assert response.status_code == 404


def test_get_mcp_context_not_a_directory(test_client, tmp_path):
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("hello", encoding="utf-8")
    response = test_client.get("/mcp/context/test_file.txt")
    assert response.status_code == 404
    assert "is not a directory" in response.json()["detail"]


def test_http_root_reports_http_server(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "ctx HTTP server is running"
