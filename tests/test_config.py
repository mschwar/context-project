"""Tests for ctx.config — config file, env var, and CLI resolution."""

from __future__ import annotations

import click
import pytest
import yaml

from ctx.config import Config, estimate_cost, load_config


def _clear_ctx_env(monkeypatch) -> None:
    for name in (
        "CTX_PROVIDER",
        "CTX_MODEL",
        "CTX_BASE_URL",
        "CTX_MAX_FILE_TOKENS",
        "CTX_MAX_DEPTH",
        "CTX_TOKEN_BUDGET",
        "CTX_MAX_TOKENS_PER_RUN",
        "CTX_MAX_USD_PER_RUN",
        "CTX_BATCH_SIZE",
        "CTX_CACHE_PATH",
        "CTX_MAX_CACHE_ENTRIES",
        "CTX_WATCH_DEBOUNCE",
        "CTX_EXTENSIONS",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _write_ctxconfig(path, data: dict) -> None:
    (path / ".ctxconfig").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _placeholder(label: str) -> str:
    return f"{label}-value"


def test_load_config_defaults(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    anthropic_value = _placeholder("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_value)

    config = load_config(tmp_path)

    assert config.provider == "anthropic"
    assert config.model == "claude-haiku-4-5-20251001"
    assert config.api_key == anthropic_value
    assert config.max_file_tokens == 8000
    assert config.max_depth is None
    assert config.extensions is None


def test_config_repr_redacts_api_key() -> None:
    value = _placeholder("repr")
    secret_field = next(name for name in Config.__dataclass_fields__ if name.endswith("_key"))
    config = Config(**{secret_field: value})

    assert value not in repr(config)


def test_load_config_reads_nearest_parent_ctxconfig(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    root_dir = tmp_path / "root"
    nested_dir = root_dir / "project" / "src"
    nested_dir.mkdir(parents=True)

    _write_ctxconfig(root_dir, {"provider": "anthropic", "model": "root-model"})
    _write_ctxconfig(
        root_dir / "project",
        {
            "provider": "openai",
            "model": "gpt-5-mini",
            "max_file_tokens": 1234,
            "max_depth": 2,
            "extensions": [".py", ".md"],
        },
    )
    openai_value = _placeholder("openai")
    monkeypatch.setenv("OPENAI_API_KEY", openai_value)

    config = load_config(nested_dir)

    assert config.provider == "openai"
    assert config.model == "gpt-5-mini"
    assert config.api_key == openai_value
    assert config.max_file_tokens == 1234
    assert config.max_depth == 2
    assert config.extensions == [".py", ".md"]


def test_load_config_env_overrides_file(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    _write_ctxconfig(tmp_path, {"provider": "anthropic", "model": "file-model", "max_depth": 1})
    monkeypatch.setenv("CTX_PROVIDER", "openai")
    monkeypatch.setenv("CTX_MODEL", "env-model")
    openai_value = _placeholder("openai")
    monkeypatch.setenv("OPENAI_API_KEY", openai_value)

    config = load_config(tmp_path)

    assert config.provider == "openai"
    assert config.model == "env-model"
    assert config.max_depth == 1
    assert config.api_key == openai_value


def test_load_config_cli_overrides_env(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    _write_ctxconfig(tmp_path, {"provider": "anthropic", "model": "file-model"})
    monkeypatch.setenv("CTX_PROVIDER", "anthropic")
    monkeypatch.setenv("CTX_MODEL", "env-model")
    anthropic_value = _placeholder("anthropic")
    openai_value = _placeholder("openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_value)
    monkeypatch.setenv("OPENAI_API_KEY", openai_value)

    config = load_config(tmp_path, provider="openai", model="cli-model", max_depth=5)

    assert config.provider == "openai"
    assert config.model == "cli-model"
    assert config.max_depth == 5
    assert config.api_key == openai_value


def test_load_config_uses_openai_default_model(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("CTX_PROVIDER", "openai")
    openai_value = _placeholder("openai")
    monkeypatch.setenv("OPENAI_API_KEY", openai_value)

    config = load_config(tmp_path)

    assert config.provider == "openai"
    assert config.model == "gpt-4o-mini"
    assert config.api_key == openai_value


def test_load_config_missing_api_key(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)

    with pytest.raises(click.UsageError, match="ANTHROPIC_API_KEY"):
        load_config(tmp_path)


def test_load_config_ollama_no_api_key_required(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)

    config = load_config(tmp_path, provider="ollama")

    assert config.provider == "ollama"
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key == "not-needed"


def test_load_config_lmstudio_no_api_key_required(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)

    config = load_config(tmp_path, provider="lmstudio")

    assert config.provider == "lmstudio"
    assert config.model == "loaded-model"
    assert config.base_url == "http://localhost:1234/v1"


def test_load_config_local_provider_custom_base_url(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)

    config = load_config(tmp_path, provider="ollama", base_url="http://gpu-server:11434/v1")

    assert config.base_url == "http://gpu-server:11434/v1"


def test_load_config_token_budget_from_cli(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", _placeholder("anthropic"))

    config = load_config(tmp_path, token_budget=50000)

    assert config.token_budget == 50000


def test_load_config_token_budget_from_ctxconfig(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", _placeholder("anthropic"))
    _write_ctxconfig(tmp_path, {"token_budget": 100000})

    config = load_config(tmp_path)

    assert config.token_budget == 100000


def test_load_config_prompts(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    anthropic_value = _placeholder("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_value)

    _write_ctxconfig(
        tmp_path,
        {
            "prompts": {
                "file_summary": "Summarize this file: {json_payload}",
                "directory_summary_system": "You are a custom directory summarizer.",
            }
        },
    )

    config = load_config(tmp_path)

    assert config.prompts == {
        "file_summary": "Summarize this file: {json_payload}",
        "directory_summary_system": "You are a custom directory summarizer.",
    }


def test_load_config_env_parity_for_scalar_fields(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", _placeholder("openai"))
    monkeypatch.setenv("CTX_PROVIDER", "openai")
    monkeypatch.setenv("CTX_MODEL", "gpt-env")
    monkeypatch.setenv("CTX_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("CTX_MAX_FILE_TOKENS", "4096")
    monkeypatch.setenv("CTX_MAX_DEPTH", "5")
    monkeypatch.setenv("CTX_TOKEN_BUDGET", "20000")
    monkeypatch.setenv("CTX_MAX_TOKENS_PER_RUN", "15000")
    monkeypatch.setenv("CTX_MAX_USD_PER_RUN", "0.75")
    monkeypatch.setenv("CTX_BATCH_SIZE", "4")
    monkeypatch.setenv("CTX_CACHE_PATH", "")
    monkeypatch.setenv("CTX_MAX_CACHE_ENTRIES", "5000")
    monkeypatch.setenv("CTX_WATCH_DEBOUNCE", "1.5")
    monkeypatch.setenv("CTX_EXTENSIONS", ".py,.md")

    config = load_config(tmp_path)

    assert config.provider == "openai"
    assert config.model == "gpt-env"
    assert config.base_url == "https://example.invalid/v1"
    assert config.max_file_tokens == 4096
    assert config.max_depth == 5
    assert config.token_budget == 20000
    assert config.max_tokens_per_run == 15000
    assert config.max_usd_per_run == pytest.approx(0.75)
    assert config.batch_size == 4
    assert config.cache_path == ""
    assert config.max_cache_entries == 5000
    assert config.watch_debounce_seconds == pytest.approx(1.5)
    assert config.extensions == [".py", ".md"]


def test_load_config_env_supports_none_sentinels(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", _placeholder("anthropic"))
    monkeypatch.setenv("CTX_MAX_DEPTH", "none")
    monkeypatch.setenv("CTX_TOKEN_BUDGET", "none")
    monkeypatch.setenv("CTX_MAX_TOKENS_PER_RUN", "none")
    monkeypatch.setenv("CTX_MAX_USD_PER_RUN", "none")
    monkeypatch.setenv("CTX_BATCH_SIZE", "none")

    config = load_config(tmp_path)

    assert config.max_depth is None
    assert config.token_budget is None
    assert config.max_tokens_per_run is None
    assert config.max_usd_per_run is None
    assert config.batch_size is None


def test_load_config_infers_openai_provider_from_api_key(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", _placeholder("openai"))

    config = load_config(tmp_path)

    assert config.provider == "openai"
    assert config.api_key == _placeholder("openai")


def test_cli_overrides_env_guardrail_related_fields(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", _placeholder("openai"))
    monkeypatch.setenv("CTX_PROVIDER", "openai")
    monkeypatch.setenv("CTX_MODEL", "env-model")
    monkeypatch.setenv("CTX_MAX_DEPTH", "2")
    monkeypatch.setenv("CTX_TOKEN_BUDGET", "999")
    monkeypatch.setenv("CTX_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("CTX_CACHE_PATH", "env-cache.json")

    config = load_config(
        tmp_path,
        model="cli-model",
        max_depth=7,
        token_budget=111,
        base_url="https://cli.example/v1",
        cache_path="cli-cache.json",
    )

    assert config.model == "cli-model"
    assert config.max_depth == 7
    assert config.token_budget == 111
    assert config.base_url == "https://cli.example/v1"
    assert config.cache_path == "cli-cache.json"


def test_load_config_reads_guardrails_from_ctxconfig(monkeypatch, tmp_path) -> None:
    _clear_ctx_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", _placeholder("anthropic"))
    _write_ctxconfig(
        tmp_path,
        {
            "max_tokens_per_run": 12345,
            "max_usd_per_run": 0.25,
        },
    )

    config = load_config(tmp_path)

    assert config.max_tokens_per_run == 12345
    assert config.max_usd_per_run == pytest.approx(0.25)


def test_estimate_cost_shared_helper() -> None:
    assert 2.5 < estimate_cost(1_000_000, "anthropic", "claude-3-sonnet") < 3.5
    assert estimate_cost(1_000_000, "ollama", "llama3.2") == pytest.approx(0.0)
