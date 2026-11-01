"""Tests for Phase 32: directed dependency/blast-radius graph and operational surface extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ctx import api
from ctx.cli import cli
from ctx.impact import analyze_impact, build_dependency_graph
from ctx.mcp_server import CtxMCPServer
from ctx.skeleton import extract_skeleton, render_context_0, render_context_1


def _build_polyglot_surface_repo(root: Path) -> Path:
    """Create a realistic polyglot repo exercising CLI, HTTP, MCP, env, and cross-file imports."""
    (root / "AGENTS.md").write_text("# AGENTS\n\nRepository authority rules.\n", encoding="utf-8")
    (root / "architecture.md").write_text("# Architecture\n\nCore layered design.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo-app"\nversion = "0.1.0"\n'
        '[project.scripts]\ndemo = "demo.cli:main"\n',
        encoding="utf-8",
    )

    pkg = root / "src" / "demo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""Demo package."""\n', encoding="utf-8")

    # Core leaf module with widely referenced symbol `CoreLedgerStore`
    (pkg / "store.py").write_text(
        "import os\n\n"
        "def zzz_unused_helper() -> int:\n"
        "    return 1\n\n"
        "class CoreLedgerStore:\n"
        "    def load(self) -> str:\n"
        '        return os.getenv("DEMO_STORE_URL", "sqlite:///local.db")\n',
        encoding="utf-8",
    )

    # Service layer importing `from demo import store` (submodule member import!)
    (pkg / "service.py").write_text(
        "import os\n"
        "from demo import store\n\n"
        "class LedgerService:\n"
        "    def __init__(self) -> None:\n"
        "        self.db = store.CoreLedgerStore()\n"
        '        self.mode = os.environ.get("DEMO_SERVICE_MODE", "strict")\n',
        encoding="utf-8",
    )

    # Click CLI + hidden hook + FastAPI HTTP routes + declarative AnnAssign MCP tables
    (pkg / "cli.py").write_text(
        "import click\n"
        "from demo.service import LedgerService\n\n"
        "@click.group()\n"
        "def main() -> None:\n"
        "    pass\n\n"
        '@main.command("sync")\n'
        '@click.option("--force", is_flag=True)\n'
        '@click.option("--limit", type=int, default=10)\n'
        "def sync_cmd(force: bool, limit: int) -> None:\n"
        "    LedgerService()\n\n"
        '@main.command("_internal_hook", hidden=True)\n'
        '@click.option("--trigger", default="post-commit")\n'
        "def internal_hook(trigger: str) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    (pkg / "http_api.py").write_text(
        "from fastapi import APIRouter\n"
        "from demo.service import LedgerService\n\n"
        "router = APIRouter()\n\n"
        '@router.get("/v1/health")\n'
        "def get_health() -> dict:\n"
        "    return {'ok': True}\n\n"
        '@router.api_route("/v1/items", methods=["POST", "DELETE"])\n'
        "def mutate_items() -> dict:\n"
        "    svc = LedgerService()\n"
        "    return {'mode': svc.mode}\n",
        encoding="utf-8",
    )

    (pkg / "mcp_tools.py").write_text(
        "from demo.service import LedgerService\n\n"
        "TOOL_DEFINITIONS: list[dict[str, object]] = [\n"
        '    {"name": "demo_query", "description": "Query ledger state", "inputSchema": {"type": "object"}},\n'
        "]\n"
        "RESOURCE_DEFINITIONS = (\n"
        '    {"uri": "demo://state/current", "name": "Current State", "mimeType": "application/json"},\n'
        ")\n\n"
        "def handle_query() -> LedgerService:\n"
        "    return LedgerService()\n",
        encoding="utf-8",
    )

    # Argparse script
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "admin_tool.py").write_text(
        "import argparse\n"
        "from demo.store import CoreLedgerStore\n\n"
        "def build_parser() -> argparse.ArgumentParser:\n"
        '    parser = argparse.ArgumentParser(prog="admin-tool")\n'
        '    parser.add_argument("--dry-run", action="store_true")\n'
        "    sub = parser.add_subparsers(dest='cmd')\n"
        '    p_audit = sub.add_parser("audit")\n'
        '    p_audit.add_argument("--strict", action="store_true")\n'
        "    CoreLedgerStore()\n"
        "    return parser\n",
        encoding="utf-8",
    )

    # Coupled tests (direct import, transitive import, naming convention)
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_store.py").write_text(
        "from demo.store import CoreLedgerStore\n\n"
        "def test_load() -> None:\n"
        "    assert CoreLedgerStore().load()\n",
        encoding="utf-8",
    )
    (tests_dir / "test_http_api.py").write_text(
        "from demo.http_api import mutate_items\n\n"
        "def test_mutate() -> None:\n"
        "    assert mutate_items()['mode'] == 'strict'\n",
        encoding="utf-8",
    )
    return root


def test_operational_surfaces_and_structural_hash_sensitivity(tmp_path: Path) -> None:
    repo = _build_polyglot_surface_repo(tmp_path)
    # Add JS, Go, and Rust surface files as well
    web = repo / "web"
    web.mkdir()
    (web / "server.ts").write_text(
        'import express from "express";\n'
        "const app = express();\n"
        'const origin = process.env.WEB_ALLOWED_ORIGIN;\n'
        'app.post("/api/webhook", (_req, res) => res.json({ origin }));\n',
        encoding="utf-8",
    )
    go_dir = repo / "go_svc"
    go_dir.mkdir()
    (go_dir / "main.go").write_text(
        "package main\n\n"
        'import ("net/http"; "os")\n\n'
        "func register(mux *http.ServeMux) {\n"
        '    _ = os.Getenv("GO_WORKER_TOKEN")\n'
        '    mux.HandleFunc("GET /v1/go-ping", nil)\n'
        "}\n",
        encoding="utf-8",
    )
    rs_dir = repo / "rust_svc"
    rs_dir.mkdir()
    (rs_dir / "lib.rs").write_text(
        "use std::env;\n\n"
        '#[post("/v1/rust-ingest")]\n'
        "pub fn ingest() {\n"
        '    let _ = env::var("RUST_INGEST_KEY");\n'
        "}\n",
        encoding="utf-8",
    )

    sk1 = extract_skeleton(repo)
    by_kind_name = {(s.kind, s.name): s for s in sk1.operational_surfaces}

    # Python Click CLI (including hidden flag preservation)
    assert ("cli_command", "sync") in by_kind_name
    assert "--force" in by_kind_name[("cli_command", "sync")].detail
    assert ("cli_command", "_internal_hook") in by_kind_name
    assert "hidden=true" in by_kind_name[("cli_command", "_internal_hook")].detail

    # Argparse subcommand
    assert ("cli_command", "audit") in by_kind_name

    # FastAPI HTTP routes
    assert ("http_route", "GET /v1/health") in by_kind_name
    assert ("http_route", "POST /v1/items") in by_kind_name
    assert ("http_route", "DELETE /v1/items") in by_kind_name

    # Declarative AnnAssign / Assign MCP tool & resource tables
    assert ("mcp_tool", "demo_query") in by_kind_name
    assert ("mcp_resource", "demo://state/current") in by_kind_name

    # Polyglot HTTP + env vars
    assert ("http_route", "POST /api/webhook") in by_kind_name
    assert ("http_route", "GET /v1/go-ping") in by_kind_name
    assert ("http_route", "POST /v1/rust-ingest") in by_kind_name
    for env_key in (
        "DEMO_STORE_URL",
        "DEMO_SERVICE_MODE",
        "WEB_ALLOWED_ORIGIN",
        "GO_WORKER_TOKEN",
        "RUST_INGEST_KEY",
    ):
        assert ("env_var", env_key) in by_kind_name

    # CONTEXT-0 and CONTEXT-1 rendering
    c0 = render_context_0(sk1)
    assert "## Entrypoints & Operational Surfaces" in c0
    assert "`demo_query`" in c0
    assert "`GET /v1/health`" in c0
    assert "| Subsystem | Role |" in c0
    c1 = render_context_1(sk1)
    assert "[`entrypoint_interface`]" in c1 or "[`core_domain`]" in c1

    # Cross-file reference ranking: CoreLedgerStore is referenced across 3 external files,
    # so it must rank ahead of unreferenced `zzz_unused_helper` in `src/demo` key_symbols.
    demo_sub = next(s for s in sk1.subsystems if s.path == "src/demo")
    core_idx = next(i for i, sym in enumerate(demo_sub.key_symbols) if "CoreLedgerStore" in sym)
    unused_idx = next(i for i, sym in enumerate(demo_sub.key_symbols) if "zzz_unused_helper" in sym)
    assert core_idx < unused_idx

    # Internal body-only edit (no symbol, import, or public operational surface change)
    # must NOT alter `structural_hash`!
    orig_hash = sk1.structural_hash
    (repo / "src" / "demo" / "store.py").write_text(
        "import os\n\n"
        "def zzz_unused_helper() -> int:\n"
        "    intermediate = 40 + 2\n"
        "    return intermediate\n\n"
        "class CoreLedgerStore:\n"
        "    def load(self) -> str:\n"
        '        return os.getenv("DEMO_STORE_URL", "sqlite:///updated-default.db")\n',
        encoding="utf-8",
    )
    sk_body_edit = extract_skeleton(repo)
    assert sk_body_edit.structural_hash == orig_hash

    # Adding a new public HTTP route MUST alter `structural_hash`!
    (repo / "src" / "demo" / "http_api.py").write_text(
        (repo / "src" / "demo" / "http_api.py").read_text(encoding="utf-8")
        + '\n@router.get("/v1/metrics")\ndef get_metrics() -> dict:\n    return {}\n',
        encoding="utf-8",
    )
    sk_surface_change = extract_skeleton(repo)
    assert sk_surface_change.structural_hash != orig_hash


def test_dependency_graph_impact_analysis_and_polyglot_imports(tmp_path: Path) -> None:
    repo = _build_polyglot_surface_repo(tmp_path)

    # Add TypeScript tsconfig paths alias + Go internal package + Rust crate::/mod + a Python cycle
    (repo / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {"@web/*": ["frontend/src/*"]},
                }
            }
        ),
        encoding="utf-8",
    )
    fe = repo / "frontend" / "src"
    fe.mkdir(parents=True)
    (fe / "client.ts").write_text("export function fetchItems() { return []; }\n", encoding="utf-8")
    (fe / "page.ts").write_text('import { fetchItems } from "@web/client";\nexport const items = fetchItems();\n', encoding="utf-8")

    (repo / "go.mod").write_text("module example.com/poly\n\ngo 1.22\n", encoding="utf-8")
    (repo / "internal" / "db").mkdir(parents=True)
    (repo / "internal" / "db" / "db.go").write_text("package db\nfunc Open() {}\n", encoding="utf-8")
    (repo / "cmd" / "worker").mkdir(parents=True)
    (repo / "cmd" / "worker" / "main.go").write_text(
        'package main\nimport "example.com/poly/internal/db"\nfunc main() { db.Open() }\n',
        encoding="utf-8",
    )

    rs_src = repo / "crate_demo" / "src"
    rs_src.mkdir(parents=True)
    (rs_src / "lib.rs").write_text("pub mod codec;\npub mod runner;\n", encoding="utf-8")
    (rs_src / "codec.rs").write_text("pub struct Frame;\n", encoding="utf-8")
    (rs_src / "runner.rs").write_text("use crate::codec::Frame;\npub fn run(_f: Frame) {}\n", encoding="utf-8")

    # Add an isolated two-file cycle to test Tarjan cycle detection
    cyc = repo / "src" / "cycle_pkg"
    cyc.mkdir(parents=True)
    (cyc / "alpha.py").write_text("from cycle_pkg import beta\ndef a(): return beta\n", encoding="utf-8")
    (cyc / "beta.py").write_text("from cycle_pkg import alpha\ndef b(): return alpha\n", encoding="utf-8")

    graph = build_dependency_graph(repo)
    assert "src/demo/store.py" in graph.outbound_files["src/demo/service.py"]
    assert "frontend/src/client.ts" in graph.outbound_files["frontend/src/page.ts"]
    assert "internal/db/db.go" in graph.outbound_files["cmd/worker/main.go"]
    assert "crate_demo/src/codec.rs" in graph.outbound_files["crate_demo/src/runner.rs"]
    assert any(set(c) == {"src/cycle_pkg/alpha.py", "src/cycle_pkg/beta.py"} for c in graph.cycles)

    # Impact query by symbol name `CoreLedgerStore`
    impact_res = analyze_impact(repo, "CoreLedgerStore")
    assert impact_res.target_kind == "symbol"
    assert impact_res.matched_files == ["src/demo/store.py"]
    assert "src/demo/service.py" in impact_res.direct_inbound_dependents

    trans_paths = {r["path"] for r in impact_res.transitive_inbound_dependents}
    assert {
        "src/demo/service.py",
        "src/demo/cli.py",
        "src/demo/http_api.py",
        "src/demo/mcp_tools.py",
        "scripts/admin_tool.py",
    }.issubset(trans_paths)

    coupled_test_paths = {t["path"]: t["reason"] for t in impact_res.coupled_tests}
    assert coupled_test_paths["tests/test_store.py"] == "direct_import"
    assert coupled_test_paths["tests/test_http_api.py"] == "transitive_import"

    # Affected entrypoints & operational surfaces include CLI, HTTP, and MCP surfaces downstream of store.py!
    eps_joined = "\n".join(impact_res.affected_entrypoints)
    assert "cli:demo -> demo.cli:main" in eps_joined
    assert "cli_command:sync" in eps_joined
    assert "http_route:POST /v1/items" in eps_joined
    assert "mcp_tool:demo_query" in eps_joined

    # Governing authority & architecture docs
    assert "AGENTS.md" in impact_res.governing_docs
    assert "architecture.md" in impact_res.governing_docs

    # Depth-1 blast radius cap excludes distance-2 transitive callers
    impact_d1 = analyze_impact(repo, "src/demo/store.py", max_depth=1)
    d1_paths = {r["path"] for r in impact_d1.transitive_inbound_dependents}
    assert "src/demo/service.py" in d1_paths
    assert "src/demo/http_api.py" not in d1_paths

    # Cycle target reports cycles_involving_target
    cyc_impact = analyze_impact(repo, "src/cycle_pkg/alpha.py")
    assert len(cyc_impact.cycles_involving_target) == 1

    # Missing target raises ValueError
    with pytest.raises(ValueError, match="Target not found"):
        analyze_impact(repo, "NonExistentSymbolXYZ")


def test_cli_impact_mcp_impact_and_enriched_fleet_capsule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _build_polyglot_surface_repo(tmp_path)
    runner = CliRunner()

    # Human CLI output
    res_human = runner.invoke(cli, ["impact", "src/demo/store.py", str(repo)])
    assert res_human.exit_code == 0, res_human.output
    assert "Target: src/demo/store.py (file)" in res_human.output
    assert "Coupled tests" in res_human.output

    # JSON CLI output
    res_json = runner.invoke(cli, ["impact", "CoreLedgerStore", str(repo), "--output", "json"])
    assert res_json.exit_code == 0, res_json.output
    env = json.loads(res_json.output)
    assert env["status"] == "success"
    assert env["command"] == "impact"
    assert env["data"]["target_kind"] == "symbol"
    assert "src/demo/store.py" in env["data"]["matched_files"]

    # Invalid target exits 1 in both human and json modes
    res_err_human = runner.invoke(cli, ["impact", "does_not_exist.py", str(repo)])
    assert res_err_human.exit_code == 1
    res_err_json = runner.invoke(cli, ["impact", "does_not_exist.py", str(repo), "--output", "json"])
    assert res_err_json.exit_code == 1
    err_env = json.loads(res_err_json.output)
    assert err_env["status"] == "error"
    assert err_env["errors"][0]["code"] == "invalid_target"

    # MCP ctx_impact + path traversal confinement
    capsys.readouterr()
    server = CtxMCPServer(repo)
    server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ctx_impact", "arguments": {"target": "src/demo/store.py"}},
        }
    )
    mcp_ok = json.loads(capsys.readouterr().out.strip())
    assert not mcp_ok["result"].get("isError")
    mcp_payload = json.loads(mcp_ok["result"]["content"][0]["text"])
    assert mcp_payload["matched_files"] == ["src/demo/store.py"]

    server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ctx_impact", "arguments": {"path": "../../etc", "target": "passwd"}},
        }
    )
    mcp_traversal = json.loads(capsys.readouterr().out.strip())
    assert "error" in mcp_traversal or mcp_traversal.get("result", {}).get("isError") is True

    # Enriched FleetCapsuleResult (`ctx export --capsule`)
    capsule = api.build_fleet_capsule(repo, depth=1)
    assert len(capsule.operational_surfaces) >= 5
    assert capsule.dependency_summary["internal_edge_count"] >= 5
    assert capsule.dependency_summary["cycle_count"] == 0
    assert any(sub.get("arch_role") for sub in capsule.subsystems)
