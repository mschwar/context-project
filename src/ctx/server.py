from fastapi import FastAPI, HTTPException
import uvicorn
from pathlib import Path
from dataclasses import asdict
import yaml

from ctx.manifest import read_manifest, Manifest, ManifestFrontmatter # Import Manifest and ManifestFrontmatter for reconstruction

app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "ctx MCP Server is running"}

@app.get("/mcp/context/{file_path:path}")
async def get_mcp_context(file_path: str):
    # Ensure the path is relative to the current working directory and not a directory traversal attempt.
    try:
        project_root = Path.cwd().resolve()
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
        # Reconstruct the original markdown content from the Manifest object
        yaml_frontmatter = yaml.safe_dump(asdict(manifest.frontmatter), sort_keys=False, default_flow_style=False)
        full_content = f"""---
{yaml_frontmatter}---
{manifest.body}"""
        return {"content": full_content}
    else:
        raise HTTPException(status_code=404, detail=f"CONTEXT.md not found in '{file_path}'")

def start_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()
