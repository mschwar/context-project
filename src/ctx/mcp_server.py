"""Deterministic zero-LLM MCP stdio server for ctx."""

from __future__ import annotations

from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys
from typing import Any

from ctx import __version__, api

# MCP uses date-stamped protocol revisions during initialize, not semver.
PROTOCOL_VERSION = "2024-11-05"

TOOL_DEFINITIONS: list[dict[str, object]] = [
    {
        "name": "ctx_refresh",
        "description": (
            "Deterministically generate or update .ctx/ architectural and dependency maps "
            "using static AST and multi-language parsers (zero LLM calls)."
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
                    "description": "Regenerate .ctx/ maps even when structural hashes match.",
                    "default": False,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview whether .ctx/ maps are stale without writing.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_check",
        "description": (
            "Check deterministic .ctx/ structural map freshness, coverage, and validity."
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
                    "description": "Full validation including .ctx/ frontmatter and export checks.",
                    "default": False,
                },
                "stats": {
                    "type": "boolean",
                    "description": "Return coverage and estimated token statistics.",
                    "default": False,
                },
                "diff": {
                    "type": "boolean",
                    "description": "Report whether .ctx/CONTEXT.md is stale.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_export",
        "description": (
            "Export deterministic .ctx/ structural context or a structured fleet capsule."
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
                    "description": "Which exports to return.",
                    "default": "all",
                },
                "depth": {
                    "type": "integer",
                    "description": "Export tier depth (0 = CONTEXT-0, 1 = CONTEXT-1, omit = full).",
                },
                "capsule": {
                    "type": "boolean",
                    "description": "Emit structured FleetCapsuleResult JSON instead of plain markdown.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "ctx_reset",
        "description": "Remove legacy per-directory CONTEXT.md files from a directory tree.",
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
        "name": "ctx_impact",
        "description": (
            "Analyze directed dependency blast radius, reverse dependents, coupled test suites, "
            "affected entrypoints/surfaces, and governing authority docs for a file, subsystem, "
            "symbol, or git diff."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Repo-relative file path, subsystem/directory path, or symbol name.",
                },
                "git_diff": {
                    "type": "string",
                    "description": "Optional git diff revision or range (e.g. HEAD, origin/main...HEAD, WORKTREE).",
                },
                "staged": {
                    "type": "boolean",
                    "description": "Analyze staged git changes when true.",
                    "default": False,
                },
                "path": {
                    "type": "string",
                    "description": "Repository root path relative to the server root.",
                    "default": ".",
                },
                "depth": {
                    "type": "integer",
                    "description": "Optional maximum reverse-dependency hop distance (>= 1).",
                },
            },
            "required": [],
        },
    },
]

RESOURCE_DEFINITIONS: list[dict[str, str]] = [
    {
        "uri": "ctx://.ctx/CONTEXT.md",
        "name": ".ctx/CONTEXT.md",
        "description": "Full deterministic structural, dependency, and file-signature map.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "ctx://.ctx/CONTEXT-1.md",
        "name": ".ctx/CONTEXT-1.md",
        "description": "Depth-1 subsystem dependency and architectural boundary map.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "ctx://.ctx/CONTEXT-0.md",
        "name": ".ctx/CONTEXT-0.md",
        "description": "Depth-0 1-page repository architecture, entrypoints, and authority map.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "ctx://.ctx/metadata.json",
        "name": ".ctx/metadata.json",
        "description": "Repository initialization metadata, version, timestamps, and structural hashes.",
        "mimeType": "application/json",
    },
]

_RESOURCE_LOOKUP: dict[str, dict[str, str]] = {}
for _res in RESOURCE_DEFINITIONS:
    _filename = _res["name"].split("/", 1)[1]
    _RESOURCE_LOOKUP[_res["uri"]] = _res
    _RESOURCE_LOOKUP[f"ctx://{_filename}"] = _res
    _RESOURCE_LOOKUP[_res["name"]] = _res
    _RESOURCE_LOOKUP[_filename] = _res


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


class UnknownResourceError(MCPToolError):
    """Raised when a requested MCP resource URI is not recognized."""

    def __init__(self, uri: str) -> None:
        super().__init__(f"Unknown resource: {uri}", error_code="unknown_resource")


class CtxNotInitializedError(MCPToolError):
    """Raised when .ctx/ resources are requested before ctx init has been run."""

    def __init__(self) -> None:
        super().__init__(
            "Repository not initialized: .ctx/ directory not found. Run 'ctx init' first.",
            error_code="ctx_not_initialized",
        )


class ResourceNotFoundError(MCPToolError):
    """Raised when .ctx/ exists but the requested export/metadata file is missing."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Resource file not found: {name}", error_code="resource_not_found")


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
        if method == "resources/list":
            self._write_result(request_id, {"resources": RESOURCE_DEFINITIONS})
            return
        if method == "resources/read":
            self._handle_resources_read(request_id, request.get("params", {}))
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
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {"name": "ctx", "version": __version__},
            },
        )

    def _handle_resources_read(self, request_id: Any, params: object) -> None:
        if not isinstance(params, dict):
            self._write_error(request_id, -32602, "Invalid params for resources/read")
            return

        uri = params.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            self._write_error(request_id, -32602, "Invalid params for resources/read: uri is required")
            return

        try:
            content_item = self._read_resource(uri.strip(), params.get("path", "."))
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

        self._write_result(request_id, {"contents": [content_item]})

    def _read_resource(self, uri: str, relative_path: object = ".") -> dict[str, str]:
        stripped = uri[len("ctx://") :] if uri.startswith("ctx://") else uri
        if ".." in Path(stripped).parts:
            raise PathTraversalDeniedError(uri)

        resource = _RESOURCE_LOOKUP.get(uri)
        if resource is None:
            raise UnknownResourceError(uri)

        target_root = self._resolve_path(relative_path)
        ctx_dir = target_root / ".ctx"
        if not ctx_dir.is_dir():
            raise CtxNotInitializedError()

        filename = resource["name"].split("/", 1)[1]
        file_path = (ctx_dir / filename).resolve()
        if not file_path.is_relative_to(ctx_dir.resolve()):
            raise PathTraversalDeniedError(uri)
        if not file_path.is_file():
            raise ResourceNotFoundError(resource["name"])

        return {
            "uri": resource["uri"],
            "name": resource["name"],
            "mimeType": resource["mimeType"],
            "text": file_path.read_text(encoding="utf-8"),
        }

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
            "ctx_impact": self._call_impact,
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
        if depth is not None and (not isinstance(depth, int) or isinstance(depth, bool)):
            raise InvalidToolArgumentsError("depth must be an integer", error_code="invalid_depth")
        if bool(arguments.get("capsule", False)):
            cap = api.build_fleet_capsule(path, depth=1 if depth is None else depth)
            return asdict(cap)
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

    def _call_impact(self, arguments: dict[str, object]) -> dict[str, object]:
        path = self._resolve_path(arguments.get("path", "."))
        depth = arguments.get("depth")
        if depth is not None and (not isinstance(depth, int) or isinstance(depth, bool) or depth < 1):
            raise InvalidToolArgumentsError("depth must be a positive integer", error_code="invalid_depth")

        git_diff = arguments.get("git_diff")
        staged = bool(arguments.get("staged", False))
        if git_diff is not None and not isinstance(git_diff, str):
            raise InvalidToolArgumentsError("git_diff must be a string", error_code="invalid_git_diff")
        if git_diff is not None or staged:
            try:
                diff_result = api.analyze_diff_impact(
                    path,
                    git_diff=git_diff.strip() if isinstance(git_diff, str) else None,
                    staged=staged,
                    max_depth=depth,
                )
            except ValueError as exc:
                raise InvalidToolArgumentsError(str(exc), error_code="target_not_found") from exc
            return asdict(diff_result)

        target = arguments.get("target")
        if not isinstance(target, str) or not target.strip():
            raise InvalidToolArgumentsError("target must be a non-empty string", error_code="invalid_target")
        try:
            result = api.analyze_impact(path, target.strip(), max_depth=depth)
        except ValueError as exc:
            raise InvalidToolArgumentsError(str(exc), error_code="target_not_found") from exc
        return asdict(result)

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
