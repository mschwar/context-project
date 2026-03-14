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
    # Ensure the path is relative to the current working directory or project root
    # For simplicity, let's assume `file_path` is relative to the project root for now.
    # A more robust solution might involve validating `file_path` against known project paths.
    full_path = Path(file_path)

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
