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

@app.get("/mcp/context/{file_path:path}")
async def get_mcp_context(file_path: str, request: Request):
    # Ensure the path is relative to the served root and not a directory traversal attempt.
    try:
        project_root = request.app.state.served_root
        # Resolve the path safely, ensuring it's within the project root
        full_path = (project_root / file_path).resolve(strict=True)

        # Security: Check that the resolved path is still within the project root.
        if not full_path.is_relative_to(project_root):
            raise HTTPException(status_code=403, detail="Access denied: path is outside the project root.")

    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Invalid or non-existent path.")

    if not full_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Path '{file_path}' is not a directory.")

    manifest = read_manifest(full_path)
    if manifest:
        return {"content": (full_path / "CONTEXT.md").read_text(encoding="utf-8")}
    else:
        raise HTTPException(status_code=404, detail=f"CONTEXT.md not found in '{file_path}'")

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
