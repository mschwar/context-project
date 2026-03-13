"""Tests for ctx.llm — provider clients and prompt parsing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest

from ctx.config import Config
from ctx.llm import AnthropicClient, FileSummary, OpenAIClient, SubdirSummary, create_client


class _FakeAnthropicFactory:
    def __init__(self, responses: list[object]) -> None:
        self.instances: list[SimpleNamespace] = []
        self._responses = list(responses)

    def __call__(self, *, api_key: str) -> SimpleNamespace:
        instance = SimpleNamespace(api_key=api_key, calls=[])

        def create(**kwargs):
            instance.calls.append(kwargs)
            return self._responses.pop(0)

        instance.messages = SimpleNamespace(create=create)
        self.instances.append(instance)
        return instance


class _FakeOpenAIFactory:
    def __init__(self, responses: list[object]) -> None:
        self.instances: list[SimpleNamespace] = []
        self._responses = list(responses)

    def __call__(self, *, api_key: str) -> SimpleNamespace:
        instance = SimpleNamespace(api_key=api_key, calls=[])

        def create(**kwargs):
            instance.calls.append(kwargs)
            return self._responses.pop(0)

        instance.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self.instances.append(instance)
        return instance


def test_create_client_returns_anthropic(monkeypatch) -> None:
    factory = _FakeAnthropicFactory([])
    monkeypatch.setattr("ctx.llm.Anthropic", factory)

    client = create_client(Config(provider="anthropic", api_key="anthropic-key"))

    assert isinstance(client, AnthropicClient)
    assert factory.instances[0].api_key == "anthropic-key"


def test_create_client_returns_openai(monkeypatch) -> None:
    factory = _FakeOpenAIFactory([])
    monkeypatch.setattr("ctx.llm.OpenAI", factory)

    client = create_client(Config(provider="openai", api_key="openai-key"))

    assert isinstance(client, OpenAIClient)
    assert factory.instances[0].api_key == "openai-key"


def test_create_client_rejects_unknown_provider() -> None:
    with pytest.raises(click.UsageError, match="Unknown provider"):
        create_client(Config(provider="unknown", api_key="key"))


def test_anthropic_summarize_files_parses_json_and_tracks_tokens(monkeypatch) -> None:
    factory = _FakeAnthropicFactory(
        [
            SimpleNamespace(
                content=[SimpleNamespace(text='```json\n["Entrypoint module", "Helper functions"]\n```')],
                usage=SimpleNamespace(input_tokens=12, output_tokens=4),
            )
        ]
    )
    monkeypatch.setattr("ctx.llm.Anthropic", factory)
    config = Config(provider="anthropic", api_key="anthropic-key")
    client = AnthropicClient(config)

    results = client.summarize_files(
        Path("src"),
        [("main.py", "print('hi')"), ("utils.py", "def helper():\n    return 1")],
    )

    assert [result.text for result in results] == ["Entrypoint module", "Helper functions"]
    assert results[0].input_tokens == 12
    assert results[0].output_tokens == 4
    assert results[1].input_tokens == 0
    assert results[1].output_tokens == 0
    assert config.tokens_used == 16
    assert factory.instances[0].calls[0]["model"] == config.model
    assert "main.py" in factory.instances[0].calls[0]["messages"][0]["content"]


def test_anthropic_summarize_directory_returns_markdown(monkeypatch) -> None:
    factory = _FakeAnthropicFactory(
        [
            SimpleNamespace(
                content=[SimpleNamespace(text="# src\n\nPurpose.\n\n## Files\n- **main.py** — Entry point\n")],
                usage=SimpleNamespace(input_tokens=20, output_tokens=6),
            )
        ]
    )
    monkeypatch.setattr("ctx.llm.Anthropic", factory)
    config = Config(provider="anthropic", api_key="anthropic-key")
    client = AnthropicClient(config)

    result = client.summarize_directory(
        Path("src"),
        [FileSummary(name="main.py", summary="Entry point")],
        [SubdirSummary(name="utils", summary="Shared helpers")],
    )

    assert result.text.startswith("# src")
    assert result.input_tokens == 20
    assert result.output_tokens == 6
    assert config.tokens_used == 26
    assert "Subdirectory summaries:" in factory.instances[0].calls[0]["messages"][0]["content"]


def test_anthropic_summarize_files_scales_output_budget_for_large_batches(monkeypatch) -> None:
    responses = [
        SimpleNamespace(
            content=[
                SimpleNamespace(
                    text=str([f"Summary {index}" for index in range(20)]).replace("'", '"')
                )
            ],
            usage=SimpleNamespace(input_tokens=40, output_tokens=20),
        )
    ]
    factory = _FakeAnthropicFactory(responses)
    monkeypatch.setattr("ctx.llm.Anthropic", factory)
    config = Config(provider="anthropic", api_key="anthropic-key")
    client = AnthropicClient(config)

    files = [(f"file_{index}.py", f"print({index})") for index in range(20)]
    client.summarize_files(Path("src"), files)

    assert factory.instances[0].calls[0]["max_tokens"] == 2816


def test_openai_summarize_files_uses_openai_default_model(monkeypatch) -> None:
    factory = _FakeOpenAIFactory(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='["CLI entrypoint", "Utilities"]')
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=8, completion_tokens=3),
            )
        ]
    )
    monkeypatch.setattr("ctx.llm.OpenAI", factory)
    config = Config(provider="openai", api_key="openai-key")
    client = OpenAIClient(config)

    results = client.summarize_files(
        Path("src"),
        [("main.py", "print('hi')"), ("utils.py", "def helper():\n    return 1")],
    )

    assert client.model == "gpt-4o-mini"
    assert config.model == "gpt-4o-mini"
    assert [result.text for result in results] == ["CLI entrypoint", "Utilities"]
    assert config.tokens_used == 11
    assert factory.instances[0].calls[0]["model"] == "gpt-4o-mini"


def test_openai_summarize_files_scales_output_budget_for_large_batches(monkeypatch) -> None:
    responses = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=str([f"Summary {index}" for index in range(20)]).replace("'", '"')
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=40, completion_tokens=20),
        )
    ]
    factory = _FakeOpenAIFactory(responses)
    monkeypatch.setattr("ctx.llm.OpenAI", factory)
    config = Config(provider="openai", api_key="openai-key", model="gpt-5-mini")
    client = OpenAIClient(config)

    files = [(f"file_{index}.py", f"print({index})") for index in range(20)]
    client.summarize_files(Path("src"), files)

    assert factory.instances[0].calls[0]["max_completion_tokens"] == 2816


def test_openai_summarize_directory_tracks_tokens(monkeypatch) -> None:
    factory = _FakeOpenAIFactory(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="# docs\n\nDocumentation.\n\n## Files\n- **guide.md** — User guide\n"
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=14, completion_tokens=7),
            )
        ]
    )
    monkeypatch.setattr("ctx.llm.OpenAI", factory)
    config = Config(provider="openai", api_key="openai-key", model="gpt-5-mini")
    client = OpenAIClient(config)

    result = client.summarize_directory(
        Path("docs"),
        [FileSummary(name="guide.md", summary="User guide")],
        [],
    )

    assert result.text.startswith("# docs")
    assert result.input_tokens == 14
    assert result.output_tokens == 7
    assert config.tokens_used == 21
    assert "File summaries:" in factory.instances[0].calls[0]["messages"][1]["content"]
