"""MCP stdio server for ctx."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ctx import __version__
from ctx import api


PROTOCOL_VERSION = "2024-11-05"

TOOL_DEFINITIONS: list[dict[str, object]] = [
    {
        "name": "ctx_refresh",
        "description": (
            "Generate or update CONTEXT.md manifests for a directory tree. "
            "Analyzes source files using an LLM and produces structured summaries."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to refresh, relative to the server root.",
                    "default": ".",
                },
                "force": {
                    "type": "boolean",
                    "description": "Regenerate all manifests, even fresh ones.",
                    "default": False,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview what would be regenerated without making changes.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_check",
        "description": (
            "Check manifest health, coverage, freshness, and validity across a directory tree. "
            "Returns status of each directory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to check, relative to the server root.",
                    "default": ".",
                },
                "verify": {
                    "type": "boolean",
                    "description": "Full validation including frontmatter field checks.",
                    "default": False,
                },
                "stats": {
                    "type": "boolean",
                    "description": "Return coverage statistics.",
                    "default": False,
                },
                "diff": {
                    "type": "boolean",
                    "description": "Show CONTEXT.md files that changed since last generation.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_export",
        "description": (
            "Export CONTEXT.md manifests as concatenated text. "
            "Returns all manifests in a single string for context loading."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to export from, relative to the server root.",
                    "default": ".",
                },
                "filter": {
                    "type": "string",
                    "enum": ["all", "stale", "missing"],
                    "description": "Which manifests to export.",
                    "default": "all",
                },
                "depth": {
                    "type": "integer",
                    "description": "Limit export to N nesting levels.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_reset",
        "description": "Remove all CONTEXT.md files from a directory tree. Destructive operation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to reset, relative to the server root.",
                    "default": ".",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "List files that would be deleted without removing them.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
]


class CtxMCPServer:
    """Stdio MCP server for ctx."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._shutdown_requested = False

    def run(self) -> None:
        """Read JSON-RPC requests from stdin and write responses to stdout."""
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
        while not self._shutdown_requested:
            line = sys.stdin.readline()
            if line == "":
                break
            payload = line.strip()
            if not payload:
                continue
            try:
                request = json.loads(payload)
            except json.JSONDecodeError:
                self._write_error(None, -32700, "Parse error")
                continue
            self._handle_request(request)

    def _handle_request(self, request: object) -> None:
        if not isinstance(request, dict):
            self._write_error(None, -32600, "Invalid Request")
            return

        request_id = request.get("id")
        method = request.get("method")

        if request_id is None:
            return
        if not isinstance(method, str):
            self._write_error(request_id, -32600, "Invalid Request")
            return

        if method == "initialize":
            self._handle_initialize(request_id)
            return
        if method == "tools/list":
            self._write_result(request_id, {"tools": TOOL_DEFINITIONS})
            return
        if method == "tools/call":
            self._handle_tools_call(request_id, request.get("params", {}))
            return
        if method == "shutdown":
            self._shutdown_requested = True
            self._write_result(request_id, {})
            return

        self._write_error(request_id, -32601, f"Method not found: {method}")

    def _handle_initialize(self, request_id: Any) -> None:
        self._write_result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ctx", "version": __version__},
            },
        )

    def _handle_tools_call(self, request_id: Any, params: object) -> None:
        if not isinstance(params, dict):
            self._write_error(request_id, -32602, "Invalid params for tools/call")
            return

        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if not isinstance(tool_name, str) or not isinstance(arguments, dict):
            self._write_error(request_id, -32602, "Invalid params for tools/call")
            return

        handlers = {
            "ctx_refresh": self._call_refresh,
            "ctx_check": self._call_check,
            "ctx_export": self._call_export,
            "ctx_reset": self._call_reset,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            self._write_error(request_id, -32602, f"Unknown tool: {tool_name}")
            return

        try:
            result = handler(arguments)
        except Exception as exc:
            self._write_error(request_id, -32603, str(exc))
            return

        self._write_result(
            request_id,
            {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
        )

    def _call_refresh(self, arguments: dict[str, object]) -> dict[str, object]:
        path = self._resolve_path(arguments.get("path", "."))
        result = api.refresh(
            path,
            force=bool(arguments.get("force", False)),
            dry_run=bool(arguments.get("dry_run", False)),
        )
        return asdict(result)

    def _call_check(self, arguments: dict[str, object]) -> dict[str, object]:
        path = self._resolve_path(arguments.get("path", "."))
        result = api.check(
            path,
            verify=bool(arguments.get("verify", False)),
            stats=bool(arguments.get("stats", False)),
            diff=bool(arguments.get("diff", False)),
        )
        return asdict(result)

    def _call_export(self, arguments: dict[str, object]) -> dict[str, object]:
        path = self._resolve_path(arguments.get("path", "."))
        depth = arguments.get("depth")
        if depth is not None and not isinstance(depth, int):
            raise ValueError("depth must be an integer")
        result = api.export_context(
            path,
            filter_mode=str(arguments.get("filter", "all")),
            depth=depth,
        )
        return asdict(result)

    def _call_reset(self, arguments: dict[str, object]) -> dict[str, object]:
        path = self._resolve_path(arguments.get("path", "."))
        result = api.reset(
            path,
            dry_run=bool(arguments.get("dry_run", False)),
            yes=True,
        )
        return asdict(result)

    def _resolve_path(self, relative: object) -> Path:
        if not isinstance(relative, str):
            raise ValueError("path must be a string")

        candidate = Path(relative or ".")
        if candidate.is_absolute():
            raise ValueError(f"Absolute paths not allowed: {relative}")

        resolved = (self._root / candidate).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError(f"Path traversal denied: {relative}")
        if not resolved.exists():
            raise ValueError(f"Path not found: {relative}")
        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {relative}")
        return resolved

    def _write_result(self, request_id: Any, result: Any) -> None:
        self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _write_error(self, request_id: Any, code: int, message: str) -> None:
        self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        )

    @staticmethod
    def _write_message(payload: dict[str, object]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
