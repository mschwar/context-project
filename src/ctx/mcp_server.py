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


# MCP uses date-stamped protocol revisions during initialize, not semver.
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
    {
        "name": "ctx_board",
        "description": (
            "Read the running board (refresh history and cost analytics) for a repository. "
            "Returns aggregate stats, per-model breakdown, and recent runs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path, relative to the server root.",
                    "default": ".",
                },
                "since": {
                    "type": "string",
                    "description": "Time filter: relative (7d, 4w) or absolute (2026-03-01).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_global_board",
        "description": (
            "Read the global running board with aggregated cost analytics across all repositories."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


class MCPToolError(ValueError):
    """Base class for client-visible MCP tool argument errors."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class InvalidToolArgumentsError(MCPToolError):
    """Raised when tool arguments fail schema or type validation."""

    def __init__(self, message: str, *, error_code: str = "invalid_tool_arguments") -> None:
        super().__init__(message, error_code=error_code)


class AbsolutePathNotAllowedError(MCPToolError):
    """Raised when a tool argument tries to use an absolute path."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"Absolute paths not allowed: {path}",
            error_code="absolute_path_not_allowed",
        )


class PathTraversalDeniedError(MCPToolError):
    """Raised when a resolved path escapes the configured server root."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Path traversal denied: {path}", error_code="path_traversal_denied")


class PathNotFoundError(MCPToolError):
    """Raised when a requested relative path does not exist under the server root."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Path not found: {path}", error_code="path_not_found")


class PathNotDirectoryError(MCPToolError):
    """Raised when a requested path exists but is not a directory."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Path is not a directory: {path}", error_code="path_not_directory")


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
            "ctx_board": self._call_board,
            "ctx_global_board": self._call_global_board,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            self._write_error(request_id, -32602, f"Unknown tool: {tool_name}")
            return

        try:
            result = handler(arguments)
        except MCPToolError as exc:
            self._write_error(
                request_id,
                -32602,
                str(exc),
                data={"code": exc.error_code},
            )
            return
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
            raise InvalidToolArgumentsError("depth must be an integer", error_code="invalid_depth")
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

    def _call_board(self, arguments: dict[str, object]) -> dict[str, object]:
        from ctx.config import load_config, Config
        from ctx.stats_board import read_board
        path = self._resolve_path(arguments.get("path", "."))
        since = arguments.get("since")
        if since is not None and not isinstance(since, str):
            since = None
        try:
            config = load_config(path, require_api_key=False)
        except Exception:
            config = Config()
        return read_board(path, config, since=since)

    def _call_global_board(self, arguments: dict[str, object]) -> dict[str, object]:
        from ctx.stats_board import read_global_board
        return read_global_board()

    def _resolve_path(self, relative: object) -> Path:
        if not isinstance(relative, str):
            raise InvalidToolArgumentsError("path must be a string", error_code="invalid_path_type")

        candidate = Path(relative or ".")
        if candidate.is_absolute():
            raise AbsolutePathNotAllowedError(relative)

        resolved = (self._root / candidate).resolve()
        if not resolved.is_relative_to(self._root):
            raise PathTraversalDeniedError(relative)
        if not resolved.exists():
            raise PathNotFoundError(relative)
        if not resolved.is_dir():
            raise PathNotDirectoryError(relative)
        return resolved

    def _write_result(self, request_id: Any, result: Any) -> None:
        self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _write_error(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        error: dict[str, object] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._write_message({"jsonrpc": "2.0", "id": request_id, "error": error})

    @staticmethod
    def _write_message(payload: dict[str, object]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
