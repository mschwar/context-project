"""Tests for the stdio MCP server."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

import ctx.mcp_server as mcp_module
from ctx.api import CheckResult, ExportResult, RefreshResult, ResetResult


def _run_server(monkeypatch: pytest.MonkeyPatch, root: Path, *messages: str) -> list[dict]:
    stdin = io.StringIO("\n".join(messages) + ("\n" if messages else ""))
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    server = mcp_module.CtxMCPServer(root)
    server.run()

    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


def test_initialize_handshake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
    )

    assert responses[0]["result"]["serverInfo"]["name"] == "ctx"
    assert responses[0]["result"]["protocolVersion"] == mcp_module.PROTOCOL_VERSION


def test_tools_list_exposes_all_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    )

    tool_names = [tool["name"] for tool in responses[0]["result"]["tools"]]
    assert tool_names == ["ctx_refresh", "ctx_check", "ctx_export", "ctx_reset"]


def test_unknown_method_returns_jsonrpc_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "nope", "params": {}}),
    )

    assert responses[0]["error"]["code"] == -32601


def test_invalid_json_returns_parse_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = _run_server(monkeypatch, tmp_path, "{")

    assert responses[0]["error"]["code"] == -32700


def test_shutdown_exits_cleanly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "shutdown", "params": {}}),
    )

    assert responses[0]["result"] == {}


def test_notification_is_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
    )

    assert len(responses) == 1
    assert responses[0]["id"] == 1


def test_ctx_check_tool_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    seen: dict[str, object] = {}

    def fake_check(path: Path, **kwargs: object) -> CheckResult:
        seen["path"] = path
        seen["kwargs"] = kwargs
        return CheckResult(mode="health", directories=[], summary={"fresh": 1, "stale": 0, "missing": 0})

    monkeypatch.setattr(mcp_module.api, "check", fake_check)

    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ctx_check", "arguments": {"path": "repo", "verify": True}},
            }
        ),
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert seen["path"] == target.resolve()
    assert seen["kwargs"] == {"verify": True, "stats": False, "diff": False}
    assert payload["mode"] == "health"


def test_ctx_export_tool_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()

    monkeypatch.setattr(
        mcp_module.api,
        "export_context",
        lambda path, filter_mode, depth: ExportResult(
            manifests_exported=1,
            filter=filter_mode,
            depth=depth,
            content=f"export:{path.name}",
        ),
    )

    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ctx_export", "arguments": {"path": "repo", "filter": "stale", "depth": 2}},
            }
        ),
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert payload["filter"] == "stale"
    assert payload["depth"] == 2
    assert payload["content"] == "export:repo"


def test_ctx_reset_tool_call_forces_noninteractive_yes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    seen: dict[str, object] = {}

    def fake_reset(path: Path, *, dry_run: bool, yes: bool) -> ResetResult:
        seen["path"] = path
        seen["dry_run"] = dry_run
        seen["yes"] = yes
        return ResetResult(manifests_removed=0, paths=["CONTEXT.md"])

    monkeypatch.setattr(mcp_module.api, "reset", fake_reset)

    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ctx_reset", "arguments": {"path": "repo", "dry_run": True}},
            }
        ),
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert seen["path"] == target.resolve()
    assert seen["dry_run"] is True
    assert seen["yes"] is True
    assert payload["paths"] == ["CONTEXT.md"]


def test_ctx_refresh_tool_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    seen: dict[str, object] = {}

    def fake_refresh(path: Path, *, force: bool, dry_run: bool) -> RefreshResult:
        seen["path"] = path
        seen["force"] = force
        seen["dry_run"] = dry_run
        return RefreshResult(
            dirs_processed=0,
            dirs_skipped=1,
            files_processed=0,
            tokens_used=0,
            errors=[],
            budget_exhausted=False,
            strategy="incremental",
            est_cost_usd=0.0,
            stale_directories=["repo"],
        )

    monkeypatch.setattr(mcp_module.api, "refresh", fake_refresh)

    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ctx_refresh", "arguments": {"path": "repo", "dry_run": True, "force": True}},
            }
        ),
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert seen["path"] == target.resolve()
    assert seen["force"] is True
    assert seen["dry_run"] is True
    assert payload["stale_directories"] == ["repo"]


def test_tool_path_validation_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ctx_check", "arguments": {"path": "../outside"}},
            }
        ),
    )

    error = responses[0]["error"]
    assert error["code"] == -32602
    assert error["message"] == "Path traversal denied: ../outside"
    assert error["data"]["code"] == "path_traversal_denied"


def test_invalid_depth_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "repo"
    target.mkdir()

    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ctx_export", "arguments": {"path": "repo", "depth": "deep"}},
            }
        ),
    )

    error = responses[0]["error"]
    assert error["code"] == -32602
    assert error["message"] == "depth must be an integer"
    assert error["data"]["code"] == "invalid_depth"


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    server = mcp_module.CtxMCPServer(tmp_path)

    with pytest.raises(mcp_module.PathTraversalDeniedError, match="Path traversal denied"):
        server._resolve_path("../outside")


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    server = mcp_module.CtxMCPServer(tmp_path)
    absolute = str((tmp_path.parent / "outside").resolve())

    with pytest.raises(mcp_module.AbsolutePathNotAllowedError, match="Absolute paths not allowed"):
        server._resolve_path(absolute)


def test_mcp_manifest_file_exists() -> None:
    manifest = json.loads((Path(__file__).resolve().parents[1] / "mcp.json").read_text(encoding="utf-8"))

    assert manifest["mcpServers"]["ctx"]["command"] == "ctx"
    assert manifest["mcpServers"]["ctx"]["args"] == ["serve", "--mcp"]
