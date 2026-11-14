# AFO Spec 05 — MCP Server

> **Status:** Canonical
> **Stage:** 5 (MCP Server)
> **Prerequisites:** Read 00-conventions.md, 02-unified-api.md, 04-concurrency.md

---

## 1. Overview

Add a stdio-based MCP (Model Context Protocol) server that exposes ctx's 4 API functions as MCP tools. This is the primary integration path for IDE-hosted agents (Claude Code, Cursor, Windsurf). The existing FastAPI HTTP server moves to an optional dependency.

---

## 2. MCP Protocol Basics

MCP uses **JSON-RPC 2.0** over **stdin/stdout** (stdio transport). The server reads newline-delimited JSON-RPC requests from stdin and writes responses to stdout.

### Key JSON-RPC 2.0 Messages

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}}

// Notification (no id, no response expected)
{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
```

### MCP Lifecycle

1. Client sends `initialize` request with protocol version and capabilities.
2. Server responds with its capabilities and tool list.
3. Client sends `notifications/initialized`.
4. Client sends `tools/call` requests as needed.
5. Client may send `shutdown` or simply close stdin.

---

## 3. New File: `src/ctx/mcp_server.py`

### 3.1 Implementation Approach

**Hand-rolled JSON-RPC**, not an MCP SDK dependency. Reason: MCP SDK stability is not guaranteed and adds a heavy dependency. The protocol is simple enough to implement directly.

### 3.2 Server Class

```python
"""MCP stdio server for ctx.

Exposes ctx's API functions as MCP tools over JSON-RPC 2.0 on stdin/stdout.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ctx import __version__
from ctx import api


class CtxMCPServer:
    """Stdio MCP server.

    Reads JSON-RPC 2.0 requests from stdin, dispatches to ctx API functions,
    writes responses to stdout.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def run(self) -> None:
        """Main loop: read requests from stdin, write responses to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                self._write_error(None, -32700, "Parse error")
                continue
            self._handle_request(request)

    def _handle_request(self, request: dict) -> None:
        request_id = request.get("id")
        method = request.get("method", "")

        # Notifications (no id) — acknowledge silently
        if request_id is None:
            return

        if method == "initialize":
            self._handle_initialize(request_id, request.get("params", {}))
        elif method == "tools/list":
            self._handle_tools_list(request_id)
        elif method == "tools/call":
            self._handle_tools_call(request_id, request.get("params", {}))
        elif method == "shutdown":
            self._write_result(request_id, {})
            sys.exit(0)
        else:
            self._write_error(request_id, -32601, f"Method not found: {method}")

    def _write_result(self, request_id: Any, result: Any) -> None:
        response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    def _write_error(self, request_id: Any, code: int, message: str) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
```

### 3.3 Initialize Handler

```python
def _handle_initialize(self, request_id: Any, params: dict) -> None:
    self._write_result(request_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "ctx",
            "version": __version__,
        },
    })
```

### 3.4 Tool Definitions

```python
TOOL_DEFINITIONS = [
    {
        "name": "ctx_refresh",
        "description": "Generate or update CONTEXT.md manifests for a directory tree. Analyzes source files using an LLM and produces structured summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to refresh. Relative to server root.",
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
        "description": "Check manifest health, coverage, freshness, and validity across a directory tree. Returns status of each directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to check. Relative to server root.",
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
        "description": "Export CONTEXT.md manifests as concatenated text. Returns all manifests in a single string for context loading.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to export from. Relative to server root.",
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
                    "description": "Directory path to reset. Relative to server root.",
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
```

### 3.5 Tool Call Dispatcher

```python
def _handle_tools_call(self, request_id: Any, params: dict) -> None:
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    try:
        if tool_name == "ctx_refresh":
            result = self._call_refresh(arguments)
        elif tool_name == "ctx_check":
            result = self._call_check(arguments)
        elif tool_name == "ctx_export":
            result = self._call_export(arguments)
        elif tool_name == "ctx_reset":
            result = self._call_reset(arguments)
        else:
            self._write_error(request_id, -32602, f"Unknown tool: {tool_name}")
            return

        self._write_result(request_id, {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        })
    except Exception as exc:
        self._write_error(request_id, -32603, str(exc))
```

### 3.6 Tool Implementations

Each method resolves the path relative to `self._root` and calls the corresponding `api.*` function:

```python
def _call_refresh(self, args: dict) -> dict:
    path = self._resolve_path(args.get("path", "."))
    result = api.refresh(
        path,
        force=args.get("force", False),
        dry_run=args.get("dry_run", False),
    )
    return asdict(result)

def _call_check(self, args: dict) -> dict:
    path = self._resolve_path(args.get("path", "."))
    result = api.check(
        path,
        verify=args.get("verify", False),
        stats=args.get("stats", False),
        diff=args.get("diff", False),
    )
    return asdict(result)

def _call_export(self, args: dict) -> dict:
    path = self._resolve_path(args.get("path", "."))
    result = api.export_context(
        path,
        filter_mode=args.get("filter", "all"),
        depth=args.get("depth"),
    )
    return asdict(result)

def _call_reset(self, args: dict) -> dict:
    path = self._resolve_path(args.get("path", "."))
    result = api.reset(
        path,
        dry_run=args.get("dry_run", False),
        yes=True,  # MCP calls are always non-interactive
    )
    return asdict(result)

def _resolve_path(self, relative: str) -> Path:
    """Resolve a path relative to the server root, with traversal protection."""
    resolved = (self._root / relative).resolve()
    if not resolved.is_relative_to(self._root):
        raise ValueError(f"Path traversal denied: {relative}")
    return resolved
```

---

## 4. CLI Integration: `ctx serve --mcp`

### 4.1 Updated `serve` Command

```python
@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--host", default="127.0.0.1", help="Host address (HTTP mode only).")
@click.option("--port", type=int, default=8000, help="Port (HTTP mode only).")
@click.option("--mcp", is_flag=True, help="Launch stdio MCP server instead of HTTP.")
def serve(path: str, host: str, port: int, mcp: bool) -> None:
    """Start the ctx server.

    Default: HTTP server (FastAPI). With --mcp: stdio MCP server.
    """
    root = Path(path).resolve()
    if mcp:
        from ctx.mcp_server import CtxMCPServer
        server = CtxMCPServer(root)
        server.run()
    else:
        from ctx.server import start_server
        click.echo(f"Starting ctx HTTP server on http://{host}:{port}")
        click.echo(f"Serving manifests from: {root}")
        start_server(host=host, port=port, root=root)
```

### 4.2 `--mcp` as New Default (Future)

In 1.0.0, `--mcp` becomes the default and `--http` is the explicit flag for FastAPI. For now (0.8.x), HTTP is the default to avoid breaking existing users.

---

## 5. MCP Manifest: `mcp.json`

Create at repo root:

```json
{
  "mcpServers": {
    "ctx": {
      "command": "ctx",
      "args": ["serve", "--mcp"],
      "description": "Filesystem-native context layer — generates and manages CONTEXT.md manifests for AI agent navigation."
    }
  }
}
```

---

## 6. IDE Configuration Examples

### 6.1 Claude Code (`.mcp.json` in project root)

```json
{
  "mcpServers": {
    "ctx": {
      "command": "ctx",
      "args": ["serve", "--mcp"]
    }
  }
}
```

### 6.2 Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "ctx": {
      "command": "ctx",
      "args": ["serve", "--mcp"],
      "env": {}
    }
  }
}
```

### 6.3 Windsurf (`.windsurf/mcp.json`)

```json
{
  "mcpServers": {
    "ctx": {
      "command": "ctx",
      "args": ["serve", "--mcp"]
    }
  }
}
```

---

## 7. FastAPI as Optional Dependency

### 7.1 `pyproject.toml` Changes

Move `fastapi` and `uvicorn` from core dependencies to an optional group:

```toml
[project]
dependencies = [
    "click>=8.1",
    "anthropic>=0.40",
    "openai>=1.50",
    "pyyaml>=6.0",
    "pathspec>=0.12",
    "watchdog>=4.0",
    "tiktoken>=0.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
]
serve = [
    "fastapi>=0.110.0",
    "uvicorn>=0.29.0",
]
```

### 7.2 Lazy Import in `serve` Command

The HTTP path already uses a lazy import (`from ctx.server import start_server` inside the function). The MCP path also uses a lazy import. Neither crashes if the dependency is missing — the `ImportError` is caught at the function call level:

```python
if not mcp:
    try:
        from ctx.server import start_server
    except ImportError:
        raise click.UsageError(
            "HTTP server requires FastAPI. Install with: pip install ctx-tool[serve]"
        )
    start_server(host=host, port=port, root=root)
```

### 7.3 MCP Server Has Zero Extra Dependencies

`mcp_server.py` uses only:
- `json` (stdlib)
- `sys` (stdlib)
- `pathlib` (stdlib)
- `ctx.api` (local)
- `ctx.__version__` (local)

No new dependencies required for MCP functionality.

---

## 8. Stdout Isolation

The MCP server uses stdout for JSON-RPC communication. The API functions must not write to stdout. This is already guaranteed by the API layer design (see 02-unified-api.md: "The API layer has zero dependency on Click. It never prints.").

However, during `refresh` operations, the generator may log warnings via `logging`. Ensure logging is configured to write to **stderr** (or suppressed) when the MCP server is running:

```python
def run(self) -> None:
    # Redirect logging to stderr so it doesn't corrupt JSON-RPC on stdout
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    # ... main loop ...
```

---

## 9. Files

### New

| File | Description |
|------|-------------|
| `src/ctx/mcp_server.py` | `CtxMCPServer` class with JSON-RPC 2.0 handler |
| `mcp.json` | MCP manifest at repo root |
| `tests/test_mcp_server.py` | MCP server tests |

### Modified

| File | Changes |
|------|---------|
| `src/ctx/cli.py` | Add `--mcp` flag to `serve` command |
| `pyproject.toml` | Move `fastapi`/`uvicorn` to `[serve]` optional deps |

---

## 10. Test Cases for `test_mcp_server.py`

### Protocol Tests

1. **Initialize handshake**: Send `initialize` → response includes `serverInfo.name = "ctx"`.
2. **Tools list**: Send `tools/list` → response includes all 4 tool definitions.
3. **Tool names**: Tool names are `ctx_refresh`, `ctx_check`, `ctx_export`, `ctx_reset`.
4. **Unknown method**: Send unknown method → error code -32601.
5. **Invalid JSON**: Send malformed JSON → error code -32700.
6. **Shutdown**: Send `shutdown` → server exits cleanly.

### Tool Call Tests

7. **ctx_check — basic**: Call `ctx_check` with mock directory → returns health data.
8. **ctx_check — verify**: Call with `verify: true` → returns verify-mode data.
9. **ctx_export — basic**: Call `ctx_export` → returns manifest content.
10. **ctx_reset — dry_run**: Call with `dry_run: true` → lists files without deleting.
11. **ctx_refresh — dry_run**: Call with `dry_run: true` → returns stale dirs.

### Security Tests

12. **Path traversal blocked**: `path: "../../etc"` → error response.
13. **Absolute path rejected**: `path: "/etc/passwd"` → resolved within root.

### Integration Test Pattern

Use `subprocess.Popen` to launch `ctx serve --mcp`, write JSON-RPC to stdin, read from stdout:

```python
import subprocess, json

proc = subprocess.Popen(
    ["ctx", "serve", "--mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=str(tmp_path),
)
# Send initialize
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
proc.stdin.flush()
# Read response
response = json.loads(proc.stdout.readline())
assert response["result"]["serverInfo"]["name"] == "ctx"
```
