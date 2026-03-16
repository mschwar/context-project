"""Phase 20.2: Agent handoff tests — ctx export and ctx serve as context sources.

Validates that exported context helps an agent navigate the target repo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from click.testing import CliRunner


def test_export_depth_1_provides_top_level_context(tmp_path) -> None:
    """ctx export --depth 1 should provide enough context for agent navigation."""
    from ctx.cli import cli
    from ctx.manifest import write_manifest
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    
    runner = CliRunner()
    
    # Create a realistic project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    
    # Create source files
    (tmp_path / "src" / "main.py").write_text("def main(): pass")
    (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass")
    (tmp_path / "docs" / "readme.md").write_text("# Project")
    
    spec = load_ignore_patterns(tmp_path)
    
    # Create manifests at different depths
    for d in [tmp_path, tmp_path / "src", tmp_path / "tests", tmp_path / "docs"]:
        content_hash = hash_directory(d, spec, tmp_path)
        write_manifest(
            d,
            model="test",
            content_hash=content_hash,
            files=1 if d != tmp_path else 0,
            dirs=0 if d != tmp_path else 3,
            tokens_total=100,
            body=f"# {d.name or 'root'}\n\nThis is the {d.name or 'root'} directory.\n"
        )
    
    # Test export --depth 0 (root only)
    result = runner.invoke(cli, ["export", str(tmp_path), "--depth", "0"])
    assert result.exit_code == 0
    assert "# CONTEXT.md" in result.output
    assert "# src/CONTEXT.md" not in result.output
    
    # Test export --depth 1 (root + immediate children)
    result = runner.invoke(cli, ["export", str(tmp_path), "--depth", "1"])
    assert result.exit_code == 0
    assert "# CONTEXT.md" in result.output
    assert "# src/CONTEXT.md" in result.output
    assert "# tests/CONTEXT.md" in result.output
    assert "# docs/CONTEXT.md" in result.output


def test_export_structure_for_agent_consumption(tmp_path) -> None:
    """Exported context should have clear structure for agents to parse."""
    from ctx.cli import cli
    from ctx.manifest import write_manifest
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    
    runner = CliRunner()
    
    # Create a well-documented project
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core").mkdir()
    
    (tmp_path / "src" / "main.py").write_text("def main(): pass")
    (tmp_path / "src" / "core" / "utils.py").write_text("def helper(): pass")
    
    spec = load_ignore_patterns(tmp_path)
    
    # Write meaningful manifests
    write_manifest(
        tmp_path,
        model="test",
        content_hash=hash_directory(tmp_path, spec, tmp_path),
        files=0,
        dirs=1,
        tokens_total=50,
        body="# Project Root\n\nEntry point for the application.\n\n## Structure\n- src/: Source code\n"
    )
    
    write_manifest(
        tmp_path / "src",
        model="test",
        content_hash=hash_directory(tmp_path / "src", spec, tmp_path),
        files=1,
        dirs=1,
        tokens_total=100,
        body="# src/\n\nSource code directory containing main application logic.\n\n## Files\n- main.py: Entry point\n\n## Subdirectories\n- core/: Core utilities\n"
    )
    
    result = runner.invoke(cli, ["export", str(tmp_path), "--depth", "2"])
    assert result.exit_code == 0
    
    # Verify the structure is clear
    output = result.output
    
    # Each manifest should be clearly delimited
    assert "# CONTEXT.md" in output
    assert "# src/CONTEXT.md" in output
    
    # Headers should be present for agent parsing
    assert "# Project Root" in output
    assert "# src/" in output
    
    # Structure information should be present
    assert "src/: Source code" in output
    assert "main.py" in output


def test_serve_provides_manifest_access(tmp_path) -> None:
    """ctx serve should expose manifests in a format agents can consume."""
    from ctx.manifest import write_manifest
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    
    # Create test manifests
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    
    spec = load_ignore_patterns(tmp_path)
    content_hash = hash_directory(tmp_path, spec, tmp_path)
    
    write_manifest(
        tmp_path,
        model="test-model",
        content_hash=content_hash,
        files=1,
        dirs=1,
        tokens_total=100,
        body="# Test Project\n\nA test project for agent handoff.\n"
    )
    
    # Test server endpoint
    from ctx.server import get_mcp_context
    from fastapi.testclient import TestClient
    from ctx.server import app
    
    client = TestClient(app)
    # Set the served_root state
    app.state.served_root = tmp_path
    
    # Get manifest via API - use relative path
    response = client.get("/mcp/context/.")
    assert response.status_code == 200
    
    data = response.json()
    assert "content" in data
    assert "# Test Project" in data["content"]
    assert "test-model" in data["content"]


def test_export_filter_stale_for_agent_prioritization(tmp_path) -> None:
    """Agents can use --filter stale to focus on directories needing attention."""
    from ctx.cli import cli
    from ctx.manifest import write_manifest
    import time
    
    runner = CliRunner()
    
    # Create structure with mixed freshness
    (tmp_path / "fresh").mkdir()
    (tmp_path / "stale").mkdir()
    
    # Fresh manifest (correct hash)
    (tmp_path / "fresh" / "file.py").write_text("x = 1")
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    spec = load_ignore_patterns(tmp_path)
    fresh_hash = hash_directory(tmp_path / "fresh", spec, tmp_path)
    write_manifest(
        tmp_path / "fresh",
        model="test",
        content_hash=fresh_hash,
        files=1,
        dirs=0,
        tokens_total=50,
        body="# Fresh\n\nThis is fresh."
    )
    
    # Stale manifest - create it first, then modify the file to make it stale
    (tmp_path / "stale" / "file.py").write_text("y = 1")
    stale_hash = hash_directory(tmp_path / "stale", spec, tmp_path)
    write_manifest(
        tmp_path / "stale",
        model="test",
        content_hash=stale_hash,
        files=1,
        dirs=0,
        tokens_total=50,
        body="# Stale\n\nThis is stale."
    )
    
    # Wait a bit, then modify the file to make the manifest stale
    time.sleep(0.1)
    (tmp_path / "stale" / "file.py").write_text("y = 2 - modified")
    
    # Root manifest
    write_manifest(
        tmp_path,
        model="test",
        content_hash="root_hash",
        files=0,
        dirs=2,
        tokens_total=100,
        body="# Root\n\nRoot directory."
    )
    
    # Export all
    result = runner.invoke(cli, ["export", str(tmp_path)])
    assert result.exit_code == 0
    all_output = result.output
    assert "# fresh/CONTEXT.md" in all_output
    assert "# stale/CONTEXT.md" in all_output
    
    # Export only stale
    result = runner.invoke(cli, ["export", str(tmp_path), "--filter", "stale"])
    assert result.exit_code == 0
    stale_output = result.output
    
    # Stale should only contain the stale directory
    assert "# stale/CONTEXT.md" in stale_output
    assert "# fresh/CONTEXT.md" not in stale_output


def test_agent_navigation_workflow(tmp_path) -> None:
    """End-to-end test of the agent navigation workflow."""
    from ctx.cli import cli
    from ctx.manifest import write_manifest
    from ctx.hasher import hash_directory
    from ctx.ignore import load_ignore_patterns
    
    runner = CliRunner()
    
    # Create a realistic project structure
    dirs = {
        "src": ["main.py", "utils.py"],
        "tests": ["test_main.py"],
        "docs": ["api.md", "setup.md"],
    }
    
    spec = load_ignore_patterns(tmp_path)
    
    for dir_name, files in dirs.items():
        d = tmp_path / dir_name
        d.mkdir()
        for f in files:
            (d / f).write_text(f"# {f}")
        
        # Write meaningful manifest
        content_hash = hash_directory(d, spec, tmp_path)
        write_manifest(
            d,
            model="claude-3-sonnet",
            content_hash=content_hash,
            files=len(files),
            dirs=0,
            tokens_total=100 * len(files),
            body=f"# {dir_name}/\n\nContains {', '.join(files)}.\n"
        )
    
    # Write root manifest
    write_manifest(
        tmp_path,
        model="claude-3-sonnet",
        content_hash=hash_directory(tmp_path, spec, tmp_path),
        files=0,
        dirs=len(dirs),
        tokens_total=sum(100 * len(files) for files in dirs.values()),
        body="# Project\n\n" + "\n".join(f"- {d}/: {', '.join(files)}" for d, files in dirs.items())
    )
    
    # Step 1: Agent uses export --depth 1 to understand top-level structure
    result = runner.invoke(cli, ["export", str(tmp_path), "--depth", "1"])
    assert result.exit_code == 0
    
    overview = result.output
    
    # Agent should be able to identify all top-level directories
    assert "src/" in overview
    assert "tests/" in overview
    assert "docs/" in overview
    
    # Step 2: Agent can then request deeper export for specific directories
    result = runner.invoke(cli, ["export", str(tmp_path / "src")])
    assert result.exit_code == 0
    
    src_detail = result.output
    assert "main.py" in src_detail or "utils.py" in src_detail


def test_serve_endpoints_for_agent_api(tmp_path) -> None:
    """Test that serve endpoints return agent-friendly formats."""
    from ctx.server import app
    from fastapi.testclient import TestClient
    from ctx.manifest import write_manifest
    
    client = TestClient(app)
    # Set the served_root state
    app.state.served_root = tmp_path
    
    # Create root manifest
    write_manifest(
        tmp_path,
        model="test",
        content_hash="test_hash",
        files=0,
        dirs=0,
        tokens_total=0,
        body="# Root\n\nRoot directory."
    )
    
    # Root endpoint
    response = client.get("/")
    assert response.status_code == 200
    assert "ctx MCP Server" in response.json()["message"]
    
    # Test error handling
    response = client.get("/mcp/context/nonexistent")
    assert response.status_code == 404
