"""Regression tests for Phase 30.8 AI-Server Live Dogfood Hardening Gate (Issue #73)."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ctx import api
from ctx.config import Config, detect_provider, probe_provider_connectivity
from ctx.generator import generate_tree
from ctx.ignore import load_ignore_patterns
from ctx.init import init_project
from ctx.llm import (
    DEFAULT_PROMPT_TEMPLATES,
    FileSummary,
    LLMResult,
    OpenAIClient,
    SubdirSummary,
    _call_with_retries,
)
from ctx.manifest import read_manifest
from ctx.preflight import _probe_local_models, run_preflight
from ctx.sdk import CtxProject
from ctx.server import app
from ctx.stats_board import _global_stats_path


class _RealRefreshFakeClient:
    model = "fake-dogfood-model"

    def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
        return [
            LLMResult(text=f"{f['name']}: Summary for {f['name']}.", input_tokens=4, output_tokens=2)
            for f in files
        ]

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        return LLMResult(
            text=f"# {dir_path.as_posix()}\n\nDirectory summary for {dir_path.name or 'root'}.\n",
            input_tokens=5,
            output_tokens=3,
        )


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), capture_output=True, check=True)
    (path / "app.py").write_text("def main() -> int:\n    return 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(path), capture_output=True, check=True)
    return path


def test_d1_init_tier1_leaves_tree_fresh_ignores_ctx_and_reset_preserves_ctx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_git_repo(tmp_path / "tier1_repo")
    cfg = Config(provider="ollama", model="fake-dogfood-model", api_key="not-needed")
    monkeypatch.setattr(
        api,
        "_build_generation_runtime",
        lambda root, **_kw: (cfg, load_ignore_patterns(root), _RealRefreshFakeClient()),
    )

    init_project(repo)

    # Immediately after Tier 1 ctx init, check and verify must both report 100% fresh and valid
    health = api.check(repo, check_exit=True)
    assert health.summary["stale"] == 0
    assert health.summary["missing"] == 0
    assert all(d["path"] != ".ctx" for d in health.directories)

    verified = api.check(repo, verify=True, check_exit=True)
    assert verified.summary["invalid"] == 0
    assert verified.summary["stale"] == 0

    # D8 check as well: redundant "app.py: " prefix stripped from rendered manifest
    root_manifest = read_manifest(repo)
    assert root_manifest is not None
    assert "- **app.py** — Summary for app.py." in root_manifest.body
    assert "app.py: Summary" not in root_manifest.body

    # ctx reset removes source-tree manifests without deleting .ctx/CONTEXT.md
    reset_res = api.reset(repo, yes=True)
    assert reset_res.manifests_removed == 1
    assert not (repo / "CONTEXT.md").exists()
    assert (repo / ".ctx" / "CONTEXT.md").is_file()


def test_d2_detect_provider_skips_embedding_models_and_preflight_uses_detected_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps(
        {"data": [{"id": "nomic-embed-text:latest"}, {"id": "qwen2.5:7b-instruct"}]}
    ).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        detected = detect_provider()
    assert detected == ("ollama", "qwen2.5:7b-instruct")

    seen_models: list[str] = []

    def _capture_quality(config: Config) -> tuple[bool, str | None]:
        seen_models.append(config.resolved_model())
        return True, None

    with patch("ctx.preflight.detect_provider", return_value=("ollama", "qwen2.5:7b-instruct")), \
         patch("ctx.preflight._probe_local_models", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", side_effect=_capture_quality):
        result = run_preflight(str(tmp_path))

    assert result.ready is True
    assert result.model == "qwen2.5:7b-instruct"
    assert seen_models == ["qwen2.5:7b-instruct"]

    # Explicit model in .ctxconfig still takes precedence over detected_model
    (tmp_path / ".ctxconfig").write_text("provider: ollama\nmodel: mistral:7b\n", encoding="utf-8")
    seen_models.clear()
    with patch("ctx.preflight.detect_provider", return_value=("ollama", "qwen2.5:7b-instruct")), \
         patch("ctx.preflight._probe_local_models", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", side_effect=_capture_quality):
        result_explicit = run_preflight(str(tmp_path))
    assert result_explicit.model == "mistral:7b"
    assert seen_models == ["mistral:7b"]


def test_d3_probe_connectivity_normalizes_v1_base_url_and_custom_base_url_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested_urls: list[str] = []
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({"data": [{"id": "gpt-4o-mini"}]}).encode("utf-8")

    def _fake_urlopen(req_or_url, timeout=10):
        url = req_or_url.full_url if hasattr(req_or_url, "full_url") else str(req_or_url)
        requested_urls.append(url)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        ok1, _ = probe_provider_connectivity("openai", "sk-test", "http://127.0.0.1:4000/v1")
        ok2, _ = probe_provider_connectivity("openai", "sk-test", "http://127.0.0.1:4000/v1/")
        ok3, _ = probe_provider_connectivity("openai", "sk-test", "http://127.0.0.1:4000")
        ok4, _ = _probe_local_models("http://127.0.0.1:11434/v1")

    assert (ok1, ok2, ok3, ok4) == (True, True, True, True)
    assert requested_urls == [
        "http://127.0.0.1:4000/v1/models",
        "http://127.0.0.1:4000/v1/models",
        "http://127.0.0.1:4000/v1/models",
        "http://127.0.0.1:11434/v1/models",
    ]

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CTX_BASE_URL", "http://127.0.0.1:4000/v1")
    with patch("ctx.preflight.detect_provider", return_value=("openai", None)), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(False, "Connection error: refused")):
        res = run_preflight(str(tmp_path))

    conn = next(c for c in res.checks if c.name == "connectivity")
    assert conn.status == "fail"
    assert conn.fix is not None
    assert "http://127.0.0.1:4000/v1" in conn.fix


def test_d4_local_mid_directory_batch_disable_plain_single_file_and_timeout_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ctx.generator import _DEFAULT_LOCAL_PARALLEL_DIRS

    assert _DEFAULT_LOCAL_PARALLEL_DIRS == 1

    calls: list[dict] = []
    responses = [
        # 1st call: 4-file batch [0:4] returns non-JSON -> disables batching & falls back to 4 single-file calls
        "not a json array",
        "Summary 0",
        "Summary 1",
        "Summary 2",
        "Summary 3",
        # Remaining 2 files [4] and [5] must run 1-by-1 immediately; plain sentence on 1-file chunk accepted!
        "Plain sentence summary 4",
        '["JSON summary 5"]',
    ]

    def _fake_create(**kwargs):
        calls.append(kwargs)
        text = responses[len(calls) - 1]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4),
        )

    monkeypatch.setattr(
        "ctx.llm.OpenAI",
        lambda **_kw: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_fake_create))),
    )

    client = OpenAIClient(
        Config(provider="ollama", model="qwen2.5:7b-instruct", api_key="not-needed"),
        DEFAULT_PROMPT_TEMPLATES,
    )
    files = [{"name": f"f{i}.py", "content": f"x = {i}"} for i in range(6)]
    results = client.summarize_files(Path("src/ctx"), files)

    assert [r.text for r in results] == [
        "Summary 0",
        "Summary 1",
        "Summary 2",
        "Summary 3",
        "Plain sentence summary 4",
        "JSON summary 5",
    ]
    assert client.local_batch_fallbacks == 1
    assert len(calls) == 7

    # Local APITimeoutError retries are capped instead of retrying 5 x 300s
    timeout_attempts = 0
    monkeypatch.setattr("ctx.llm.time.sleep", lambda _d: None)

    def _always_timeout():
        nonlocal timeout_attempts
        timeout_attempts += 1
        raise openai.APITimeoutError(request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"))

    with pytest.raises(RuntimeError, match=r"\[transient, retries exhausted\]"):
        _call_with_retries("OpenAI", _always_timeout, is_local=True)
    assert timeout_attempts == 2


def test_d5_d6_subcommand_output_json_export_collision_and_check_exit_json_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    repo = _make_git_repo(tmp_path / "cli_repo")

    # Stale/missing repo: trailing `--output json` on `ctx check --check-exit` must parse AND exit 1
    res_fail = runner.invoke(cli_module.cli, ["check", str(repo), "--check-exit", "--output", "json"])
    assert res_fail.exit_code == 1
    env_fail = json.loads(res_fail.output)
    assert env_fail["errors"][0]["code"] == "stale_manifests"

    # Also via CTX_OUTPUT=json env var (matches .github/workflows/ctx-check.yml)
    res_env_fail = runner.invoke(
        cli_module.cli, ["check", str(repo), "--check-exit"], env={"CTX_OUTPUT": "json"}
    )
    assert res_env_fail.exit_code == 1

    # `ctx export <repo> --depth 1 --capsule --output json` must emit JSON to stdout and NOT write ./json
    monkeypatch.chdir(tmp_path)
    res_cap = runner.invoke(
        cli_module.cli, ["export", str(repo), "--depth", "1", "--capsule", "--output", "json"]
    )
    assert res_cap.exit_code == 0
    assert not (tmp_path / "json").exists()
    cap_env = json.loads(res_cap.output)
    assert cap_env["status"] == "success"
    assert cap_env["data"]["repo_name"] == "cli_repo"

    # `--out-file` writes to disk cleanly
    out_file = tmp_path / "capsule.json"
    res_out = runner.invoke(
        cli_module.cli, ["export", str(repo), "--depth", "1", "--capsule", "--out-file", str(out_file)]
    )
    assert res_out.exit_code == 0
    assert out_file.is_file()


def test_d7_tier2_check_export_and_http_serve(tmp_path: Path) -> None:
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    repo = _make_git_repo(tmp_path / "tier2_repo")
    (repo / "AGENTS.md").write_text("# AGENTS\n\nRepo rules.\n", encoding="utf-8")

    init_project(repo, tier2=True)

    # Health, verify, and stats recognize Tier 2 repo as fresh
    health = api.check(repo, check_exit=True)
    assert health.summary["fresh"] == 1
    assert health.summary["stale"] == 0
    assert health.summary["missing"] == 0

    verified = api.check(repo, verify=True, check_exit=True)
    assert verified.summary["invalid"] == 0

    stats = api.check(repo, stats=True)
    assert stats.summary["covered"] == 1
    assert stats.summary["missing"] == 0

    # Export without --capsule returns depth-appropriate Tier 2 map
    exp1 = api.export_context(repo, depth=1)
    assert exp1.manifests_exported == 1
    assert "tier: CONTEXT-1" in exp1.content

    # HTTP server serves Tier 2 root context and blocks internal .ctx path
    app.state.served_root = repo.resolve()
    client = TestClient(app)
    r_dot = client.get("/mcp/context/.")
    assert r_dot.status_code == 200
    assert "mode: tier2" in r_dot.json()["content"]

    r_root = client.get("/mcp/context")
    assert r_root.status_code == 200
    assert "mode: tier2" in r_root.json()["content"]

    r_internal = client.get("/mcp/context/.ctx")
    assert r_internal.status_code == 404

    # Adding a new public function marks Tier 2 check as stale (exit 1 with --check-exit)
    (repo / "app.py").write_text(
        "def main() -> int:\n    return 0\n\ndef added_api() -> str:\n    return 'v2'\n",
        encoding="utf-8",
    )
    stale_check = runner.invoke(cli_module.cli, ["check", str(repo), "--check-exit", "--output", "json"])
    assert stale_check.exit_code == 1
    stale_env = json.loads(stale_check.output)
    assert stale_env["data"]["summary"]["stale"] == 1


def test_d8_prompt_examples_are_json_arrays_without_filename_prefixes() -> None:
    sys_prompt = DEFAULT_PROMPT_TEMPLATES["file_summary_system"]
    assert "- __init__.py:" not in sys_prompt
    assert "- config.py:" not in sys_prompt
    assert "file name" in sys_prompt.lower() or "filename" in sys_prompt.lower()


def test_d9_sdk_hook_telemetry_alias_and_standalone_is_stale_without_skeleton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_git_repo(tmp_path / "sdk_repo")
    init_project(repo, tier2=True)
    (repo / ".ctx" / "hook_log.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "timestamp": "2026-10-30T00:00:00Z",
                        "trigger": "post-commit",
                        "duration_ms": 15,
                        "success": True,
                        "error": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proj = CtxProject.load(repo, walk_parents=False)
    assert proj.hook_telemetry == proj.hook_runs
    assert len(proj.hook_telemetry) == 1

    # Simulate standalone SDK usage where ctx.skeleton (and pathspec) is unavailable
    monkeypatch.setitem(sys.modules, "ctx.skeleton", None)
    assert proj.is_stale() is False

    (repo / ".ctx" / "CONTEXT-0.md").unlink()
    assert proj.is_stale() is True


def test_d10_global_stats_isolated_via_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Under pytest conftest, _global_stats_path() must NOT point to ~/.ctx/run_stats.json
    default_under_pytest = _global_stats_path()
    assert default_under_pytest != (Path.home() / ".ctx" / "run_stats.json")

    custom = tmp_path / "custom_global" / "stats.json"
    monkeypatch.setenv("CTX_GLOBAL_STATS_PATH", str(custom))
    assert _global_stats_path() == custom
