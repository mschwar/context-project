"""Regression tests for ctx v2.0.0 (Waves A–D):
- Wave A: .ctxconfig max_depth / CTX_MAX_DEPTH end-to-end wiring, cross-host repo_id, archive doc exclusion
- Wave B: AST + inbound-hub symbol ranking, .ctx/capsule.json atomic persistence
- Wave C: ctx impact --git-diff and --staged proportional verification compiler (API, CLI, MCP)
- Wave D: 13-language C/C++ parser + #include graph, Python/TS/Rust monorepo workspace resolution
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

from ctx import api
from ctx.cli import cli
from ctx.impact import analyze_diff_impact, analyze_impact
from ctx.init import compute_repo_id, normalize_git_remote_url
from ctx.lang_parsers.c_cpp_parser import parse_c_cpp_file
from ctx.mcp_server import CtxMCPServer
from ctx.skeleton import extract_skeleton


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test Bot",
        "GIT_AUTHOR_EMAIL": "bot@example.com",
        "GIT_COMMITTER_NAME": "Test Bot",
        "GIT_COMMITTER_EMAIL": "bot@example.com",
    }
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return proc


def _init_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init")
    return root


# ── Wave A: .ctxconfig max_depth & CTX_MAX_DEPTH wiring ─────────────────────


def test_ctxconfig_and_env_max_depth_apply_across_skeleton_export_and_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_git_repo(tmp_path / "depth_repo")
    (repo / "top.py").write_text("def top_fn() -> int:\n    return 1\n", encoding="utf-8")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "mid.py").write_text("def mid_fn() -> int:\n    return 2\n", encoding="utf-8")
    (repo / "pkg" / "sub" / "leaf").mkdir(parents=True)
    (repo / "pkg" / "sub" / "leaf" / "deep.py").write_text(
        "def deep_fn() -> int:\n    return 3\n",
        encoding="utf-8",
    )
    (repo / ".ctxconfig").write_text("max_depth: 1\n", encoding="utf-8")

    sk = extract_skeleton(repo)
    rels = {f.relative_path for f in sk.files}
    assert "top.py" in rels
    assert "pkg/mid.py" in rels
    assert "pkg/sub/leaf/deep.py" not in rels

    exported = api.export_context(repo)
    assert "mid_fn" in exported.content
    assert "deep_fn" not in exported.content

    api.init_project(repo)
    refreshed = api.refresh(repo, force=True)
    assert refreshed.files_processed == len(sk.files)
    assert "deep_fn" not in (repo / ".ctx" / "CONTEXT.md").read_text(encoding="utf-8")

    # Explicit max_depth argument overrides .ctxconfig max_depth: 1
    sk_override = extract_skeleton(repo, max_depth=4)
    assert "pkg/sub/leaf/deep.py" in {f.relative_path for f in sk_override.files}

    # CTX_MAX_DEPTH env var overrides .ctxconfig
    monkeypatch.setenv("CTX_MAX_DEPTH", "0")
    sk_env = extract_skeleton(repo)
    assert {f.relative_path for f in sk_env.files} == {"top.py"}


# ── Wave A: Cross-host canonical repo_id ────────────────────────────────────


def test_normalize_git_remote_url_canonicalizes_ssh_https_and_tokens() -> None:
    expected = "github.com/mschwar/context-project"
    variants = [
        "git@github.com:mschwar/context-project.git",
        "git@GitHub.COM:mschwar/context-project",
        "https://github.com/mschwar/context-project.git/",
        "https://x-access-token:ghs_secret123@github.com/mschwar/context-project.git",
        "ssh://git@github.com/mschwar/context-project.git",
    ]
    for url in variants:
        assert normalize_git_remote_url(url) == expected
    assert normalize_git_remote_url("/local/filesystem/clone") is None


def test_compute_repo_id_matches_across_hosts_remotes_and_root_commits(tmp_path: Path) -> None:
    repo_ssh = _init_git_repo(tmp_path / "host_a" / "context-project")
    _git(repo_ssh, "remote", "add", "origin", "git@github.com:mschwar/context-project.git")

    repo_https = _init_git_repo(tmp_path / "completely_different_dir" / "checkout_2")
    _git(
        repo_https,
        "remote",
        "add",
        "origin",
        "https://token:secret@github.com/mschwar/context-project",
    )

    assert compute_repo_id(repo_ssh) == compute_repo_id(repo_https)

    # Without remotes, two clones sharing the same root commit SHA produce the same repo_id
    origin_local = _init_git_repo(tmp_path / "local_origin")
    (origin_local / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(origin_local, "add", "app.py")
    _git(origin_local, "commit", "-m", "initial")

    second_copy = tmp_path / "other_mount" / "copy_without_remote"
    _git(tmp_path, "clone", str(origin_local), str(second_copy))
    _git(second_copy, "remote", "remove", "origin")

    assert compute_repo_id(origin_local) == compute_repo_id(second_copy)


# ── Wave A & B: Boundary doc filtering & .ctx/capsule.json persistence ──────


def test_archive_docs_and_todos_excluded_while_capsule_persists_atomically(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path / "capsule_repo")
    _git(repo, "remote", "add", "origin", "git@github.com:acme/capsule-svc.git")
    (repo / "AGENTS.md").write_text("# Agents\n\nFollow repository rules.\n", encoding="utf-8")
    (repo / "RUNBOOK.md").write_text("# Runbook\n\nRun pytest before merge.\n", encoding="utf-8")
    (repo / "TODOS.md").write_text("# TODOS\n\n- volatile item\n", encoding="utf-8")
    (repo / "archive" / "afo").mkdir(parents=True)
    (repo / "archive" / "architecture.md").write_text("# Retired Architecture\n", encoding="utf-8")
    (repo / "archive" / "afo" / "01-spec.md").write_text("# Old Spec\n", encoding="utf-8")
    (repo / "src" / "svc").mkdir(parents=True)
    (repo / "src" / "svc" / "core.py").write_text(
        "def process_event(payload: dict) -> bool:\n    return bool(payload)\n",
        encoding="utf-8",
    )

    init_res = api.init_project(repo)
    capsule_path = repo / ".ctx" / "capsule.json"
    assert capsule_path.is_file()

    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert capsule["repo_id"] == init_res["metadata"]["repo_id"]
    assert capsule["structural_hash"] == init_res["metadata"]["structural_hash"]
    assert isinstance(capsule["dependency_summary"]["internal_edge_count"], int)

    bdoc_paths = {d["path"] for d in capsule["authority_boundaries"]}
    assert "AGENTS.md" in bdoc_paths
    assert "RUNBOOK.md" in bdoc_paths
    assert "TODOS.md" not in bdoc_paths
    assert "archive/architecture.md" not in bdoc_paths
    assert "archive/afo/01-spec.md" not in bdoc_paths

    # Mutating source and calling refresh updates capsule.json structural_hash in lockstep
    (repo / "src" / "svc" / "core.py").write_text(
        "def process_event(payload: dict) -> bool:\n    return True\n\n"
        "def validate_event(name: str) -> str:\n    return name.strip()\n",
        encoding="utf-8",
    )
    api.refresh(repo)
    meta_after = json.loads((repo / ".ctx" / "metadata.json").read_text(encoding="utf-8"))
    capsule_after = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert capsule_after["structural_hash"] == meta_after["structural_hash"]
    assert capsule_after["structural_hash"] != init_res["metadata"]["structural_hash"]


# ── Wave B: Hub-aware symbol ranking & AST non-kwarg extraction ─────────────


def test_python_kwarg_names_do_not_inflate_cli_command_over_hub_symbols(tmp_path: Path) -> None:
    repo = tmp_path / "hub_ranking_repo"
    pkg = repo / "src" / "engine"
    pkg.mkdir(parents=True)

    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "cli.py").write_text(
        "def check() -> None:\n    pass\n\ndef reset() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (pkg / "api.py").write_text(
        "from engine.compiler import compile_graph\n"
        "def run_api() -> object:\n    return compile_graph()\n",
        encoding="utf-8",
    )
    (pkg / "server.py").write_text(
        "from engine.compiler import compile_graph\n"
        "def serve_http() -> object:\n    return compile_graph()\n",
        encoding="utf-8",
    )
    (pkg / "compiler.py").write_text(
        "def compile_graph() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    # Four worker modules using `check=False` kwargs while calling `compile_graph()`
    for idx in range(4):
        (pkg / f"worker_{idx}.py").write_text(
            "import subprocess\n"
            "from engine.compiler import compile_graph\n"
            f"def job_{idx}() -> None:\n"
            "    subprocess.run(['true'], check=False)\n"
            "    subprocess.run(['true'], check=False)\n"
            "    compile_graph()\n",
            encoding="utf-8",
        )

    sk = extract_skeleton(repo)
    sub_map = {s.path: s for s in sk.subsystems}
    engine_sub = sub_map["src/engine"]
    assert engine_sub.arch_role == "core_domain"
    assert "compiler.py:fn compile_graph" in engine_sub.key_symbols[:3]
    assert "cli.py:fn check" not in engine_sub.key_symbols[:2]


# ── Wave C: ctx impact --git-diff & --staged proportional verification ──────


def test_diff_impact_scopes_docs_only_targeted_and_broad_across_cli_and_mcp(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _init_git_repo(tmp_path / "diff_impact_repo")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Demo\n\n## TL;DR\n\nShort summary.\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("# AGENTS\n\nFollow checks.\n", encoding="utf-8")
    (repo / "src" / "demo").mkdir(parents=True)
    (repo / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "demo" / "billing.py").write_text(
        "def compute_total(cents: int) -> int:\n    return cents\n",
        encoding="utf-8",
    )
    (repo / "src" / "demo" / "orders.py").write_text(
        "from demo.billing import compute_total\n\n"
        "def create_order(cents: int) -> int:\n    return compute_total(cents)\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_doc_hygiene.py").write_text(
        "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_billing.py").write_text(
        "from demo.billing import compute_total\n\n"
        "def test_total() -> None:\n    assert compute_total(5) == 5\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_orders.py").write_text(
        "from demo.orders import create_order\n\n"
        "def test_order() -> None:\n    assert create_order(5) == 5\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    # 1. Clean working tree -> scope == "none"
    clean_res = analyze_diff_impact(repo, git_diff="WORKTREE")
    assert clean_res.verification_scope == "none"
    assert clean_res.recommended_checks == []

    # 2. Docs-only working-tree edit -> scope == "docs_only"
    (repo / "README.md").write_text("# Demo\n\n## TL;DR\n\nUpdated summary.\n", encoding="utf-8")
    docs_res = analyze_diff_impact(repo, git_diff="HEAD")
    assert docs_res.verification_scope == "docs_only"
    assert "python -m unittest tests/test_doc_hygiene.py" in docs_res.recommended_checks
    _git(repo, "checkout", "--", "README.md")

    # 3. Staged single-module edit -> scope == "targeted_tests" via CLI & MCP
    (repo / "src" / "demo" / "billing.py").write_text(
        "def compute_total(cents: int, tax: int = 0) -> int:\n    return cents + tax\n",
        encoding="utf-8",
    )
    _git(repo, "add", "src/demo/billing.py")

    runner = CliRunner()
    cli_res = runner.invoke(cli, ["--output", "json", "impact", "--staged", str(repo)])
    assert cli_res.exit_code == 0, cli_res.output
    env = json.loads(cli_res.output)
    assert env["status"] == "success"
    data = env["data"]
    assert data["diff_spec"] == "--staged"
    assert data["verification_scope"] == "targeted_tests"
    coupled_paths = [c["path"] for c in data["coupled_tests"]]
    assert "tests/test_billing.py" in coupled_paths
    assert "tests/test_orders.py" in coupled_paths
    assert data["recommended_checks"] == [
        "pytest tests/test_billing.py tests/test_orders.py"
    ]

    capsys.readouterr()
    mcp = CtxMCPServer(root=repo)
    mcp._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ctx_impact", "arguments": {"staged": True}},
        }
    )
    mcp_resp = json.loads(capsys.readouterr().out.strip())
    mcp_payload = json.loads(mcp_resp["result"]["content"][0]["text"])
    assert mcp_payload["verification_scope"] == "targeted_tests"

    # 4. Shared config edit (pyproject.toml) escalates to broad_suite
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )
    broad_res = analyze_diff_impact(repo, git_diff="HEAD")
    assert broad_res.verification_scope == "broad_suite"
    assert broad_res.recommended_checks == ["pytest"]
    assert any("pyproject.toml" in r for r in broad_res.escalation_reasons)

    # 5. Reject flag-injected git_diff spec and mutually exclusive target + --git-diff
    with pytest.raises(ValueError, match="Invalid git diff revision"):
        analyze_diff_impact(repo, git_diff="--output=/tmp/pwn")

    bad_cli = runner.invoke(
        cli,
        ["--output", "json", "impact", "src/demo/billing.py", "--staged", str(repo)],
    )
    assert bad_cli.exit_code == 1
    assert json.loads(bad_cli.output)["errors"][0]["code"] == "invalid_usage"


# ── Wave D: 13-language C/C++ parser & #include blast radius ────────────────


def test_c_cpp_parser_and_include_dependency_graph(tmp_path: Path) -> None:
    repo = tmp_path / "cpp_engine"
    (repo / "include").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "tests").mkdir()

    header = repo / "include" / "vec3.hpp"
    header.write_text(
        "#pragma once\n"
        "#include <cmath>\n"
        "namespace math {\n"
        "struct Vec3 {\n"
        "    float x;\n"
        "    float y;\n"
        "    float z;\n"
        "};\n"
        "enum class Axis { X, Y, Z };\n"
        "using Scalar = float;\n"
        "float dot_product(const Vec3& a, const Vec3& b);\n"
        "}\n",
        encoding="utf-8",
    )
    parsed = parse_c_cpp_file(header)
    assert "Vec3" in parsed["structs"]
    assert "Axis" in parsed["enums"]
    assert "math" in parsed["modules"]
    assert "Scalar" in parsed["types"]
    assert "dot_product" in parsed["functions"]

    (repo / "src" / "physics.hpp").write_text(
        '#include "vec3.hpp"\n'
        "class RigidBody {\n"
        "public:\n"
        "    void step(float dt);\n"
        "};\n",
        encoding="utf-8",
    )
    (repo / "src" / "world.cpp").write_text(
        '#include "physics.hpp"\n'
        "#include <vector>\n"
        "int step_world(int ticks) {\n"
        "    if (ticks <= 0) {\n"
        "        return 0;\n"
        "    }\n"
        "    return ticks;\n"
        "}\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_world.cpp").write_text(
        '#include "physics.hpp"\n'
        "int test_simulation() {\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    sk = extract_skeleton(repo)
    assert "C++" in sk.languages

    impact = analyze_impact(repo, "include/vec3.hpp", skeleton=sk)
    assert impact.direct_inbound_dependents == ["src/physics.hpp"]
    transitive_paths = {r["path"] for r in impact.transitive_inbound_dependents}
    assert "src/world.cpp" in transitive_paths
    coupled_test_paths = {t["path"] for t in impact.coupled_tests}
    assert "tests/test_world.cpp" in coupled_test_paths


# ── Wave D: Monorepo cross-package workspace resolution (Py / TS / Rust) ────


def test_monorepo_workspace_edges_for_python_typescript_and_rust(tmp_path: Path) -> None:
    # 1. Python monorepo: packages/core/src/acme_core -> packages/api/src/acme_api
    py_mono = tmp_path / "py_mono"
    (py_mono / "packages" / "core" / "src" / "acme_core").mkdir(parents=True)
    (py_mono / "packages" / "core" / "src" / "acme_core" / "__init__.py").write_text("", encoding="utf-8")
    (py_mono / "packages" / "core" / "src" / "acme_core" / "models.py").write_text(
        "class Invoice:\n    pass\n",
        encoding="utf-8",
    )
    (py_mono / "packages" / "api" / "src" / "acme_api").mkdir(parents=True)
    (py_mono / "packages" / "api" / "src" / "acme_api" / "__init__.py").write_text("", encoding="utf-8")
    (py_mono / "packages" / "api" / "src" / "acme_api" / "handler.py").write_text(
        "from acme_core.models import Invoice\n\ndef handle() -> Invoice:\n    return Invoice()\n",
        encoding="utf-8",
    )
    (py_mono / "packages" / "api" / "tests").mkdir(parents=True)
    (py_mono / "packages" / "api" / "tests" / "test_handler.py").write_text(
        "from acme_api.handler import handle\n\ndef test_h() -> None:\n    assert handle() is not None\n",
        encoding="utf-8",
    )

    py_impact = analyze_impact(py_mono, "packages/core/src/acme_core/models.py")
    assert "packages/api/src/acme_api/handler.py" in py_impact.direct_inbound_dependents
    assert "packages/api/tests/test_handler.py" in {t["path"] for t in py_impact.coupled_tests}

    # 2. TypeScript workspace monorepo: @acme/shared -> packages/web/src/app.ts
    ts_mono = tmp_path / "ts_mono"
    (ts_mono / "packages" / "shared" / "src").mkdir(parents=True)
    (ts_mono / "packages" / "shared" / "package.json").write_text(
        json.dumps({"name": "@acme/shared", "main": "./src/index.ts"}),
        encoding="utf-8",
    )
    (ts_mono / "packages" / "shared" / "src" / "index.ts").write_text(
        "export interface SessionToken { id: string; }\n",
        encoding="utf-8",
    )
    (ts_mono / "packages" / "web" / "src").mkdir(parents=True)
    (ts_mono / "packages" / "web" / "package.json").write_text(
        json.dumps({"name": "@acme/web"}),
        encoding="utf-8",
    )
    (ts_mono / "packages" / "web" / "src" / "client.ts").write_text(
        'import { SessionToken } from "@acme/shared";\n'
        "export function current(t: SessionToken): string { return t.id; }\n",
        encoding="utf-8",
    )

    ts_impact = analyze_impact(ts_mono, "packages/shared/src/index.ts")
    assert "packages/web/src/client.ts" in ts_impact.direct_inbound_dependents

    # 3. Rust Cargo workspace: crates/core-domain -> crates/cli-bin
    rs_mono = tmp_path / "rs_mono"
    (rs_mono / "crates" / "core-domain" / "src").mkdir(parents=True)
    (rs_mono / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/core-domain", "crates/cli-bin"]\n',
        encoding="utf-8",
    )
    (rs_mono / "crates" / "core-domain" / "Cargo.toml").write_text(
        '[package]\nname = "core-domain"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (rs_mono / "crates" / "core-domain" / "src" / "lib.rs").write_text(
        "pub struct LedgerEntry { pub id: u64 }\n",
        encoding="utf-8",
    )
    (rs_mono / "crates" / "cli-bin" / "src").mkdir(parents=True)
    (rs_mono / "crates" / "cli-bin" / "Cargo.toml").write_text(
        '[package]\nname = "cli-bin"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (rs_mono / "crates" / "cli-bin" / "src" / "main.rs").write_text(
        "use core_domain::LedgerEntry;\nfn main() { let _e = LedgerEntry { id: 1 }; }\n",
        encoding="utf-8",
    )

    rs_impact = analyze_impact(rs_mono, "crates/core-domain/src/lib.rs")
    assert "crates/cli-bin/src/main.rs" in rs_impact.direct_inbound_dependents
