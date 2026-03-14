"""Tests for ctx setup command and supporting config helpers."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ctx.config import detect_provider, write_default_config


# ---------------------------------------------------------------------------
# detect_provider
# ---------------------------------------------------------------------------


def test_detect_provider_anthropic_key(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert detect_provider() == ("anthropic", None)


def test_detect_provider_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert detect_provider() == ("openai", None)


def test_detect_provider_anthropic_takes_priority_over_openai(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    provider, _ = detect_provider()
    assert provider == "anthropic"


def test_detect_provider_ollama_probe(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_response = MagicMock()
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)
    fake_response.read.return_value = json.dumps({"data": [{"id": "llama3.2"}]}).encode()

    with patch("urllib.request.urlopen", return_value=fake_response):
        result = detect_provider()

    assert result == ("ollama", "llama3.2")


def test_detect_provider_returns_none_when_nothing_available(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = detect_provider()

    assert result is None


# ---------------------------------------------------------------------------
# write_default_config
# ---------------------------------------------------------------------------


def test_write_default_config_anthropic(tmp_path) -> None:
    write_default_config(tmp_path, "anthropic")
    content = (tmp_path / ".ctxconfig").read_text(encoding="utf-8")
    assert "provider: anthropic" in content
    assert "base_url" not in content


def test_write_default_config_ollama_with_model_and_base_url(tmp_path) -> None:
    write_default_config(tmp_path, "ollama", model="llama3.2", base_url="http://localhost:11434/v1")
    content = (tmp_path / ".ctxconfig").read_text(encoding="utf-8")
    assert "provider: ollama" in content
    assert "model: llama3.2" in content
    assert "base_url: http://localhost:11434/v1" in content


# ---------------------------------------------------------------------------
# ctx setup command
# ---------------------------------------------------------------------------


def test_setup_writes_config_when_none_exists(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["setup", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".ctxconfig").exists()
    assert "anthropic" in (tmp_path / ".ctxconfig").read_text(encoding="utf-8")
    assert "Config written" in result.output
    assert "ctx init ." in result.output


def test_setup_aborts_when_user_declines_overwrite(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    (tmp_path / ".ctxconfig").write_text("provider: openai\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["setup", str(tmp_path)], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled" in result.output
    assert (tmp_path / ".ctxconfig").read_text(encoding="utf-8") == "provider: openai\n"


def test_setup_overwrites_when_user_confirms(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".ctxconfig").write_text("provider: openai\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["setup", str(tmp_path)], input="y\n")

    assert result.exit_code == 0
    assert "anthropic" in (tmp_path / ".ctxconfig").read_text(encoding="utf-8")


def test_setup_exits_1_when_no_provider_detected(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch("ctx.cli.detect_provider", return_value=None):
        runner = CliRunner()
        result = runner.invoke(cli_module.cli, ["setup", str(tmp_path)])

    assert result.exit_code != 0
    assert "No LLM provider detected" in result.output


# ---------------------------------------------------------------------------
# Graceful failure on missing API key
# ---------------------------------------------------------------------------


def test_init_shows_setup_hint_on_missing_api_key(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CTX_PROVIDER", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["init", str(tmp_path)])

    assert result.exit_code != 0
    assert "ctx setup" in result.output


def test_update_shows_setup_hint_on_missing_api_key(tmp_path, monkeypatch) -> None:
    cli_module = import_module("ctx.cli")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CTX_PROVIDER", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["update", str(tmp_path)])

    assert result.exit_code != 0
    assert "ctx setup" in result.output
