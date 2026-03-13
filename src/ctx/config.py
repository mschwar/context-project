"""Configuration loading from env vars and .ctxconfig files.

Resolution order (highest priority first):
1. CLI flags (passed through from Click)
2. Environment variables: CTX_PROVIDER, CTX_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY
3. .ctxconfig YAML file in target directory or parents
4. Built-in defaults

Built-in defaults:
    provider: "anthropic"
    model: "claude-haiku-4-5-20251001"
    max_file_tokens: 8000  (truncate files larger than this before sending to LLM)
    max_depth: None  (unlimited)
    extensions: None  (all text files)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Config:
    """Resolved configuration for a ctx run."""

    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    api_key: str = ""
    max_file_tokens: int = 8000
    max_depth: Optional[int] = None
    extensions: Optional[list[str]] = None  # None = all text files

    # Runtime stats (populated during run, not from config)
    tokens_used: int = field(default=0, repr=False)
    cost_usd: float = field(default=0.0, repr=False)


def load_config(
    target_path: Path,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_depth: Optional[int] = None,
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
    raise NotImplementedError
