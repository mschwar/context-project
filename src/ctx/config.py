"""Deterministic configuration loading from env vars and .ctxconfig files.

Resolution order (highest priority first):
1. Explicit function arguments (passed through from CLI/API)
2. Environment variables: CTX_MAX_DEPTH, CTX_EXTENSIONS
3. .ctxconfig YAML file in target directory or parents
4. Built-in defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click
import yaml


@dataclass
class Config:
    """Resolved deterministic configuration for a ctx run."""

    max_depth: Optional[int] = None
    extensions: Optional[list[str]] = None


def _env_text(name: str) -> str | None:
    """Return a trimmed env var value when set and non-empty."""
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_optional_int(value: str) -> int | None:
    """Parse an int env/config value, allowing the string 'none'."""
    return None if value.lower() == "none" else int(value)


def _iter_config_dirs(start_dir: Path) -> list[Path]:
    """Return directories from *start_dir* upward for .ctxconfig lookup."""
    return [start_dir, *start_dir.parents]


def resolve_project_anchor(target_path: Path) -> Path:
    """Resolve the canonical project root anchor for *target_path*."""
    resolved = target_path.resolve()
    start_dir = resolved if resolved.is_dir() else resolved.parent
    candidates = _iter_config_dirs(start_dir)
    try:
        home_dir = Path.home().resolve()
    except OSError:
        home_dir = None

    for directory in candidates:
        if (directory / ".git").exists() or (directory / ".ctx" / "metadata.json").is_file():
            return directory

    for directory in candidates:
        if directory != home_dir and (directory / ".ctxconfig").is_file():
            return directory

    return start_dir


def resolve_configured_extensions(target_path: Path) -> Optional[list[str]]:
    """Resolve file-extension allowlist from CTX_EXTENSIONS or .ctxconfig."""
    env_extensions = os.getenv("CTX_EXTENSIONS")
    if env_extensions is not None:
        parsed = [item.strip() for item in env_extensions.split(",") if item.strip()]
        return parsed or None

    start_dir = target_path if target_path.is_dir() else target_path.parent
    for directory in _iter_config_dirs(start_dir):
        config_path = directory / ".ctxconfig"
        if not config_path.exists():
            continue
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if isinstance(data, dict) and "extensions" in data:
            raw = data["extensions"]
            if raw is None:
                return None
            if isinstance(raw, str):
                return [raw.strip()] if raw.strip() else None
            if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
                cleaned = [item.strip() for item in raw if item.strip()]
                return cleaned or None
        break
    return None


def load_config(
    target_path: Path,
    *,
    max_depth: Optional[int] = None,
    extensions: Optional[list[str]] = None,
) -> Config:
    """Load deterministic config by merging .ctxconfig, env vars, and explicit overrides."""
    config = Config()

    start_dir = target_path if target_path.is_dir() else target_path.parent
    for directory in _iter_config_dirs(start_dir):
        config_path = directory / ".ctxconfig"
        if not config_path.exists():
            continue

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise click.UsageError(f"Invalid .ctxconfig in {config_path}: expected a YAML mapping.")

        if "max_depth" in data:
            config.max_depth = None if data["max_depth"] is None else int(data["max_depth"])
        if "extensions" in data:
            raw_ext = data["extensions"]
            if raw_ext is None:
                config.extensions = None
            elif isinstance(raw_ext, str):
                config.extensions = [raw_ext.strip()] if raw_ext.strip() else None
            elif isinstance(raw_ext, list) and all(isinstance(item, str) for item in raw_ext):
                cleaned = [item.strip() for item in raw_ext if item.strip()]
                config.extensions = cleaned or None
            else:
                raise click.UsageError(
                    f"Invalid extensions in {config_path}: expected a string list or null."
                )
        break

    env_max_depth = _env_text("CTX_MAX_DEPTH")
    if env_max_depth is not None:
        config.max_depth = _parse_optional_int(env_max_depth)

    env_extensions = os.getenv("CTX_EXTENSIONS")
    if env_extensions is not None:
        parsed_extensions = [item.strip() for item in env_extensions.split(",") if item.strip()]
        config.extensions = parsed_extensions or None

    if max_depth is not None:
        config.max_depth = max_depth
    if extensions is not None:
        config.extensions = extensions

    if config.max_depth is not None and config.max_depth < 0:
        raise click.UsageError(f"Invalid max_depth ({config.max_depth}): expected a non-negative integer.")

    return config
