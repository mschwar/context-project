"""Configuration loading from env vars and .ctxconfig files.

Resolution order (highest priority first):
1. CLI flags (passed through from Click)
2. Environment variables: CTX_PROVIDER, CTX_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY
3. .ctxconfig YAML file in target directory or parents
4. Built-in defaults

Built-in defaults:
    provider: "anthropic"
    model: provider-specific default
        - anthropic: "claude-haiku-4-5-20251001"
        - openai: "gpt-4o-mini"
        - ollama: "llama3.2"
        - lmstudio: "loaded-model"
    max_file_tokens: 8000  (truncate files larger than this before sending to LLM)
    max_depth: None  (unlimited)
    token_budget: None  (unlimited — set to cap total tokens per run)
    extensions: None  (all text files)
    base_url: None  (provider default — override for custom endpoints)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
import yaml


DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
    "lmstudio": "loaded-model",
    "bitnet": "",  # model path is required; no default
}
DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}
LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio", "bitnet"})


@dataclass
class Config:
    """Resolved configuration for a ctx run."""

    provider: str = DEFAULT_PROVIDER
    model: str = ""
    api_key: str = field(default="", repr=False)
    base_url: Optional[str] = None
    max_file_tokens: int = 8000
    max_depth: Optional[int] = None
    token_budget: Optional[int] = None  # None = unlimited
    extensions: Optional[list[str]] = None  # None = all text files

    # Runtime stats (populated during run, not from config)
    tokens_used: int = field(default=0, repr=False)

    def resolved_model(self) -> str:
        """Return the provider-specific default when no explicit model is set."""

        provider = (self.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        return self.model.strip() or DEFAULT_MODELS.get(provider, DEFAULT_MODELS[DEFAULT_PROVIDER])


def load_config(
    target_path: Path,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_depth: Optional[int] = None,
    token_budget: Optional[int] = None,
    base_url: Optional[str] = None,
) -> Config:
    """Load config by merging .ctxconfig, env vars, and CLI overrides.

    Args:
        target_path: The directory being processed (search here and parents for .ctxconfig).
        provider: CLI override for provider.
        model: CLI override for model.
        max_depth: CLI override for max recursion depth.

    Returns:
        Fully resolved Config instance ready for use.

    Implementation:
        1. Start with Config() defaults.
        2. Walk target_path up to root looking for .ctxconfig — if found, yaml.safe_load it
           and overlay matching fields onto the Config.
        3. Check env vars CTX_PROVIDER, CTX_MODEL and overlay if set.
        4. Apply CLI overrides (provider, model, max_depth) if not None.
        5. Resolve api_key: if provider is "anthropic" read ANTHROPIC_API_KEY,
           if "openai" read OPENAI_API_KEY. Raise click.UsageError if missing.
        6. Return the Config.
    """
    config = Config()

    start_dir = target_path if target_path.is_dir() else target_path.parent
    for directory in (start_dir, *start_dir.parents):
        config_path = directory / ".ctxconfig"
        if not config_path.exists():
            continue

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise click.UsageError(f"Invalid .ctxconfig in {config_path}: expected a YAML mapping.")

        if "provider" in data and data["provider"] is not None:
            config.provider = str(data["provider"]).strip()
        if "model" in data and data["model"] is not None:
            config.model = str(data["model"]).strip()
        if "max_file_tokens" in data and data["max_file_tokens"] is not None:
            config.max_file_tokens = int(data["max_file_tokens"])
        if "max_depth" in data:
            config.max_depth = None if data["max_depth"] is None else int(data["max_depth"])
        if "token_budget" in data:
            config.token_budget = None if data["token_budget"] is None else int(data["token_budget"])
        if "base_url" in data and data["base_url"] is not None:
            config.base_url = str(data["base_url"]).strip()
        if "extensions" in data:
            extensions = data["extensions"]
            if extensions is None:
                config.extensions = None
            elif isinstance(extensions, str):
                config.extensions = [extensions]
            elif isinstance(extensions, list) and all(isinstance(item, str) for item in extensions):
                config.extensions = extensions
            else:
                raise click.UsageError(
                    f"Invalid extensions in {config_path}: expected a string list or null."
                )
        break

    env_provider = os.getenv("CTX_PROVIDER")
    env_model = os.getenv("CTX_MODEL")
    if env_provider:
        config.provider = env_provider.strip()
    if env_model:
        config.model = env_model.strip()

    if provider is not None:
        config.provider = provider
    if model is not None:
        config.model = model
    if max_depth is not None:
        config.max_depth = max_depth
    if token_budget is not None:
        config.token_budget = token_budget
    if base_url is not None:
        config.base_url = base_url

    config.provider = config.provider.strip().lower()
    if config.provider not in DEFAULT_MODELS:
        raise click.UsageError(f"Unsupported provider: {config.provider}")
    config.model = config.resolved_model()

    # Local providers don't require an API key
    if config.provider in LOCAL_PROVIDERS:
        if not config.base_url and config.provider in DEFAULT_BASE_URLS:
            config.base_url = DEFAULT_BASE_URLS[config.provider]
        config.api_key = os.getenv("OPENAI_API_KEY", "not-needed").strip() or "not-needed"
        if config.provider == "bitnet" and not config.model:
            raise click.UsageError(
                "--provider bitnet requires --model with the path to a .gguf file."
            )
    else:
        api_key_env = "ANTHROPIC_API_KEY" if config.provider == "anthropic" else "OPENAI_API_KEY"
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            raise click.UsageError(f"Missing required environment variable: {api_key_env}")
        config.api_key = api_key

    return config
