"""Documentation and package metadata checks for Stage 4."""

from __future__ import annotations

import json
import re
from pathlib import Path


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
        "Error Codes",
        "Integration Patterns",
        "Manifest Format",
        "Security",
    ]
    assert re.search(r"^## schema_version\s+1\s*$", text, flags=re.MULTILINE)

    json_blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert len(json_blocks) == 4
    for block in json_blocks:
        json.loads(block)

    for code in [
        "provider_not_configured",
        "provider_unreachable",
        "auth_failed",
        "budget_exhausted",
        "lock_held",
        "partial_failure",
        "no_manifests",
        "stale_manifests",
        "invalid_manifests",
        "git_unavailable",
        "unknown_error",
    ]:
        assert f"`{code}`" in text


def test_readme_is_demoted_and_short() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 50
    assert "[AGENTS.md](./AGENTS.md)" in text
    assert "pip install ctx-tool" in text
    assert "ctx refresh ." in text


def test_pyproject_agent_metadata_present() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "generates CONTEXT.md manifests for codebase navigation" in text
    for keyword in ['"ai"', '"agent"', '"context"', '"codebase"', '"mcp"', '"manifest"', '"llm"', '"documentation"']:
        assert keyword in text
    for classifier in [
        '"Environment :: Console"',
        '"Topic :: Software Development :: Documentation"',
        '"Typing :: Typed"',
    ]:
        assert classifier in text
