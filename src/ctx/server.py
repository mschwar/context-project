"""Optional FastAPI HTTP server for serving .ctx/ architectural context."""

from __future__ import annotations

from pathlib import Path

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request
except ImportError as exc:
    raise ImportError(
        "HTTP server requires FastAPI. Install with: pip install ctx-tool[serve]"
    ) from exc

app = FastAPI()


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": "ctx HTTP server is running"}


def _resolve_and_read_context(file_path: str, request: Request) -> dict[str, str]:
    """Resolve *file_path* within served_root and return its .ctx/ architectural context."""
    try:
        project_root = request.app.state.served_root
        rel_target = file_path or "."
        full_path = (project_root / rel_target).resolve(strict=True)

        if not full_path.is_relative_to(project_root):
            raise HTTPException(status_code=403, detail="Access denied: path is outside the project root.")
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Invalid or non-existent path.")

    rel_parts = full_path.relative_to(project_root).parts
    if ".ctx" in rel_parts or ".ctx-cache" in rel_parts:
        raise HTTPException(status_code=404, detail=f"Context map not found in '{file_path}'")

    if not full_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Path '{file_path}' is not a directory.")

    ctx_export = full_path / ".ctx" / "CONTEXT.md"
    if ctx_export.is_file():
        return {"content": ctx_export.read_text(encoding="utf-8")}

    raise HTTPException(status_code=404, detail=f"Context map not found in '{file_path}'")


@app.get("/mcp/context")
async def get_mcp_root_context(request: Request) -> dict[str, str]:
    return _resolve_and_read_context(".", request)


@app.get("/mcp/context/{file_path:path}")
async def get_mcp_context(file_path: str, request: Request) -> dict[str, str]:
    return _resolve_and_read_context(file_path, request)


def start_server(host: str = "127.0.0.1", port: int = 8000, root: Path | None = None) -> None:
    """Start the HTTP context server."""
    app.state.served_root = root.resolve() if root is not None else Path.cwd().resolve()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
