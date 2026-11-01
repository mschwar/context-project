"""Tests for Phase 33: Phase 27.1 A/B/C navigation benchmark, lazy heavy-SDK imports, and CLI polish."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from click.testing import CliRunner

from ctx.benchmark import render_benchmark_markdown, run_navigation_benchmark
from ctx.cli import cli


def _build_benchmark_fixture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text("# AGENTS\n\nGovernance contract.\n", encoding="utf-8")
    (root / "architecture.md").write_text("# Architecture\n\nSystem architecture.\n", encoding="utf-8")
    (root / "CONTRIBUTING.md").write_text("# Contributing\n\nPR workflow.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "bench-demo"\nversion = "0.1.0"\n'
        '[project.scripts]\nbench = "bench.cli:app"\n',
        encoding="utf-8",
    )
    pkg = root / "src" / "bench"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text(
        "import os\n\n"
        "class CoreEngine:\n"
        "    def run(self) -> str:\n"
        '        return os.getenv("BENCH_MODE", "fast")\n',
        encoding="utf-8",
    )
    (pkg / "middle.py").write_text(
        "from bench.core import CoreEngine\n\n"
        "def execute() -> str:\n"
        "    return CoreEngine().run()\n",
        encoding="utf-8",
    )
    (pkg / "cli.py").write_text(
        "import click\n"
        "from bench.middle import execute\n\n"
        "@click.command()\n"
        '@click.option("--verbose", is_flag=True)\n'
        "def app(verbose: bool) -> None:\n"
        "    execute()\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text(
        "from bench.core import CoreEngine\ndef test_core(): assert CoreEngine().run()\n",
        encoding="utf-8",
    )
    (tests / "test_cli.py").write_text(
        "from bench.cli import app\ndef test_cli(): assert app is not None\n",
        encoding="utf-8",
    )
    return root


def test_navigation_benchmark_and_cli_report_generation(tmp_path: Path) -> None:
    repo = _build_benchmark_fixture(tmp_path / "bench_repo")
    report = run_navigation_benchmark([repo])

    assert report["repos_evaluated"] == 1
    aggs = report["summary"]["aggregates"]
    assert set(aggs.keys()) == {"raw_grep", "tier1_manifests", "tier2_plus_impact"}
    assert aggs["tier2_plus_impact"]["mean_recall"] > aggs["raw_grep"]["mean_recall"]
    assert aggs["tier2_plus_impact"]["mean_tool_turns"] < aggs["raw_grep"]["mean_tool_turns"]
    assert aggs["tier2_plus_impact"]["maint_llm_tokens_impl_commit"] == 0.0
    # Independent static oracle checks:
    # 1) CONTRIBUTING.md is in independent oracle boundary docs but not in skeleton._AUTHORITY_DOC_NAMES -> < 1.0 (proves non-hardcoded recall!)
    repo_cond_c = report["repositories"][0]["conditions"]["tier2_plus_impact"]
    repo_cond_a = report["repositories"][0]["conditions"]["raw_grep"]
    assert 0.5 <= repo_cond_c["recall_arch_orientation"] < 1.0
    # 2) Multi-hop cli.py -> middle.py -> core.py: raw regex grep for \bcore\b finds middle.py (0.5) while ctx impact finds both (1.0)
    assert repo_cond_a["recall_blast_radius"] == 0.5
    assert repo_cond_c["recall_blast_radius"] == 1.0

    md = render_benchmark_markdown(report)
    assert "# Phase 27.1 — Deterministic Static-Oracle Navigation & Blast-Radius Benchmark" in md
    assert "| `tier2_plus_impact` |" in md

    # CLI `ctx benchmark` writing both Markdown and JSON reports
    runner = CliRunner()
    md_out = tmp_path / "out" / "report.md"
    res_md = runner.invoke(cli, ["benchmark", str(repo), "--out-file", str(md_out)])
    assert res_md.exit_code == 0, res_md.output
    assert md_out.is_file()
    assert "Phase 27.1" in md_out.read_text(encoding="utf-8")

    json_out = tmp_path / "out" / "report.json"
    res_json = runner.invoke(cli, ["benchmark", str(repo), "-o", str(json_out), "--output", "json"])
    assert res_json.exit_code == 0, res_json.output
    env = json.loads(res_json.output)
    assert env["status"] == "success"
    assert env["command"] == "benchmark"
    assert json.loads(json_out.read_text(encoding="utf-8"))["repos_evaluated"] == 1


def test_lazy_imports_keep_deterministic_paths_free_of_heavy_sdks(tmp_path: Path) -> None:
    repo = _build_benchmark_fixture(tmp_path / "lazy_repo")
    src_root = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    probe_code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "import ctx.sdk, ctx.skeleton, ctx.impact, ctx.jev, ctx.benchmark\n"
        "from ctx import api\n"
        f"root = Path({str(repo)!r})\n"
        "api.check(root)\n"
        "api.build_fleet_capsule(root, depth=1)\n"
        "api.analyze_impact(root, 'src/bench/core.py')\n"
        "api.jev_list_heads(root)\n"
        "heavy = [m for m in ('anthropic', 'openai', 'tiktoken', 'watchdog', 'fastapi', 'uvicorn') if m in sys.modules]\n"
        "print(json.dumps({'heavy_loaded': heavy}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe_code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    parsed = json.loads(proc.stdout.strip())
    assert parsed["heavy_loaded"] == []


def test_pyproject_optional_extras_and_deduplicated_reset_clean(tmp_path: Path) -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    for group in ("anthropic", "openai", "cloud", "watch", "serve", "all"):
        assert group in extras, f"Missing optional dependency extra [{group}]"

    # Verify both `ctx reset` and legacy `ctx clean` work identically through shared helper
    repo = tmp_path / "reset_repo"
    repo.mkdir()
    (repo / "CONTEXT.md").write_text("---\ngenerator: ctx/1.1.0\n---\n# root\n", encoding="utf-8")
    sub = repo / "sub"
    sub.mkdir()
    (sub / "CONTEXT.md").write_text("---\ngenerator: ctx/1.1.0\n---\n# sub\n", encoding="utf-8")

    runner = CliRunner()
    dry = runner.invoke(cli, ["clean", str(repo), "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert (repo / "CONTEXT.md").is_file()

    real = runner.invoke(cli, ["reset", str(repo), "--yes", "--output", "json"])
    assert real.exit_code == 0, real.output
    env = json.loads(real.output)
    assert env["data"]["manifests_removed"] == 2
    assert not (repo / "CONTEXT.md").exists()

    # Round-2 QA Finding 8: legacy `ctx clean` on a 0-manifest tree without `--yes` in `--output json`
    # succeeds with exit 0 and does not acquire lock or create `.ctx-cache/`.
    empty_repo = tmp_path / "empty_clean_repo"
    empty_repo.mkdir()
    clean_empty = runner.invoke(cli, ["clean", str(empty_repo), "--output", "json"])
    assert clean_empty.exit_code == 0, clean_empty.output
    clean_env = json.loads(clean_empty.output)
    assert clean_env["status"] == "success"
    assert clean_env["data"] == {"manifests_removed": 0, "paths": []}
    assert not (empty_repo / ".ctx-cache").exists()

    # Round-2 QA Finding 9: negative recall/F1 deltas never render `+-` in benchmark Markdown
    sample_report = run_navigation_benchmark([_build_benchmark_fixture(tmp_path / "neg_delta_repo")])
    sample_report["summary"]["recall_gain_vs_raw_grep_pct"] = -3.4
    sample_report["summary"]["blast_f1_gain_vs_raw_grep_pct"] = -1.2
    neg_md = render_benchmark_markdown(sample_report)
    assert "+-" not in neg_md
    assert "-3.4 percentage points" in neg_md

    # Round-3 QA Findings 6 & 7: Python 3.10 `tomllib=None` fallback + grep cap scoring alignment
    import ctx.benchmark as bench_mod

    sample_toml = '[project]\nname = "demo"\n\n[project.scripts]\nctx = "ctx.cli:cli"\nctx-mcp = "ctx.mcp_server:main"\n\n[tool.pytest]\naddopts = "-q"\n'
    orig_tomllib = bench_mod.tomllib
    try:
        bench_mod.tomllib = None
        assert bench_mod._extract_pyproject_script_names(sample_toml) == ["ctx", "ctx-mcp"]
    finally:
        bench_mod.tomllib = orig_tomllib

    files_for_cap = {
        "a_first.py": "\n".join(f"hit_token_{i}" for i in range(5)),
        "z_beyond_cap.py": "hit_token_late",
    }
    import re as _re

    emitted_text, scored_files = bench_mod._execute_regex_grep(
        files_for_cap,
        _re.compile(r"hit_token"),
        include_tests=True,
        only_tests=False,
        max_lines=3,
    )
    assert len(emitted_text.splitlines()) == 3
    assert scored_files == {"a_first.py"}
    assert "z_beyond_cap.py" not in scored_files
