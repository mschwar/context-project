"""Tests for Phase 34 (Type 1 Jev System-One heads) and Phase 31 (Tier 2 invariants & structured outputs)."""

from __future__ import annotations

import copy
import io
import json
import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ctx.cli import cli
from ctx.config import Config
from ctx.init import init_project
from ctx.invariants import load_cached_invariants, synthesize_tier2_invariants
from ctx.jev import (
    BUILTIN_HEADS,
    GOLD_EVAL_CASES,
    decide,
    evaluate_heads,
    list_head_ids,
    noul_decision_from_prob,
    run_jev,
    validate_head,
)
from ctx.llm import (
    LLMResult,
    OpenAIClient,
    _extract_json_array,
    build_file_summaries_json_schema,
    clear_structured_output_capability_cache,
    get_structured_output_capability,
)
from ctx.mcp_server import CtxMCPServer
from ctx.skeleton import extract_skeleton


def test_jev_head_validation_and_authority_ceiling() -> None:
    assert set(list_head_ids()) == {
        "invariant_drift_material",
        "operational_surface_exposure",
        "subsystem_arch_role",
    }
    for hid, raw in BUILTIN_HEADS.items():
        assert validate_head(raw, expected_id=hid) == []

    # Authority head with ceiling above ADVISORY must be rejected!
    illegal_auth = copy.deepcopy(BUILTIN_HEADS["operational_surface_exposure"])
    illegal_auth["ceiling"] = "ROUTING"
    auth_errs = validate_head(illegal_auth)
    assert any("permanent ceiling ADVISORY" in e for e in auth_errs)

    # Unpinned model outside SHADOW must be rejected!
    unpinned = copy.deepcopy(BUILTIN_HEADS["subsystem_arch_role"])
    unpinned["provider"]["model"] = "jev-latest"
    pin_errs = validate_head(unpinned)
    assert any("model aliases are only permitted in SHADOW" in e for e in pin_errs)


def test_noul_decision_from_prob_threshold_and_confidence() -> None:
    out_true, conf_true = noul_decision_from_prob(0.80, 0.45)
    assert out_true is True
    assert conf_true == pytest.approx(0.5 + 0.5 * (0.80 - 0.45) / (1.0 - 0.45))

    out_false, conf_false = noul_decision_from_prob(0.20, 0.45)
    assert out_false is False
    assert conf_false == pytest.approx(0.5 + 0.5 * (0.45 - 0.20) / 0.45)


def test_jev_gold_eval_code_provider_100_percent() -> None:
    import inspect
    import ctx.jev as jev_mod

    # Public PyPI hygiene: zero hardcoded private 1Password `op://` vault URIs in source
    assert "op://" not in inspect.getsource(jev_mod)

    assert len(GOLD_EVAL_CASES) == 18
    report = evaluate_heads(provider="code")
    assert report["total"] == 18
    assert report["evaluated"] == 18
    assert report["abstained"] == 0
    assert report["accuracy"] == 1.0
    assert "pre_rule_hits" in report
    assert "live_model_calls" in report
    assert report["live_model_calls"] == 0
    assert report["total_input_tokens"] == 0
    assert report["total_cost_usd"] == 0.0

    # Segment-level path matching: "cli" inside "api_client", "ui" inside "query_builder", "git" inside "digit_parser"
    for tricky_path, expected_role in (
        ("src/api_client", "adapter_integration"),
        ("src/query_builder", "core_domain"),
        ("src/digit_parser", "core_domain"),
    ):
        dec = decide(
            ["subsystem_arch_role"],
            {
                "path": tricky_path,
                "file_count": 3,
                "languages": ["Python"],
                "key_symbols": ["mod.py:fn run"],
                "internal_deps": [],
                "external_deps": ["httpx"] if "api_client" in tricky_path else [],
                "operational_surface_kinds": [],
            },
            provider="code",
            record_trace=False,
        )
        assert dec["decisions"][0]["effective_output"] == expected_role


def test_jev_systemone_http_wire_batching_error_hygiene_and_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-secret-do-not-leak")
    monkeypatch.setenv("CTX_JEV", "auto")

    captured_requests: list[tuple[str, dict[str, str], dict[str, object]]] = []

    class _FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._raw = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._raw

        def __enter__(self) -> "_FakeHTTPResponse":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def _fake_urlopen(req, timeout=15.0):
        headers = {k.lower(): v for k, v in req.header_items()}
        body = json.loads(req.data.decode("utf-8"))
        captured_requests.append((req.full_url, headers, body))
        return _FakeHTTPResponse(
            {
                "model": "jev-1.13.0",
                "answers": {
                    "subsystem_arch_role": {
                        "choice": "core_domain",
                        "probabilities": {
                            "entrypoint_interface": 0.05,
                            "core_domain": 0.82,
                            "adapter_integration": 0.08,
                            "shared_utility": 0.03,
                            "verification_tooling": 0.01,
                            "docs_governance": 0.01,
                        },
                        "confidence": 0.82,
                    },
                    "custom_urgency_score": {
                        "score": 2.4,
                        "probabilities": {"0": 0.05, "1": 0.10, "2": 0.25, "3": 0.60},
                    },
                },
                "usage": {"input_tokens": 120},
            }
        )

    score_head = {
        "id": "custom_urgency_score",
        "version": "1.0.0",
        "type": "score",
        "authority": False,
        "tier": "judge",
        "promotion_state": "ADVISORY",
        "ceiling": "ADVISORY",
        "instructions": "Score subsystem urgency from 0 to 3.",
        "criteria": [
            "0: No action required",
            "1: Low urgency",
            "2: Moderate urgency",
            "3: Immediate attention",
        ],
        "state_keys": ["path", "file_count"],
        "thresholds": {"act_min_confidence": 0.50},
        "provider": {"name": "jev", "model": "jev-1.13.0"},
        "fallback": "deliberate",
    }
    assert validate_head(score_head) == []
    role_head = copy.deepcopy(BUILTIN_HEADS["subsystem_arch_role"])

    state = {
        "path": "src/compiler",
        "file_count": 6,
        "languages": ["Python"],
        "key_symbols": ["graph.py:fn build_graph"],
        "internal_deps": ["app.models"],
        "external_deps": [],
        "operational_surface_kinds": [],
    }

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        batch_out = run_jev([role_head, score_head], state, root=tmp_path, skip_pre_rule=True)

    assert len(captured_requests) == 1
    url, headers, wire_body = captured_requests[0]
    assert url.endswith("/v1/systemone")
    assert headers["authorization"] == "Bearer ts-test-secret-do-not-leak"
    assert wire_body["model"] == "jev-1.13.0"
    assert set(wire_body["questions"].keys()) == {"subsystem_arch_role", "custom_urgency_score"}

    assert batch_out["subsystem_arch_role"]["output"] == "core_domain"
    assert batch_out["subsystem_arch_role"]["input_tokens"] == 60
    assert batch_out["custom_urgency_score"]["output"] == 3
    assert batch_out["custom_urgency_score"]["expected_score"] == pytest.approx(2.4, rel=1e-3)
    assert batch_out["custom_urgency_score"]["input_tokens"] == 60

    # Governed decide() writes trace to .ctx-cache/jev_decisions.jsonl
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        decided = decide(["subsystem_arch_role"], state, root=tmp_path, provider="jev")
    assert decided["result"] == "DECIDED"
    assert decided["decisions"][0]["effective_output"] == "core_domain"
    trace_file = tmp_path / ".ctx-cache" / "jev_decisions.jsonl"
    assert trace_file.is_file()
    trace_entry = json.loads(trace_file.read_text(encoding="utf-8").strip().splitlines()[0])
    assert trace_entry["head_id"] == "subsystem_arch_role"

    # HTTP 500 error body MUST NOT leak into abstain_reason!
    def _fake_urlopen_500(req, timeout=15.0):
        raise urllib.error.HTTPError(
            req.full_url,
            500,
            "Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b"SENSITIVE_UPSTREAM_BODY_SECRET_XYZ"),
        )

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_500):
        err_out = run_jev([role_head], state, root=tmp_path, skip_pre_rule=True)
    assert err_out["subsystem_arch_role"]["abstained"] is True
    assert err_out["subsystem_arch_role"]["abstain_reason"] == "JEV_UNAVAILABLE: HTTP 500"
    assert "SENSITIVE_UPSTREAM_BODY_SECRET_XYZ" not in json.dumps(err_out)

    # CTX_JEV=off disables live HTTP calls and falls back cleanly to deterministic `code`
    monkeypatch.setenv("CTX_JEV", "off")
    off_decided = decide(["subsystem_arch_role"], state, root=tmp_path, provider="jev", record_trace=False)
    assert "CTX_JEV=off" in off_decided["decisions"][0]["abstain_reason"]
    assert off_decided["decisions"][0]["effective_output"] == "core_domain"
    assert off_decided["decisions"][0]["tier"] == "code"


def test_cli_jev_and_mcp_jev(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("CTX_JEV", "off")
    runner = CliRunner()

    res_heads = runner.invoke(cli, ["jev", "heads", str(tmp_path), "--output", "json"])
    assert res_heads.exit_code == 0, res_heads.output
    heads_env = json.loads(res_heads.output)
    assert heads_env["data"]["count"] == 3

    state_file = tmp_path / "surface_state.json"
    state_file.write_text(
        json.dumps(
            {
                "kind": "cli_command",
                "name": "ctx _hook",
                "file": "src/ctx/cli.py",
                "detail": "hidden=true; flags: --trigger",
            }
        ),
        encoding="utf-8",
    )
    res_decide = runner.invoke(
        cli,
        [
            "jev",
            "decide",
            str(tmp_path),
            "--head",
            "operational_surface_exposure",
            "--state",
            f"@{state_file}",
            "--provider",
            "code",
            "--no-trace",
            "--output",
            "json",
        ],
    )
    assert res_decide.exit_code == 0, res_decide.output
    dec_env = json.loads(res_decide.output)
    assert dec_env["data"]["decisions"][0]["effective_output"] == "internal_plumbing"

    res_eval = runner.invoke(cli, ["jev", "eval", str(tmp_path), "--provider", "code", "--output", "json"])
    assert res_eval.exit_code == 0, res_eval.output
    eval_env = json.loads(res_eval.output)
    assert eval_env["data"]["accuracy"] == 1.0

    # MCP ctx_jev tool
    capsys.readouterr()
    server = CtxMCPServer(tmp_path)
    server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "ctx_jev", "arguments": {"action": "eval", "provider": "code"}},
        }
    )
    mcp_eval = json.loads(capsys.readouterr().out.strip())
    assert not mcp_eval["result"].get("isError")
    assert json.loads(mcp_eval["result"]["content"][0]["text"])["accuracy"] == 1.0


def test_tier2_hybrid_invariant_synthesis_three_stage_gating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CTX_JEV", "off")  # deterministic judge fallback

    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n\nNever bypass lock fencing.\n", encoding="utf-8")
    pkg = tmp_path / "src" / "core"
    pkg.mkdir(parents=True)
    (pkg / "engine.py").write_text("class Engine:\n    def run(self) -> int:\n        return 1\n", encoding="utf-8")
    (pkg / "worker.py").write_text("from core.engine import Engine\ndef work() -> int:\n    return Engine().run()\n", encoding="utf-8")

    # Fallback gracefully when no LLM key is configured AND persist attempted=True so subsequent refreshes skip cleanly
    from ctx.api import refresh as api_refresh

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    init_res = init_project(tmp_path, tier2=True, synthesize=True)
    assert init_res["mode"] == "tier2"
    assert (tmp_path / ".ctx" / "CONTEXT-0.md").is_file()
    no_key_cache = load_cached_invariants(tmp_path)
    assert no_key_cache is not None
    assert no_key_cache["attempted"] is True
    assert no_key_cache["gate_action"] == "no_provider_configured"
    assert init_res.get("warnings")

    # Second refresh on unchanged commit with no API key MUST skip (`dirs_processed == 0`) instead of looping on missing_synth_cache
    repeat_refresh = api_refresh(tmp_path)
    assert repeat_refresh.strategy == "tier2"
    assert repeat_refresh.dirs_processed == 0
    assert repeat_refresh.dirs_skipped >= 1

    # Remove attempted fallback cache so the mocked Type-II LLM test below exercises fresh synthesis
    (tmp_path / ".ctx" / "invariants.json").unlink(missing_ok=True)

    # Now mock LLM client `complete_json` to verify the 3-stage Determinism Gradient
    llm_calls: list[dict[str, object]] = []

    class _FakeLLMClient:
        model = "gpt-4o-mini"

        def complete_json(
            self,
            system_prompt: str,
            user_prompt: str,
            *,
            json_schema: dict | None = None,
            max_tokens: int = 2048,
        ) -> LLMResult:
            schema_name = (json_schema or {}).get("json_schema", {}).get("name", "unknown")
            llm_calls.append({"schema": schema_name, "prompt_len": len(user_prompt)})
            payload = {
                "invariants": [
                    {
                        "category": "invariant",
                        "scope": ".ctx/",
                        "statement": "All .ctx/ mutations MUST hold CtxLock and verify generation fencing before unlink or replace.",
                    },
                    {
                        "category": "contract",
                        "scope": "src/core",
                        "statement": "worker.work delegates execution strictly through Engine.run.",
                    },
                ]
            }
            return LLMResult(text=json.dumps(payload), input_tokens=220, output_tokens=100)

    fake_cfg = Config(provider="openai", model="gpt-4o-mini", api_key="sk-test")

    with (
        patch("ctx.invariants.load_config", return_value=fake_cfg),
        patch("ctx.llm.create_client", return_value=_FakeLLMClient()),
    ):
        # 1. Initial synthesis -> calls Type-II LLM once
        sk1 = extract_skeleton(tmp_path)
        res1 = synthesize_tier2_invariants(tmp_path, sk1)
        assert res1.gate_action == "synthesized"
        assert res1.tokens_used == 320
        assert len(llm_calls) == 1

        # 2. Identical structure -> Stage 1 (`code`) short-circuits with 0 Jev & 0 LLM calls!
        res2 = synthesize_tier2_invariants(tmp_path, sk1)
        assert res2.gate_action == "cached_structural_match"
        assert res2.tokens_used == 0
        assert len(llm_calls) == 1

        # 3. Minor 1-file additive formatting function (no boundary doc, no new subsystem, no new public surface)
        # -> Stage 2 (`judge`) classifies invariant_drift_material == False -> 0 Type-II LLM calls!
        (pkg / "worker.py").write_text(
            "from core.engine import Engine\n"
            "def format_sparkline() -> str:\n    return ''\n"
            "def work() -> int:\n    return Engine().run()\n",
            encoding="utf-8",
        )
        sk_minor = extract_skeleton(tmp_path)
        assert sk_minor.structural_hash != sk1.structural_hash
        res3 = synthesize_tier2_invariants(tmp_path, sk_minor)
        assert res3.gate_action == "jev_skipped_non_material"
        assert res3.tokens_used == 0
        assert len(llm_calls) == 1
        assert load_cached_invariants(tmp_path)["structural_hash"] == sk_minor.structural_hash

        # 4. Authority doc change (`AGENTS.md` updated) -> Stage 2 (`judge`) flags material drift -> Stage 3 LLM runs!
        (tmp_path / "AGENTS.md").write_text(
            "# AGENTS\n\nNever bypass lock fencing. Enforce ADVISORY ceiling on authority heads.\n",
            encoding="utf-8",
        )
        sk_material = extract_skeleton(tmp_path)
        res4 = synthesize_tier2_invariants(tmp_path, sk_material)
        assert res4.gate_action == "synthesized"
        assert res4.tokens_used == 320
        assert len(llm_calls) == 2

        # End-to-end `init_project(..., force=True, tier2=True, synthesize=True)` embeds invariants into CONTEXT-{0,1}.md
        init_project(tmp_path, force=True, tier2=True, synthesize=True)

    c0_text = (tmp_path / ".ctx" / "CONTEXT-0.md").read_text(encoding="utf-8")
    c1_text = (tmp_path / ".ctx" / "CONTEXT-1.md").read_text(encoding="utf-8")
    assert "## Synthesized Cross-Module Invariants & Footguns" in c0_text
    assert "generation fencing" in c0_text
    assert "## Synthesized Cross-Module Invariants & Footguns" in c1_text
    assert "Engine.run" in c1_text


def test_structured_output_json_schema_capability_and_400_fallback() -> None:
    clear_structured_output_capability_cache()
    schema = build_file_summaries_json_schema(expected_count=2)
    assert schema["type"] == "json_schema"
    inner = schema["json_schema"]
    assert inner["strict"] is True
    assert inner["schema"]["properties"]["summaries"]["minItems"] == 2

    # _extract_json_array parses both `{"summaries": [...]}` and bare `[...]`
    wrapped = '{"summaries": ["First.", "Second."]}'
    parsed = _extract_json_array(wrapped)
    assert parsed == ["First.", "Second."]

    # OpenAIClient uses response_format in auto mode and caches True on success
    cfg_ok = Config(
        provider="ollama",
        model="qwen2.5-coder:7b",
        api_key="local",
        base_url="http://127.0.0.1:11434/v1",
        structured_outputs="auto",
    )
    seen_kwargs: list[dict[str, object]] = []

    def _create_ok(**kwargs):
        seen_kwargs.append(kwargs)
        msg = SimpleNamespace(content='{"summaries": ["Clean structured summary."]}')
        usage = SimpleNamespace(prompt_tokens=25, completion_tokens=15)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)

    fake_openai_client = MagicMock()
    fake_openai_client.chat.completions.create.side_effect = _create_ok
    with patch("ctx.llm._get_openai_cls", return_value=MagicMock(return_value=fake_openai_client)):
        client = OpenAIClient(cfg_ok, cfg_ok.prompts)
        results = client.summarize_files(
            Path("."),
            [{"name": "a.py", "content": "def a(): pass\n", "language": "Python", "metadata": {}}],
        )

    assert results[0].text == "Clean structured summary."
    assert "response_format" in seen_kwargs[0]
    assert get_structured_output_capability(cfg_ok) is True

    # OpenAIClient seamlessly retries without response_format on 400 unsupported response_format error
    cfg_legacy = Config(
        provider="lmstudio",
        model="legacy-local-model",
        api_key="local",
        base_url="http://127.0.0.1:1234/v1",
        structured_outputs="auto",
    )
    legacy_calls: list[dict[str, object]] = []

    class _FakeBadRequestError(Exception):
        status_code = 400

    def _create_fallback(**kwargs):
        legacy_calls.append(kwargs)
        if "response_format" in kwargs:
            raise _FakeBadRequestError("Invalid parameter: response_format json_schema is not supported")
        msg = SimpleNamespace(content='["Fallback prompt summary."]')
        usage = SimpleNamespace(prompt_tokens=20, completion_tokens=10)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)

    fake_legacy_client = MagicMock()
    fake_legacy_client.chat.completions.create.side_effect = _create_fallback
    with patch("ctx.llm._get_openai_cls", return_value=MagicMock(return_value=fake_legacy_client)):
        client2 = OpenAIClient(cfg_legacy, cfg_legacy.prompts)
        res2 = client2.summarize_files(
            Path("."),
            [{"name": "b.py", "content": "def b(): pass\n", "language": "Python", "metadata": {}}],
        )

    assert res2[0].text == "Fallback prompt summary."
    assert len(legacy_calls) == 2
    assert "response_format" in legacy_calls[0]
    assert "response_format" not in legacy_calls[1]
    assert get_structured_output_capability(cfg_legacy) is False

    # Explicit structured_outputs="on" MUST override a cached False capability entry
    cfg_forced = Config(
        provider="lmstudio",
        model="legacy-local-model",
        api_key="local",
        base_url="http://127.0.0.1:1234/v1",
        structured_outputs="on",
    )
    forced_calls: list[dict[str, object]] = []

    def _create_forced_ok(**kwargs):
        forced_calls.append(kwargs)
        msg = SimpleNamespace(content='{"summaries": ["Forced structured summary."]}')
        usage = SimpleNamespace(prompt_tokens=15, completion_tokens=8)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)

    fake_forced_client = MagicMock()
    fake_forced_client.chat.completions.create.side_effect = _create_forced_ok
    with patch("ctx.llm._get_openai_cls", return_value=MagicMock(return_value=fake_forced_client)):
        client3 = OpenAIClient(cfg_forced, cfg_forced.prompts)
        res3 = client3.summarize_files(
            Path("."),
            [{"name": "c.py", "content": "def c(): pass\n", "language": "Python", "metadata": {}}],
        )
    assert res3[0].text == "Forced structured summary."
    assert "response_format" in forced_calls[0]


def test_round2_qa_invariants_retry_cumulative_drift_disable_and_head_confinement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression coverage for Round-2 QA findings 1, 2, 3, and 6."""
    from ctx.api import refresh as api_refresh
    from ctx.jev import load_head

    monkeypatch.setenv("CTX_JEV", "off")
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n\nRule 1: Keep locks fenced.\n", encoding="utf-8")
    pkg = tmp_path / "src" / "core"
    pkg.mkdir(parents=True)
    (pkg / "engine.py").write_text("class Engine:\n    def run(self) -> int:\n        return 1\n", encoding="utf-8")

    # Finding 6: Jev head_id path traversal MUST be rejected before touching disk
    outside_secret = tmp_path.parent / "outside_secret_probe.json"
    outside_secret.write_text('{"secret": true}\n', encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="Invalid Jev head ID"):
            load_head("../../../outside_secret_probe", tmp_path)
        with pytest.raises(ValueError, match="Invalid Jev head ID"):
            load_head("../outside_secret_probe", tmp_path)
    finally:
        outside_secret.unlink(missing_ok=True)

    # Finding 6b: Malformed custom head file does NOT crash `ctx jev heads` or Tier 2 synthesis
    custom_heads = tmp_path / ".ctx" / "heads"
    custom_heads.mkdir(parents=True)
    (custom_heads / "broken_custom.json").write_text("{not valid json", encoding="utf-8")
    (custom_heads / "invariant_drift_material.json").write_text('{"id": "wrong"}', encoding="utf-8")

    runner = CliRunner()
    heads_res = runner.invoke(cli, ["jev", "heads", str(tmp_path)])
    assert heads_res.exit_code == 0, heads_res.output
    assert "Warning: Skipped invalid custom Jev head" in heads_res.output
    assert "invariant_drift_material" in heads_res.output  # fell back to valid builtin head!
    (custom_heads / "invariant_drift_material.json").unlink()

    # Set up Tier 2 repo and test Finding 1 (transient failure retry + cumulative multi-commit drift),
    # Finding 2 (surfaced warnings), and Finding 3 (turning synthesis OFF).
    call_counter = {"count": 0, "should_fail": False}

    class _ControllableLLM:
        model = "gpt-4o-mini"

        def complete_json(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResult:
            call_counter["count"] += 1
            if call_counter["should_fail"]:
                raise RuntimeError("HTTP 503 upstream overloaded")
            payload = {
                "invariants": [
                    {
                        "category": "invariant",
                        "scope": "src/core",
                        "statement": f"Synthesized invariant generation #{call_counter['count']} covers current baseline.",
                    }
                ]
            }
            return LLMResult(text=json.dumps(payload), input_tokens=100, output_tokens=50)

    fake_cfg = Config(provider="openai", model="gpt-4o-mini", api_key="sk-test")
    with (
        patch("ctx.invariants.load_config", return_value=fake_cfg),
        patch("ctx.llm.create_client", return_value=_ControllableLLM()),
    ):
        init_project(tmp_path, force=True, tier2=True, synthesize=True)
        assert call_counter["count"] == 1

        # Material edit to AGENTS.md, but Type-II LLM suffers a transient 503 failure
        (tmp_path / "AGENTS.md").write_text(
            "# AGENTS\n\nRule 1: Keep locks fenced.\nRule 2: Retry transient synthesis failures.\n",
            encoding="utf-8",
        )
        call_counter["should_fail"] = True
        failed_ref = api_refresh(tmp_path)
        assert call_counter["count"] == 2
        assert len(failed_ref.warnings) == 1
        assert "HTTP 503" in failed_ref.warnings[0]

        # Next refresh with NO new code changes MUST retry because checked_structural_hash was NOT advanced!
        call_counter["should_fail"] = False
        recovered_ref = api_refresh(tmp_path)
        assert call_counter["count"] == 3
        assert recovered_ref.warnings == []
        assert "generation #3" in (tmp_path / ".ctx" / "CONTEXT-0.md").read_text(encoding="utf-8")

        # Cumulative slow drift across 2 small commits (+2 symbols then +2 symbols = +4 total vs synthesized_snapshot):
        # Commit A (+2 symbols < 4): skipped by Jev judge as non-material
        (pkg / "engine.py").write_text(
            "class Engine:\n    def run(self) -> int:\n        return 1\n"
            "def helper_one() -> int:\n    return 1\n"
            "def helper_two() -> int:\n    return 2\n",
            encoding="utf-8",
        )
        c1_ref = api_refresh(tmp_path)
        assert call_counter["count"] == 3
        assert c1_ref.tokens_used == 0

        # Commit B (+2 more symbols => +4 cumulative symbols vs generation #3 baseline!): MUST trigger rebuild!
        (pkg / "engine.py").write_text(
            "class Engine:\n    def run(self) -> int:\n        return 1\n"
            "def helper_one() -> int:\n    return 1\n"
            "def helper_two() -> int:\n    return 2\n"
            "def helper_three() -> int:\n    return 3\n"
            "def helper_four() -> int:\n    return 4\n",
            encoding="utf-8",
        )
        c2_ref = api_refresh(tmp_path)
        assert call_counter["count"] == 4
        assert c2_ref.tokens_used == 150
        assert "generation #4" in (tmp_path / ".ctx" / "CONTEXT-0.md").read_text(encoding="utf-8")

        # Finding 3: Disabling synthesis via `CTX_TIER2_SYNTHESIZE=0` turns synthesis OFF even though
        # metadata["synthesize_invariants"] was previously True, and strips synthesized section!
        monkeypatch.setenv("CTX_TIER2_SYNTHESIZE", "0")
        off_ref = api_refresh(tmp_path)
        assert call_counter["count"] == 4
        assert off_ref.dirs_processed >= 1
        meta_after_off = json.loads((tmp_path / ".ctx" / "metadata.json").read_text(encoding="utf-8"))
        assert meta_after_off["synthesize_invariants"] is False
        assert "## Synthesized Cross-Module Invariants & Footguns" not in (
            tmp_path / ".ctx" / "CONTEXT-0.md"
        ).read_text(encoding="utf-8")


def test_round3_qa_symlink_confinement_nan_confidence_budget_guardrails_and_surface_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression coverage for Round-3 Codex QA findings 1, 2, 3, and 4."""
    import os
    import types
    from ctx.api import refresh as api_refresh
    from ctx.init import init_project
    from ctx.jev import append_decision_traces, decide, list_head_ids, load_head

    # Finding 1: Symlinks escaping `root` for `.ctx-cache`, `jev_decisions.jsonl`, and `.ctx/heads` MUST fail closed
    repo = tmp_path / "confined_repo"
    outside = tmp_path / "outside_dir"
    repo.mkdir()
    outside.mkdir()
    (outside / "evil_head.json").write_text('{"id": "evil_head"}', encoding="utf-8")

    (repo / ".ctx").mkdir()
    (repo / ".ctx" / "heads").symlink_to(outside, target_is_directory=True)
    assert "evil_head" not in list_head_ids(repo)
    with pytest.raises(ValueError, match="symlink"):
        load_head("evil_head", repo)

    (repo / ".ctx-cache").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        append_decision_traces(repo, [{"head_id": "subsystem_arch_role"}])
    assert not (outside / "jev_decisions.jsonl").exists()

    # Finding 4: Malformed non-finite (`NaN`, `Inf`) or out-of-range (`2.0`, `-0.1`) confidence/probabilities MUST abstain
    state = {
        "path": "misc",
        "file_count": 3,
        "languages": ["Python"],
        "key_symbols": [],
        "internal_deps": [],
        "external_deps": [],
        "operational_surface_kinds": [],
    }
    for bad_conf in (float("nan"), float("inf"), 2.0, -0.1):
        raw = json.dumps(
            {
                "answers": {
                    "subsystem_arch_role": {
                        "choice": "docs_governance",
                        "confidence": bad_conf,
                    }
                },
                "usage": {"input_tokens": 5},
            },
            allow_nan=True,
        ).encode("utf-8")
        with (
            patch.dict(os.environ, {"CTX_JEV": "routing", "TYPESAFE_API_KEY": "ts-test-key"}),
            patch("urllib.request.urlopen", side_effect=lambda req, timeout=15.0, b=raw: io.BytesIO(b)),
        ):
            dec = decide(
                ["subsystem_arch_role"],
                state,
                provider="jev",
                record_trace=False,
            )["decisions"][0]
        assert dec["abstained"] is True
        assert dec["acted"] is False
        assert dec["route"].startswith("fallback:")

    # Finding 2 & Finding 3: Tier 2 surface/env hash updates + semantic synthesis token/USD guardrails
    t2_repo = tmp_path / "t2_budget_surface"
    (t2_repo / ".git" / "hooks").mkdir(parents=True)
    (t2_repo / "src" / "app").mkdir(parents=True)
    (t2_repo / "AGENTS.md").write_text("# AGENTS\n\nRule: Enforce budgets.\n", encoding="utf-8")
    (t2_repo / "src" / "app" / "cli.py").write_text(
        'import os, click\n\n@click.command()\n@click.option("--old", is_flag=True)\ndef run(old: bool) -> str:\n    return os.environ.get("APP_OLD", "")\n',
        encoding="utf-8",
    )
    init_project(t2_repo, tier2=True)
    c0_before = (t2_repo / ".ctx" / "CONTEXT-0.md").read_text(encoding="utf-8")
    assert "--old" in c0_before
    assert "APP_OLD" in c0_before

    # Renaming `--old` -> `--new` and `APP_OLD` -> `APP_NEW` MUST change structural_hash and refresh CONTEXT-0.md
    (t2_repo / "src" / "app" / "cli.py").write_text(
        'import os, click\n\n@click.command()\n@click.option("--new", is_flag=True)\ndef run(new: bool) -> str:\n    return os.environ.get("APP_NEW", "")\n',
        encoding="utf-8",
    )
    surf_ref = api_refresh(t2_repo)
    assert surf_ref.dirs_processed >= 1
    c0_after = (t2_repo / ".ctx" / "CONTEXT-0.md").read_text(encoding="utf-8")
    assert "--new" in c0_after and "--old" not in c0_after
    assert "APP_NEW" in c0_after and "APP_OLD" not in c0_after

    # Budget guardrails (`token_budget=1`, `max_tokens_per_run: 1`, `max_usd_per_run: 0.000001`) MUST block LLM call
    (t2_repo / ".ctxconfig").write_text(
        "provider: openai\nmodel: gpt-4.1-mini\nmax_tokens_per_run: 1\nmax_usd_per_run: 0.000001\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-budget-guard")
    monkeypatch.setenv("CTX_JEV", "off")
    llm_calls = {"n": 0}

    class _CountingStubClient:
        provider = "openai"
        model = "gpt-4.1-mini"

        def complete_json(self, *args, **kwargs):
            llm_calls["n"] += 1
            return types.SimpleNamespace(
                text='{"invariants": [{"category": "invariant", "scope": ".", "statement": "Should not have been called under 1-token budget."}]}',
                input_tokens=900,
                output_tokens=150,
            )

    with patch("ctx.llm.create_client", return_value=_CountingStubClient()):
        bud_ref = api_refresh(t2_repo, synthesize=True, token_budget=1)

    assert llm_calls["n"] == 0
    assert bud_ref.tokens_used == 0
    assert bud_ref.budget_exhausted is True
    assert bud_ref.budget_guardrail is not None


def test_round4_qa_parse_failure_billing_symlink_trace_graceful_and_tier2_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression coverage for Round-4 Claude QA findings 1, 2, 3, and 4."""
    import os
    import types
    from ctx.api import refresh as api_refresh
    from ctx.init import init_project
    from ctx.jev import decide

    monkeypatch.setenv("CTX_GLOBAL_STATS_PATH", str(tmp_path / "global_run_stats.json"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-round4")
    monkeypatch.setenv("CTX_JEV", "off")

    repo = tmp_path / "t2_round4"
    (repo / ".git" / "hooks").mkdir(parents=True)
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# AGENTS\n\nRule: Track every paid token.\n", encoding="utf-8")
    (repo / "src" / "pkg" / "core.py").write_text(
        "class CoreEngine:\n    def execute(self) -> int:\n        return 42\n",
        encoding="utf-8",
    )
    init_project(repo, tier2=True)

    # Finding 4: Tier 2 `--dry-run --synthesize` MUST report "." stale when synthesis is toggled on or uncached
    dry_plain = api_refresh(repo, dry_run=True)
    assert dry_plain.stale_directories == []
    dry_synth = api_refresh(repo, dry_run=True, synthesize=True)
    assert dry_synth.stale_directories == ["."]

    # Finding 1: Paid synthesis returning unparseable JSON MUST report actual tokens/cost,
    # enforce post-call guardrails, record run_stats.json, AND NOT re-bill on unchanged refresh!
    (repo / ".ctxconfig").write_text(
        "provider: openai\nmodel: gpt-4.1-mini\nmax_tokens_per_run: 3000\n",
        encoding="utf-8",
    )
    bad_calls = {"n": 0}

    class _UnparseablePaidClient:
        provider = "openai"
        model = "gpt-4.1-mini"

        def complete_json(self, *args, **kwargs):
            bad_calls["n"] += 1
            # Verify 256-token minimum output floor (never truncated to 1 token)
            assert kwargs.get("max_tokens", 0) >= 256
            return types.SimpleNamespace(
                text='{"invariants": [TRUNCATED_JSON',
                input_tokens=1500,
                output_tokens=2000,
            )

    with patch("ctx.llm.create_client", return_value=_UnparseablePaidClient()):
        first_fail = api_refresh(repo, synthesize=True)
        second_noop = api_refresh(repo, synthesize=True)

    assert bad_calls["n"] == 1
    assert first_fail.tokens_used == 3500
    assert first_fail.input_tokens == 1500
    assert first_fail.output_tokens == 2000
    assert first_fail.est_cost_usd > 0.0
    assert first_fail.budget_exhausted is True
    assert first_fail.budget_guardrail is not None
    assert "3,500 tokens used" in first_fail.budget_guardrail
    assert second_noop.tokens_used == 0

    run_stats_path = repo / ".ctx-cache" / "run_stats.json"
    assert run_stats_path.is_file()
    runs_data = json.loads(run_stats_path.read_text(encoding="utf-8"))
    assert runs_data["runs"][-1]["tokens_used"] == 3500
    assert runs_data["runs"][-1]["strategy"] == "tier2"

    # Finding 2: Symlinked `.ctx-cache` refuses trace writes outside `root` WITHOUT cancelling `decide()`
    sym_repo = tmp_path / "sym_trace_repo"
    outside_cache = tmp_path / "outside_trace_dir"
    sym_repo.mkdir()
    outside_cache.mkdir()
    (sym_repo / ".ctx-cache").symlink_to(outside_cache, target_is_directory=True)
    dec_env = decide(
        ["invariant_drift_material"],
        {
            "repo_name": "demo",
            "boundary_docs_changed": [],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": ["_helper"],
            "removed_symbols": [],
            "added_subsystems": [],
            "removed_subsystems": [],
            "changed_imports": [],
            "touched_subsystems": ["src/pkg"],
            "cycle_count_delta": 0,
            "files_changed_count": 1,
        },
        root=sym_repo,
        record_trace=True,
    )
    assert dec_env["result"] == "DECIDED"
    assert dec_env["decisions"][0]["effective_output"] is False
    assert not (outside_cache / "jev_decisions.jsonl").exists()
