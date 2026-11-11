"""Documentation and package metadata checks for zero-LLM deterministic ctx."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agents_contract_sections_and_examples() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    heading_text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    sections = re.findall(r"^## (.+)$", heading_text, flags=re.MULTILINE)
    assert sections == [
        "schema_version",
        "What ctx Is",
        "Install",
        "Configure",
        "Commands",
        "Exit Codes",
        "Error Codes",
        "Integration Patterns",
        "Manifest Format",
        "Security",
    ]
    assert re.search(r"^## schema_version\s+1\s*$", text, flags=re.MULTILINE)

    json_blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert len(json_blocks) >= 5
    for block in json_blocks:
        json.loads(block)
    assert any('"mcpServers"' in block for block in json_blocks)

    for uri in (
        "ctx://.ctx/CONTEXT.md",
        "ctx://.ctx/CONTEXT-1.md",
        "ctx://.ctx/CONTEXT-0.md",
        "ctx://.ctx/metadata.json",
    ):
        assert f"`{uri}`" in text

    for retired in ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ctx jev", "ctx_jev"):
        assert retired not in text


def test_readme_references_agents_and_quickstart() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 100
    assert "[AGENTS.md](./AGENTS.md)" in text
    assert "pip install ctx-tool" in text
    assert "ctx init ." in text
    assert "ctx impact" in text
    for retired in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ctx jev"):
        assert retired not in text


def test_pyproject_and_repo_tree_are_zero_llm_and_hook_free() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert len(deps) == 3
    for pkg in ("click", "pyyaml", "pathspec"):
        assert any(d.startswith(pkg) for d in deps)

    assert not (REPO_ROOT / "src" / "ctx" / "jev.py").exists()
    assert not (REPO_ROOT / "src" / "ctx" / "llm.py").exists()
    assert not (REPO_ROOT / "src" / "ctx" / "generator.py").exists()
    assert not (REPO_ROOT / "heads").exists()
    assert not (REPO_ROOT / ".machina").exists()
    assert not (REPO_ROOT / ".husky").exists()
    assert not (REPO_ROOT / "package.json").exists()
    assert list(REPO_ROOT.rglob("CONTEXT.md")) == []
