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
    report = evaluate_heads(provider="code")
    assert report["total"] == len(GOLD_EVAL_CASES)
    assert report["evaluated"] == len(GOLD_EVAL_CASES)
    assert report["abstained"] == 0
    assert report["accuracy"] == 1.0
    assert report["total_input_tokens"] == 0
    assert report["total_cost_usd"] == 0.0


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

    # Fallback gracefully when no LLM key is configured
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    init_res = init_project(tmp_path, tier2=True, synthesize=True)
    assert init_res["mode"] == "tier2"
    assert (tmp_path / ".ctx" / "CONTEXT-0.md").is_file()

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
