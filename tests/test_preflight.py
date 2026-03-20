from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ctx.config import Config
from ctx.preflight import PreflightCheck, PreflightResult, run_preflight


# ---------------------------------------------------------------------------
# 6.1 Unit tests for PreflightCheck / PreflightResult
# ---------------------------------------------------------------------------


def test_preflight_result_ready_when_all_ok():
    checks = [
        PreflightCheck(name="provider", status="ok", detail="anthropic"),
        PreflightCheck(name="git", status="info", detail="not a git repo"),
    ]
    result = PreflightResult(checks=checks, ready=True)
    assert result.ready is True


def test_preflight_result_not_ready_when_any_fail():
    checks = [
        PreflightCheck(name="provider", status="ok", detail="anthropic"),
        PreflightCheck(name="config", status="fail", detail="missing key", fix="set the key"),
    ]
    result = PreflightResult(checks=checks, ready=False)
    assert result.ready is False


# ---------------------------------------------------------------------------
# 6.2 Unit tests for run_preflight
# ---------------------------------------------------------------------------


def test_preflight_no_provider_detected(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("ctx.preflight.detect_provider", return_value=None):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    assert result.checks[0].name == "provider"
    assert result.checks[0].status == "fail"
    assert len(result.checks) == 1


def test_preflight_cloud_provider_missing_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", side_effect=__import__("ctx.config", fromlist=["MissingApiKeyError"]).MissingApiKeyError("Missing required environment variable: ANTHROPIC_API_KEY")):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    names = [c.name for c in result.checks]
    assert "provider" in names
    assert "config" in names
    config_check = next(c for c in result.checks if c.name == "config")
    assert config_check.status == "fail"
    # connectivity and model_quality should be skipped
    assert "connectivity" not in names
    assert "model_quality" not in names


def test_preflight_cloud_connectivity_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(False, "HTTP 401")):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    names = [c.name for c in result.checks]
    assert "connectivity" in names
    conn = next(c for c in result.checks if c.name == "connectivity")
    assert conn.status == "fail"
    assert "model_quality" not in names


def test_preflight_cloud_all_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    mock_result = MagicMock()
    mock_result.text = "Simple function that returns a greeting string."
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)):
        result = run_preflight(str(tmp_path))
    assert result.ready is True
    assert result.provider == "anthropic"
    statuses = {c.name: c.status for c in result.checks}
    assert statuses["provider"] == "ok"
    assert statuses["connectivity"] == "ok"
    assert statuses["model_quality"] == "ok"
    assert statuses["target"] == "ok"


def test_preflight_local_provider_no_models(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_config = Config(provider="ollama", model="llama3.2", api_key="not-needed",
                         base_url="http://localhost:11434/v1")
    with patch("ctx.preflight.detect_provider", return_value=("ollama", "llama3.2")), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight._probe_local_models", return_value=(False, "no models loaded")):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    conn = next(c for c in result.checks if c.name == "connectivity")
    assert conn.status == "fail"
    assert "no models loaded" in conn.detail


def test_preflight_local_provider_all_pass(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_config = Config(provider="ollama", model="llama3.2", api_key="not-needed",
                         base_url="http://localhost:11434/v1")
    with patch("ctx.preflight.detect_provider", return_value=("ollama", "llama3.2")), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight._probe_local_models", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)):
        result = run_preflight(str(tmp_path))
    assert result.ready is True
    assert result.provider == "ollama"


def test_preflight_model_quality_empty_response(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(False, None)):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    mq = next(c for c in result.checks if c.name == "model_quality")
    assert mq.status == "fail"
    assert "empty" in mq.detail or "unusable" in mq.detail


def test_preflight_model_quality_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(False, "timeout")):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    mq = next(c for c in result.checks if c.name == "model_quality")
    assert mq.status == "fail"
    assert "60 seconds" in mq.detail


def test_preflight_target_not_a_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    nonexistent = str(tmp_path / "does_not_exist")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)):
        result = run_preflight(nonexistent)
    assert result.ready is False
    target_check = next(c for c in result.checks if c.name == "target")
    assert target_check.status == "fail"
    assert "not a directory" in target_check.detail


def test_preflight_target_not_writable(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)), \
         patch("ctx.preflight.tempfile.mkstemp", side_effect=OSError("permission denied")):
        result = run_preflight(str(tmp_path))
    assert result.ready is False
    target_check = next(c for c in result.checks if c.name == "target")
    assert target_check.status == "fail"
    assert "cannot write" in target_check.detail


def test_preflight_no_git_repo(monkeypatch, tmp_path):
    import subprocess as _subprocess
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)), \
         patch("ctx.preflight.subprocess.run", side_effect=_subprocess.CalledProcessError(128, "git")):
        result = run_preflight(str(tmp_path))
    git_check = next(c for c in result.checks if c.name == "git")
    assert git_check.status == "info"
    assert result.ready is True


def test_preflight_no_ctxignore(monkeypatch, tmp_path):
    import subprocess as _subprocess
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)), \
         patch("ctx.preflight.subprocess.run", side_effect=_subprocess.CalledProcessError(128, "git")):
        result = run_preflight(str(tmp_path))
    ignore_check = next(c for c in result.checks if c.name == "ignore")
    assert ignore_check.status == "info"
    assert "no .ctxignore" in ignore_check.detail


def test_preflight_has_ctxignore(monkeypatch, tmp_path):
    import subprocess as _subprocess
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")
    (tmp_path / ".ctxignore").write_text("*.pyc\n")
    with patch("ctx.preflight.detect_provider", return_value=("anthropic", None)), \
         patch("ctx.preflight.load_config", return_value=fake_config), \
         patch("ctx.preflight.probe_provider_connectivity", return_value=(True, None)), \
         patch("ctx.preflight.probe_model_quality", return_value=(True, None)), \
         patch("ctx.preflight.subprocess.run", side_effect=_subprocess.CalledProcessError(128, "git")):
        result = run_preflight(str(tmp_path))
    ignore_check = next(c for c in result.checks if c.name == "ignore")
    assert ignore_check.status == "ok"
    assert ".ctxignore" in ignore_check.detail


# ---------------------------------------------------------------------------
# 6.3 CLI integration tests
# ---------------------------------------------------------------------------


def test_setup_check_all_pass_human_mode(monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    fake_config = Config(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-test")

    from ctx.preflight import PreflightCheck, PreflightResult

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(name="config", status="ok", detail="loaded from .ctxconfig"),
            PreflightCheck(name="connectivity", status="ok", detail="anthropic API reachable"),
            PreflightCheck(name="model_quality", status="ok", detail="claude-haiku-4-5-20251001 returned valid summary"),
            PreflightCheck(name="target", status="ok", detail=f"{tmp_path} is writable"),
            PreflightCheck(name="git", status="ok", detail="repository detected."),
            PreflightCheck(name="ignore", status="info", detail="no .ctxignore found. Using built-in defaults."),
        ],
        ready=True,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("ctx.preflight.run_preflight", return_value=fake_result) as mock_run:
        result = runner.invoke(cli_module.cli, ["setup", "--check", str(tmp_path)])

    assert "[ OK ]" in result.output
    assert "Ready to run: ctx refresh ." in result.output
    assert result.exit_code == 0


def test_setup_check_fail_human_mode(monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    from ctx.preflight import PreflightCheck, PreflightResult

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(
                name="provider",
                status="fail",
                detail="no LLM provider detected.",
                fix="set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment.",
            ),
        ],
        ready=False,
        provider=None,
        model=None,
    )

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(cli_module.cli, ["setup", "--check", str(tmp_path)])

    assert "[FAIL]" in result.output
    assert result.exit_code == 1


def test_setup_check_all_pass_json_mode(monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    from ctx.preflight import PreflightCheck, PreflightResult

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(name="config", status="ok", detail="loaded from .ctxconfig"),
            PreflightCheck(name="connectivity", status="ok", detail="anthropic API reachable"),
            PreflightCheck(name="model_quality", status="ok", detail="claude-haiku-4-5-20251001 returned valid summary"),
            PreflightCheck(name="target", status="ok", detail=f"{tmp_path} is writable"),
            PreflightCheck(name="git", status="ok", detail="repository detected."),
            PreflightCheck(name="ignore", status="info", detail="no .ctxignore found."),
        ],
        ready=True,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(
            cli_module.cli,
            ["--output", "json", "setup", "--check", str(tmp_path)],
        )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["ready"] is True
    assert envelope["data"]["check_only"] is True
    checks = envelope["data"]["checks"]
    assert checks["provider"]["status"] == "ok"


def test_setup_check_fail_json_mode(monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    from ctx.preflight import PreflightCheck, PreflightResult

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(
                name="connectivity",
                status="fail",
                detail="cannot reach anthropic API — Connection error.",
                fix="check your internet connection.",
            ),
        ],
        ready=False,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(
            cli_module.cli,
            ["--output", "json", "setup", "--check", str(tmp_path)],
        )

    envelope = json.loads(result.output)
    assert envelope["data"]["ready"] is False
    assert len(envelope["errors"]) > 0
    assert envelope["errors"][0]["code"] == "preflight_failed"


def test_setup_check_backward_compatible(monkeypatch, tmp_path):
    cli_module = import_module("ctx.cli")
    runner = CliRunner()

    from ctx.preflight import PreflightCheck, PreflightResult

    fake_result = PreflightResult(
        checks=[
            PreflightCheck(name="provider", status="ok", detail="anthropic (via ANTHROPIC_API_KEY)"),
            PreflightCheck(name="config", status="ok", detail="loaded from .ctxconfig"),
            PreflightCheck(name="connectivity", status="ok", detail="anthropic API reachable"),
            PreflightCheck(name="model_quality", status="ok", detail="claude-haiku-4-5-20251001 returned valid summary"),
            PreflightCheck(name="target", status="ok", detail=f"{tmp_path} is writable"),
            PreflightCheck(name="git", status="info", detail="not a git repository."),
            PreflightCheck(name="ignore", status="info", detail="no .ctxignore found."),
        ],
        ready=True,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("ctx.preflight.run_preflight", return_value=fake_result):
        result = runner.invoke(
            cli_module.cli,
            ["--output", "json", "setup", "--check", str(tmp_path)],
        )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["command"] == "setup"
    assert envelope["data"]["check_only"] is True
    assert "provider" in envelope["data"]["checks"]
    assert "connectivity" in envelope["data"]["checks"]
