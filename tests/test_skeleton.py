"""Unit tests for ctx.skeleton (Deterministic Structural Skeleton & Invariant Maps)."""

from __future__ import annotations

from pathlib import Path

from ctx.skeleton import (
    extract_skeleton,
    render_context_0,
    render_context_1,
    render_context_full,
    should_invoke_llm,
)


def _create_sample_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample"\n\n[project.scripts]\nsample-cli = "sample.cli:main"\n',
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text(
        "# AGENTS\n\nRepo governance contract.\n\n## Authority\n\n## Invariants\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Sample Repo\n\nHigh-signal structural mapper.\n",
        encoding="utf-8",
    )
    adr_dir = root / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / "001-tier2.md").write_text(
        "# ADR 001: Tier 2 Synthesis\n\nPrefer deterministic structural maps.\n",
        encoding="utf-8",
    )
    pkg_dir = root / "src" / "sample"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "cli.py").write_text(
        "import click\nfrom sample.engine import Engine\n\ndef main() -> None:\n    pass\n\ndef _private_helper() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (pkg_dir / "engine.py").write_text(
        "import json\n\nclass Engine:\n    def run(self) -> int:\n        return 1\n",
        encoding="utf-8",
    )
    web_dir = root / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.ts").write_text(
        'import { render } from "./ui";\nexport interface AppConfig { debug: boolean; }\nexport function startApp(): void {}\n',
        encoding="utf-8",
    )
    return root


def test_extract_skeleton_collects_symbols_imports_entrypoints_and_boundaries(tmp_path: Path) -> None:
    repo = _create_sample_repo(tmp_path / "sample")

    sk = extract_skeleton(repo)

    assert sk.repo_name == "sample"
    assert sk.total_files == 7
    assert sk.languages["Python"] == 2
    assert sk.languages["TypeScript"] == 1
    assert "cli:sample-cli -> sample.cli:main" in sk.entrypoints
    assert "file:src/sample/cli.py" in sk.entrypoints
    assert "file:web/index.ts" in sk.entrypoints

    bdoc_paths = {d.relative_path: d for d in sk.boundary_docs}
    assert "AGENTS.md" in bdoc_paths
    assert bdoc_paths["AGENTS.md"].kind == "authority"
    assert "Authority" in bdoc_paths["AGENTS.md"].headings
    assert "docs/adr/001-tier2.md" in bdoc_paths
    assert bdoc_paths["docs/adr/001-tier2.md"].kind == "architecture"

    files_by_path = {f.relative_path: f for f in sk.files}
    assert files_by_path["src/sample/cli.py"].symbols == ["fn main"]
    assert "click" in files_by_path["src/sample/cli.py"].imports
    assert "sample.engine" in files_by_path["src/sample/cli.py"].imports
    assert files_by_path["src/sample/engine.py"].symbols == ["class Engine"]
    assert "interface AppConfig" in files_by_path["web/index.ts"].symbols
    assert "fn startApp" in files_by_path["web/index.ts"].symbols


def test_structural_hash_ignores_body_edits_and_detects_signature_changes(tmp_path: Path) -> None:
    repo = _create_sample_repo(tmp_path / "sample")
    sk1 = extract_skeleton(repo)

    # Modify internal implementation & comments in engine.py without changing public signature or imports
    (repo / "src" / "sample" / "engine.py").write_text(
        "import json\n\n# Refactored implementation comment\nclass Engine:\n    def run(self) -> int:\n        data = json.dumps({'ok': True})\n        return len(data)\n",
        encoding="utf-8",
    )
    sk2 = extract_skeleton(repo)
    assert sk2.structural_hash == sk1.structural_hash
    assert sk2.boundary_doc_hash == sk1.boundary_doc_hash
    assert should_invoke_llm(
        {"structural_hash": sk1.structural_hash, "boundary_doc_hash": sk1.boundary_doc_hash},
        sk2,
    ) is False

    # Now add a new exported function
    (repo / "src" / "sample" / "engine.py").write_text(
        "import json\n\nclass Engine:\n    pass\n\ndef build_engine() -> Engine:\n    return Engine()\n",
        encoding="utf-8",
    )
    sk3 = extract_skeleton(repo)
    assert sk3.structural_hash != sk1.structural_hash
    assert should_invoke_llm(
        {"structural_hash": sk1.structural_hash, "boundary_doc_hash": sk1.boundary_doc_hash},
        sk3,
    ) is True


def test_boundary_doc_hash_detects_agents_md_updates(tmp_path: Path) -> None:
    repo = _create_sample_repo(tmp_path / "sample")
    sk1 = extract_skeleton(repo)

    (repo / "AGENTS.md").write_text(
        "# AGENTS\n\nUpdated governance rule.\n\n## Authority\n\n## Security\n",
        encoding="utf-8",
    )
    sk2 = extract_skeleton(repo)
    assert sk2.structural_hash == sk1.structural_hash
    assert sk2.boundary_doc_hash != sk1.boundary_doc_hash
    assert should_invoke_llm(
        {"structural_hash": sk1.structural_hash, "boundary_doc_hash": sk1.boundary_doc_hash},
        sk2,
    ) is True


def test_render_tiered_markdown_outputs(tmp_path: Path) -> None:
    repo = _create_sample_repo(tmp_path / "sample")
    sk = extract_skeleton(repo)

    c0 = render_context_0(sk, generated="2026-10-29T00:00:00Z")
    c1 = render_context_1(sk, generated="2026-10-29T00:00:00Z")
    cfull = render_context_full(sk, generated="2026-10-29T00:00:00Z")

    assert "mode: tier2" in c0
    assert "tier: CONTEXT-0" in c0
    assert "## Authority Boundaries & Governance" in c0
    assert "## Entrypoints & Operational Surfaces" in c0
    assert "## Subsystem Overview" in c0
    assert "AGENTS.md" in c0

    assert "tier: CONTEXT-1" in c1
    assert "## Cross-Directory Dependency & Export Map" in c1
    assert "## Architectural Invariants & Boundary Contracts" in c1
    assert "`src/sample`" in c1

    assert "## File-Level Structural Signatures" in cfull
    assert "**src/sample/engine.py**" in cfull
