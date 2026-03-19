"""Configuration loading from env vars and .ctxconfig files.

Resolution order (highest priority first):
1. CLI flags (passed through from Click)
2. Environment variables: CTX_* plus provider API keys
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
    token_budget: None  (generator-level budget)
    max_tokens_per_run: None  (hard token guardrail)
    max_usd_per_run: None  (hard USD guardrail)
    files_per_call: None  (send all files in a single LLM call — smaller values increase API call count)
    max_concurrent_dirs: None  (auto: 1 for cloud providers, 4 for local)
    extensions: None  (all text files)
    base_url: None  (provider default — override for custom endpoints)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import click
import yaml


class MissingApiKeyError(click.UsageError):
    """Raised when a required LLM provider API key is not set."""


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

# Probe endpoints for connectivity checks
ANTHROPIC_PROBE_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_API_VERSION = "2023-06-01"
OPENAI_DEFAULT_PROBE_BASE_URL = "https://api.openai.com"

# Proxy environment variables checked when connectivity fails
PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")

# Human-readable detection source shown by `ctx setup`
PROVIDER_DETECTED_VIA: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY env var",
    "openai": "OPENAI_API_KEY env var",
    "ollama": "Ollama running on localhost:11434",
    "lmstudio": "LM Studio running on localhost:1234",
}

# Pricing per 1M input tokens in USD.
PRICING_DATA: dict[str, dict] = {
    "anthropic": {
        "models": [
            ("claude-opus-4", 15.0),
            ("claude-sonnet-4", 3.0),
            ("claude-haiku-4-5", 0.80),
            ("claude-3-opus", 15.0),
            ("claude-3-sonnet", 3.0),
            ("claude-3-haiku", 0.25),
        ],
        "default": 0.80,
    },
    "openai": {
        "models": [
            ("gpt-4.1", 2.0),
            ("gpt-4o", 2.50),
            ("gpt-4-o", 2.50),
            ("gpt-4", 30.0),
            ("gpt-3.5-turbo", 0.5),
            ("gpt-3.5", 0.5),
        ],
        "default": 2.50,
    },
    "ollama": {"default": 0.0},
    "lmstudio": {"default": 0.0},
}
DEFAULT_UNKNOWN_PROVIDER_PRICE = 3.0


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
    max_tokens_per_run: Optional[int] = None  # None = unlimited hard token guardrail
    max_usd_per_run: Optional[float] = None  # None = unlimited hard USD guardrail
    files_per_call: Optional[int] = None  # None = send all files in one call
    max_concurrent_dirs: Optional[int] = None  # None = auto (1 for cloud, 4 for local)
    extensions: Optional[list[str]] = None  # None = all text files
    cache_path: Optional[str] = None  # None = default .ctx-cache/llm_cache.json; "" = disable
    max_cache_entries: int = 10_000  # trim disk cache when it exceeds this many entries
    watch_debounce_seconds: float = 0.5  # per-file debounce window for ctx watch
    resume_cooldown_seconds: float = 60.0  # delay between auto-resume cycles
    prompts: dict[str, str] = field(default_factory=dict)


    # Runtime stats (populated during run, not from config)
    tokens_used: int = field(default=0, repr=False)

    def resolved_model(self) -> str:
        """Return the provider-specific default when no explicit model is set."""

        provider = (self.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        return self.model.strip() or DEFAULT_MODELS.get(provider, DEFAULT_MODELS[DEFAULT_PROVIDER])


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


def _parse_optional_float(value: str) -> float | None:
    """Parse a float env/config value, allowing the string 'none'."""

    return None if value.lower() == "none" else float(value)


def detect_provider(
    _probe_callback: "Callable[[str], None] | None" = None,
) -> tuple[str, str | None] | None:
    """Detect an available LLM provider from env vars and local port probes.

    Returns (provider, model_or_None) or None if nothing is found.
    """
    import json
    import urllib.error
    import urllib.request

    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return ("anthropic", None)
    if os.getenv("OPENAI_API_KEY", "").strip():
        return ("openai", None)

    for provider, base_url in (
        ("ollama", "http://localhost:11434"),
        ("lmstudio", "http://localhost:1234"),
    ):
        if _probe_callback:
            _probe_callback(provider)
        try:
            with urllib.request.urlopen(f"{base_url}/v1/models", timeout=2) as resp:
                data = json.loads(resp.read())
            model: str | None = None
            if isinstance(data.get("data"), list) and data["data"]:
                model = data["data"][0].get("id")
            return (provider, model)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
            pass

    return None


def probe_provider_connectivity(
    provider: str, api_key: str, base_url: str | None = None
) -> tuple[bool, str | None]:
    """Make a lightweight call to verify a cloud provider is reachable.

    Returns (True, None) on success or (False, error_message) on failure.
    Local providers (ollama, lmstudio, bitnet) always return success — they are
    validated via port probe during detect_provider.
    """
    import urllib.error
    import urllib.request

    if provider in LOCAL_PROVIDERS:
        return True, None

    if provider == "anthropic":
        url = ANTHROPIC_PROBE_URL
        req = urllib.request.Request(url)
        req.add_header("x-api-key", api_key)
        req.add_header("anthropic-version", ANTHROPIC_API_VERSION)
    elif provider == "openai":
        url = (base_url or OPENAI_DEFAULT_PROBE_BASE_URL) + "/v1/models"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {api_key}")
    else:
        return True, None

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True, None
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, f"Authentication failed (HTTP {exc.code}) — check your API key"
        return False, f"HTTP error {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"
    except (TimeoutError, OSError) as exc:
        return False, f"Connection error: {exc}"


def write_default_config(path: Path, provider: str, model: str | None = None, base_url: str | None = None) -> None:
    """Write a minimal .ctxconfig into *path* directory."""
    lines = [f"provider: {provider}"]
    if model:
        lines.append(f"model: {model}")
    if base_url:
        lines.append(f"base_url: {base_url}")
    (path / ".ctxconfig").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_config(
    target_path: Path,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_depth: Optional[int] = None,
    token_budget: Optional[int] = None,
    base_url: Optional[str] = None,
    cache_path: Optional[str] = None,
    require_api_key: bool = True,
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
    provider_explicit = False

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
            provider_explicit = True
        if "model" in data and data["model"] is not None:
            config.model = str(data["model"]).strip()
        if "max_file_tokens" in data and data["max_file_tokens"] is not None:
            config.max_file_tokens = int(data["max_file_tokens"])
        if "max_depth" in data:
            config.max_depth = None if data["max_depth"] is None else int(data["max_depth"])
        if "token_budget" in data:
            config.token_budget = None if data["token_budget"] is None else int(data["token_budget"])
        if "max_tokens_per_run" in data:
            config.max_tokens_per_run = (
                None if data["max_tokens_per_run"] is None else int(data["max_tokens_per_run"])
            )
        if "max_usd_per_run" in data:
            config.max_usd_per_run = (
                None if data["max_usd_per_run"] is None else float(data["max_usd_per_run"])
            )
        if "files_per_call" in data:
            config.files_per_call = None if data["files_per_call"] is None else int(data["files_per_call"])
        elif "batch_size" in data:
            config.files_per_call = None if data["batch_size"] is None else int(data["batch_size"])
        if "max_concurrent_dirs" in data:
            config.max_concurrent_dirs = None if data["max_concurrent_dirs"] is None else int(data["max_concurrent_dirs"])
        if "resume_cooldown_seconds" in data and data["resume_cooldown_seconds"] is not None:
            config.resume_cooldown_seconds = float(data["resume_cooldown_seconds"])
        if "max_cache_entries" in data and data["max_cache_entries"] is not None:
            config.max_cache_entries = int(data["max_cache_entries"])
        if "watch_debounce_seconds" in data and data["watch_debounce_seconds"] is not None:
            config.watch_debounce_seconds = float(data["watch_debounce_seconds"])
        if "cache_path" in data:
            config.cache_path = None if data["cache_path"] is None else str(data["cache_path"])
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
        
        if "prompts" in data and isinstance(data["prompts"], dict):
            config.prompts.update(data["prompts"])

        break

    env_provider = _env_text("CTX_PROVIDER")
    env_model = _env_text("CTX_MODEL")
    if env_provider:
        config.provider = env_provider.strip()
        provider_explicit = True
    if env_model:
        config.model = env_model.strip()
    env_base_url = _env_text("CTX_BASE_URL")
    if env_base_url:
        config.base_url = env_base_url
    env_max_file_tokens = _env_text("CTX_MAX_FILE_TOKENS")
    if env_max_file_tokens is not None:
        config.max_file_tokens = int(env_max_file_tokens)
    env_max_depth = _env_text("CTX_MAX_DEPTH")
    if env_max_depth is not None:
        config.max_depth = _parse_optional_int(env_max_depth)
    env_token_budget = _env_text("CTX_TOKEN_BUDGET")
    if env_token_budget is not None:
        config.token_budget = _parse_optional_int(env_token_budget)
    env_max_tokens_per_run = _env_text("CTX_MAX_TOKENS_PER_RUN")
    if env_max_tokens_per_run is not None:
        config.max_tokens_per_run = _parse_optional_int(env_max_tokens_per_run)
    env_max_usd_per_run = _env_text("CTX_MAX_USD_PER_RUN")
    if env_max_usd_per_run is not None:
        config.max_usd_per_run = _parse_optional_float(env_max_usd_per_run)
    env_files_per_call = _env_text("CTX_FILES_PER_CALL") or _env_text("CTX_BATCH_SIZE")
    if env_files_per_call is not None:
        config.files_per_call = _parse_optional_int(env_files_per_call)
    env_max_concurrent_dirs = _env_text("CTX_MAX_CONCURRENT_DIRS")
    if env_max_concurrent_dirs is not None:
        config.max_concurrent_dirs = _parse_optional_int(env_max_concurrent_dirs)
    env_cache_path = os.getenv("CTX_CACHE_PATH")
    if env_cache_path is not None:
        config.cache_path = env_cache_path
    env_max_cache_entries = _env_text("CTX_MAX_CACHE_ENTRIES")
    if env_max_cache_entries is not None:
        config.max_cache_entries = int(env_max_cache_entries)
    env_watch_debounce = _env_text("CTX_WATCH_DEBOUNCE")
    if env_watch_debounce is not None:
        config.watch_debounce_seconds = float(env_watch_debounce)
    env_extensions = os.getenv("CTX_EXTENSIONS")
    if env_extensions is not None:
        parsed_extensions = [item.strip() for item in env_extensions.split(",") if item.strip()]
        config.extensions = parsed_extensions or None

    if provider is not None:
        config.provider = provider
        provider_explicit = True
    if model is not None:
        config.model = model
    if max_depth is not None:
        config.max_depth = max_depth
    if token_budget is not None:
        config.token_budget = token_budget
    if base_url is not None:
        config.base_url = base_url
    if cache_path is not None:
        config.cache_path = cache_path

    if not provider_explicit:
        # Support env-only setups where the operator exported an API key but
        # did not also set CTX_PROVIDER or write a .ctxconfig file yet.
        if os.getenv("ANTHROPIC_API_KEY", "").strip():
            config.provider = "anthropic"
        elif os.getenv("OPENAI_API_KEY", "").strip():
            config.provider = "openai"

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
    elif require_api_key:
        api_key_env = "ANTHROPIC_API_KEY" if config.provider == "anthropic" else "OPENAI_API_KEY"
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            raise MissingApiKeyError(f"Missing required environment variable: {api_key_env}")
        config.api_key = api_key

    return config


def estimate_cost(tokens: int, provider: str, model: str) -> float:
    """Estimate cost in USD based on tokens used and provider pricing."""
    provider_lower = provider.lower()
    model_lower = model.lower()

    provider_pricing = PRICING_DATA.get(provider_lower)
    if not provider_pricing:
        return tokens * DEFAULT_UNKNOWN_PROVIDER_PRICE / 1_000_000

    if "models" not in provider_pricing:
        return tokens * provider_pricing["default"] / 1_000_000

    for model_key, price_per_million in provider_pricing["models"]:
        if model_key in model_lower:
            return tokens * price_per_million / 1_000_000

    return tokens * provider_pricing["default"] / 1_000_000
