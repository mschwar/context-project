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


def test_skeleton_filters_stdlib_resolves_multilang_imports_and_cleans_entrypoints(tmp_path: Path) -> None:
    """Verify stdlib filtering, 11-lang imports, go.mod internal roots, clean entrypoints, and doc summaries."""
    repo = tmp_path / "polyglot"
    repo.mkdir()
    (repo / "AGENTS.md").write_text(
        "# AGENTS\n\n## schema_version\n1\n\n## Purpose\nPolyglot architectural contract.\n",
        encoding="utf-8",
    )
    # Nonexistent main -> index.js must NOT appear in entrypoints
    (repo / "package.json").write_text('{"name": "poly", "main": "nonexistent.js"}', encoding="utf-8")
    (repo / "go.mod").write_text("module github.com/acme/poly\n\ngo 1.22\n", encoding="utf-8")

    # Python with stdlib + third-party
    py_dir = repo / "src" / "poly"
    py_dir.mkdir(parents=True)
    (py_dir / "aaa.py").write_text(
        "from __future__ import annotations\nimport ast\nimport sys\nimport openai\n\nclass AlphaOne:\n    pass\n\nclass AlphaTwo:\n    pass\n",
        encoding="utf-8",
    )
    (py_dir / "cli.py").write_text(
        "import click\nfrom poly.aaa import AlphaOne\n\ndef run_cli() -> None:\n    pass\n",
        encoding="utf-8",
    )

    # Go with stdlib + internal + external
    go_dir = repo / "cmd"
    go_dir.mkdir()
    (go_dir / "main.go").write_text(
        'package main\n\nimport (\n\t"fmt"\n\t"net/http"\n\t"github.com/acme/poly/internal/core"\n\t"github.com/spf13/cobra"\n)\n\nfunc main() {}\n',
        encoding="utf-8",
    )

    # Additional languages (Java, Ruby, Elixir) + fixture entrypoint that must be excluded
    extra_dir = repo / "services"
    extra_dir.mkdir()
    (extra_dir / "App.java").write_text(
        "import java.util.List;\nimport com.google.gson.Gson;\npublic class App {}\n",
        encoding="utf-8",
    )
    (extra_dir / "worker.rb").write_text(
        "require 'sidekiq'\nclass Worker\nend\n",
        encoding="utf-8",
    )
    (extra_dir / "pipeline.ex").write_text(
        "defmodule Pipeline do\n  use Broadway\nend\n",
        encoding="utf-8",
    )

    fixture_dir = repo / "tests" / "fixtures" / "demo"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "main.py").write_text("def demo() -> None:\n    pass\n", encoding="utf-8")

    sk = extract_skeleton(repo)

    # 1. Authority doc skips bare '1' under schema_version
    agents_doc = next(d for d in sk.boundary_docs if d.relative_path == "AGENTS.md")
    assert agents_doc.summary_line == "Polyglot architectural contract."

    # 2. Entrypoints exclude nonexistent npm:main and tests/fixtures/*/main.py
    assert not any("nonexistent.js" in ep for ep in sk.entrypoints)
    assert not any("tests/fixtures" in ep for ep in sk.entrypoints)
    assert "file:src/poly/cli.py" in sk.entrypoints
    assert "file:cmd/main.go" in sk.entrypoints

    # 3. Python subsystem filters stdlib (ast, sys, __future__) and keeps click & openai, with diversified symbols
    subs = {s.path: s for s in sk.subsystems}
    py_sub = subs["src/poly"]
    assert set(py_sub.external_deps) == {"click", "openai"}
    assert "poly.aaa" in py_sub.internal_deps
    assert py_sub.key_symbols[0] == "cli.py:fn run_cli"
    assert "aaa.py:class AlphaOne" in py_sub.key_symbols[:2]

    # 4. Go subsystem filters fmt & net/http, classifies github.com/acme/poly/* as internal, keeps cobra external
    go_sub = subs["cmd"]
    assert go_sub.internal_deps == ["github.com/acme/poly/internal/core"]
    assert go_sub.external_deps == ["github.com/spf13/cobra"]

    # 5. Additional language imports parsed and java.* filtered
    svc_sub = subs["services"]
    assert "com" in svc_sub.external_deps
    assert "sidekiq" in svc_sub.external_deps
    assert "Broadway" in svc_sub.external_deps
    assert "java" not in svc_sub.external_deps


def test_fleet_capsule_honors_depth_in_markdown_and_subsystems(tmp_path: Path) -> None:
    """build_fleet_capsule must filter capsule_markdown subsystems to match requested depth."""
    from ctx.api import build_fleet_capsule
    from ctx.skeleton import strip_tier2_chrome

    repo = _create_sample_repo(tmp_path / "capsule_repo")
    deep_dir = repo / "src" / "sample" / "nested_sub"
    deep_dir.mkdir(parents=True)
    (deep_dir / "deep_mod.py").write_text("class DeepSymbol:\n    pass\n", encoding="utf-8")

    cap_d1 = build_fleet_capsule(repo, depth=1)
    d1_paths = {s["path"] for s in cap_d1.subsystems}
    assert "src/sample/nested_sub" not in d1_paths
    assert "src/sample/nested_sub" not in cap_d1.capsule_markdown

    cap_d0 = build_fleet_capsule(repo, depth=0)
    assert "## Cross-Directory Dependency & Export Map" not in cap_d0.capsule_markdown

    # Verify delimiter-based strip_tier2_chrome handles arbitrary frontmatter length
    sample_md = "---\na: 1\nb: 2\nc: 3\n---\n\n# Heading\nBody\n<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->\n"
    assert strip_tier2_chrome(sample_md) == "# Heading\nBody"


def test_deterministic_subsystem_arch_role_segment_classification() -> None:
    """_rule_subsystem_arch_role classifies segment tokens accurately without substring false positives."""
    from ctx.skeleton import _classify_subsystem_arch_role

    assert _classify_subsystem_arch_role("tests/unit", 1, ["Python"], [], [], [], []) == "verification_tooling"
    assert _classify_subsystem_arch_role("docs/adr", 1, ["Markdown"], [], [], [], []) == "docs_governance"
    assert _classify_subsystem_arch_role("src/cli", 1, ["Python"], ["fn main"], [], ["click"], ["cli_command"]) == "entrypoint_interface"
    # Segment-level checks prevent "api_client", "query_builder", and "digit_parser" false positives
    assert _classify_subsystem_arch_role("src/api_client", 1, ["Python"], ["class Client"], [], ["httpx"], []) == "adapter_integration"
    assert _classify_subsystem_arch_role("src/query_builder", 1, ["Python"], ["class QueryBuilder"], [], [], []) == "core_domain"
    assert _classify_subsystem_arch_role("src/digit_parser", 1, ["Python"], ["fn parse_digits"], [], [], []) == "core_domain"

