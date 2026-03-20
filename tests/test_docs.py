"""Documentation and package metadata checks for the current roadmap state."""

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
        "Exit Codes",
        "Error Codes",
        "Integration Patterns",
        "Manifest Format",
        "Security",
    ]
    assert re.search(r"^## schema_version\s+1\s*$", text, flags=re.MULTILINE)

    json_blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert len(json_blocks) == 5
    for block in json_blocks:
        json.loads(block)
    assert any('"mcpServers"' in block for block in json_blocks)

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


def test_readme_references_agents_and_quickstart() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 100
    assert "[AGENTS.md](./AGENTS.md)" in text
    assert "pip install ctx-tool" in text
    assert "ctx refresh ." in text


def test_workflow_patterns_use_canonical_check_commands() -> None:
    pre_commit = (REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "ctx-check.yml").read_text(encoding="utf-8")
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "RUNBOOK.md").read_text(encoding="utf-8")

    assert "ctx check . --check-exit" in pre_commit
    assert "status . --check-exit-code" not in pre_commit

    assert "run: python -m ctx check . --check-exit" in workflow
    assert "CTX_OUTPUT: json" in workflow
    assert "status . --check-exit-code" not in workflow

    assert "### Session-End Manifest Refresh" in agents
    assert "### First 3 Commands" in agents
    assert "### Natural Language Triggers" in agents
    assert "CTX_OUTPUT=json python -m ctx check . --check-exit" in agents
    assert "`update ctx` / `update context` / `refresh manifests`" in agents
    assert '"local_batch_fallbacks": 0' in agents
    assert "validate frontmatter, body structure, freshness, and coverage" in agents

    assert "pre-commit hook and `CTX Manifest Check` CI job both use `ctx check . --check-exit`" in runbook
    assert "falls back cleanly to incremental refresh" in runbook
    assert "duplicate bullets, nonexistent files, missing real files" in runbook


def test_afo_closeout_artifact_and_phase24_scope_exist() -> None:
    reflection = (REPO_ROOT / "archive" / "reflections" / "2026-03-18-afo-stage1-6-reflection.md")
    state = (REPO_ROOT / "state.md").read_text(encoding="utf-8")
    overhaul = (REPO_ROOT / "AGENT_FIRST_OVERHAUL.md").read_text(encoding="utf-8")

    assert reflection.exists()
    reflection_text = reflection.read_text(encoding="utf-8")
    assert "Disposition Table" in reflection_text
    assert "Carry into Phase 24" in reflection_text

    assert "AFO Stage 1–6 Closeout ✓" in state
    assert "## Phase 24 — Manifest Trust & External Validation" in state
    assert "[x] **24.1 git-optional refresh**" in state
    assert "[x] **24.3 Body-level verification**" in state
    assert "local-provider fallback counts are surfaced" in state

    assert "## AFO Stage 1–6 Closeout" in overhaul
    assert "## Phase 24 — Manifest Trust & External Validation" in overhaul
    assert "[x] **24.6 local-provider adaptive batching**" in overhaul


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
