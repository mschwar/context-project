"""Tests for the deterministic zero-LLM stdio MCP server (`ctx.mcp_server`)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ctx.api import CheckResult, ExportResult, RefreshResult, ResetResult
from ctx.init import init_project
import ctx.mcp_server as mcp_module


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


def test_initialize_tools_list_and_resources_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = _run_server(
        monkeypatch,
        tmp_path,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}}),
    )

    assert responses[0]["result"]["serverInfo"]["name"] == "ctx"
    tool_names = [t["name"] for t in responses[1]["result"]["tools"]]
    assert tool_names == ["ctx_refresh", "ctx_check", "ctx_export", "ctx_reset", "ctx_impact"]
    resource_uris = [r["uri"] for r in responses[2]["result"]["resources"]]
    assert resource_uris == [
        "ctx://.ctx/CONTEXT.md",
        "ctx://.ctx/CONTEXT-1.md",
        "ctx://.ctx/CONTEXT-0.md",
        "ctx://.ctx/metadata.json",
    ]
    assert responses[3]["result"] == {}


def test_mcp_tool_dispatch_and_capsule_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    (repo / "core.py").write_text("def alpha() -> int:\n    return 1\n", encoding="utf-8")
    (repo / "caller.py").write_text("from core import alpha\n\ndef beta() -> int:\n    return alpha()\n", encoding="utf-8")
    init_project(repo)

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
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "ctx_export", "arguments": {"path": "repo", "capsule": True, "depth": 1}},
            }
        ),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ctx_impact", "arguments": {"path": "repo", "target": "core.py"}},
            }
        ),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "ctx://.ctx/CONTEXT-0.md", "path": "repo"},
            }
        ),
    )

    check_payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert check_payload["summary"]["invalid"] == 0

    cap_payload = json.loads(responses[1]["result"]["content"][0]["text"])
    assert cap_payload["repo_name"] == "repo"
    assert cap_payload["languages"]["Python"] == 2

    impact_payload = json.loads(responses[2]["result"]["content"][0]["text"])
    assert "caller.py" in impact_payload["direct_inbound_dependents"]

    res_content = responses[3]["result"]["contents"][0]
    assert "Architecture & Authority Map (CONTEXT-0)" in res_content["text"]


def test_mcp_security_confinement_and_argument_validation(
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
                "params": {"name": "ctx_check", "arguments": {"path": "../outside"}},
            }
        ),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "ctx_check", "arguments": {"path": str(target.resolve())}},
            }
        ),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ctx_export", "arguments": {"path": "repo", "depth": "deep"}},
            }
        ),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "ctx://../secret.txt", "path": "repo"},
            }
        ),
    )

    assert responses[0]["error"]["data"]["code"] == "path_traversal_denied"
    assert responses[1]["error"]["data"]["code"] == "absolute_path_not_allowed"
    assert responses[2]["error"]["data"]["code"] == "invalid_depth"
    assert responses[3]["error"]["data"]["code"] == "path_traversal_denied"
