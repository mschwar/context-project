from pathlib import Path

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request
except ImportError as exc:
    raise ImportError(
        "HTTP server requires FastAPI. Install with: pip install ctx-tool[serve]"
    ) from exc

from ctx.manifest import read_manifest

app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "ctx HTTP server is running"}

def _resolve_and_read_context(file_path: str, request: Request) -> dict[str, str]:
    """Resolve *file_path* within served_root and return its CONTEXT.md payload.

    Implementation:
        1. Resolve path strictly inside ``request.app.state.served_root``.
        2. Reject paths outside root (403) and internal ``.ctx`` paths (404).
        3. Serve directory ``CONTEXT.md`` when valid, or Tier 2 ``.ctx/CONTEXT.md`` at root.
    """
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
        raise HTTPException(status_code=404, detail=f"CONTEXT.md not found in '{file_path}'")

    if not full_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Path '{file_path}' is not a directory.")

    manifest = read_manifest(full_path)
    if manifest:
        return {"content": (full_path / "CONTEXT.md").read_text(encoding="utf-8")}

    tier2_export = project_root / ".ctx" / "CONTEXT.md"
    if full_path == project_root and tier2_export.is_file():
        return {"content": tier2_export.read_text(encoding="utf-8")}

    raise HTTPException(status_code=404, detail=f"CONTEXT.md not found in '{file_path}'")


@app.get("/mcp/context")
async def get_mcp_root_context(request: Request):
    return _resolve_and_read_context(".", request)


@app.get("/mcp/context/{file_path:path}")
async def get_mcp_context(file_path: str, request: Request):
    return _resolve_and_read_context(file_path, request)

def start_server(host: str = "127.0.0.1", port: int = 8000, root: Path | None = None):
    """Start the HTTP manifest server.
    
    Args:
        host: Host address to bind to.
        port: Port number to bind to.
        root: Root directory for serving manifests. If None, uses current working directory.
    """
    app.state.served_root = root.resolve() if root is not None else Path.cwd().resolve()
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()
