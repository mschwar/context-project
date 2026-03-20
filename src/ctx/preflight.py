from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ctx.config import (
    DEFAULT_BASE_URLS,
    LOCAL_PROVIDERS,
    PROXY_ENV_VARS,
    MissingApiKeyError,
    detect_provider,
    load_config,
    probe_provider_connectivity,
)


@dataclass
class PreflightCheck:
    name: str
    status: str
    detail: str
    fix: Optional[str] = None


@dataclass
class PreflightResult:
    checks: list[PreflightCheck]
    ready: bool
    provider: Optional[str] = None
    model: Optional[str] = None


def _probe_local_models(base_url: str) -> tuple[bool, str | None]:
    """Hit {base_url}/v1/models and confirm at least one model is listed.

    Returns (ok, error_or_None).
    """
    try:
        with urllib.request.urlopen(f"{base_url}/v1/models", timeout=5) as resp:
            data = json.loads(resp.read())
        if isinstance(data.get("data"), list) and data["data"]:
            return True, None
        return False, "no models loaded"
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        return False, str(exc)


def probe_model_quality(config) -> tuple[bool, str | None]:
    try:
        from ctx.llm import create_client
    except ImportError as exc:
        return False, str(exc)

    test_file = {
        "path": "example.py",
        "content": "def hello():\n    return 'Hello, world!'",
        "language": "python",
        "metadata": {"functions": ["hello"]},
    }

    try:
        client = create_client(config)
        results = client.summarize_files(
            Path("."),
            [{"name": "example.py", "content": test_file["content"], "language": "python", "metadata": {"functions": ["hello"]}}],
        )
        if not results:
            return False, None
        summary = results[0].text if results else ""
        if not summary or not summary.strip() or len(summary.strip()) < 5:
            return False, None
        return True, None
    except TimeoutError:
        return False, "timeout"
    except Exception as exc:
        return False, str(exc)


def run_preflight(path: str = ".") -> PreflightResult:
    checks: list[PreflightCheck] = []
    target = Path(path)

    # 3.1 Provider detection
    detected = detect_provider()
    if detected is None:
        checks.append(PreflightCheck(
            name="provider",
            status="fail",
            detail="no LLM provider detected.",
            fix=(
                "set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment,\n"
                "       or start Ollama / LM Studio before running ctx."
            ),
        ))
        return PreflightResult(checks=checks, ready=False)

    provider_name, detected_model = detected

    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        detected_via = "via ANTHROPIC_API_KEY"
    elif os.getenv("OPENAI_API_KEY", "").strip():
        detected_via = "via OPENAI_API_KEY"
    elif provider_name == "ollama":
        detected_via = "Ollama running on localhost:11434"
    elif provider_name == "lmstudio":
        detected_via = "LM Studio running on localhost:1234"
    else:
        detected_via = provider_name

    checks.append(PreflightCheck(
        name="provider",
        status="ok",
        detail=f"{provider_name} ({detected_via})",
    ))

    # 3.2 Config resolution
    config = None
    config_failed_fatal = False
    try:
        config = load_config(target, provider=provider_name, require_api_key=True)
        config_detail = f"loaded from {target.resolve()}"
        # Check for .ctxconfig file specifically
        for d in (target.resolve(), *target.resolve().parents):
            if (d / ".ctxconfig").exists():
                config_detail = f"loaded from {d / '.ctxconfig'}"
                break
        checks.append(PreflightCheck(
            name="config",
            status="ok",
            detail=config_detail,
        ))
    except MissingApiKeyError:
        api_key_env = "ANTHROPIC_API_KEY" if provider_name == "anthropic" else "OPENAI_API_KEY"
        checks.append(PreflightCheck(
            name="config",
            status="fail",
            detail=f"{provider_name} provider detected but API key is missing.",
            fix=f"set {api_key_env} in your environment.",
        ))
        config_failed_fatal = True
    except Exception as exc:
        checks.append(PreflightCheck(
            name="config",
            status="fail",
            detail=f".ctxconfig contains invalid YAML.",
            fix="check the file for syntax errors, or delete it and run `ctx setup` to regenerate.",
        ))

    if config_failed_fatal:
        return PreflightResult(checks=checks, ready=False, provider=provider_name)

    # 3.3 Provider connectivity — use config as the resolved source of truth
    resolved_provider = config.provider if config else provider_name
    conn_ok = False
    if resolved_provider in LOCAL_PROVIDERS:
        base_url = (config.base_url if config else None) or DEFAULT_BASE_URLS.get(resolved_provider, "")
        # Strip trailing /v1 to get the host:port base
        host_base = base_url.rstrip("/")
        if host_base.endswith("/v1"):
            host_base = host_base[:-3]
        ok, err = _probe_local_models(host_base)
        if ok:
            conn_ok = True
            checks.append(PreflightCheck(
                name="connectivity",
                status="ok",
                detail=f"{resolved_provider} is running and has models loaded",
            ))
        else:
            if err == "no models loaded":
                checks.append(PreflightCheck(
                    name="connectivity",
                    status="fail",
                    detail=f"{resolved_provider} is running but has no models loaded.",
                    fix=f"pull a model first — e.g., `ollama pull llama3.2`",
                ))
            else:
                checks.append(PreflightCheck(
                    name="connectivity",
                    status="fail",
                    detail=f"{resolved_provider} is not responding on {host_base}.",
                    fix=f"start {resolved_provider} before running ctx.",
                ))
    else:
        api_key = config.api_key if config else ""
        base_url = config.base_url if config else None
        ok, err = probe_provider_connectivity(resolved_provider, api_key, base_url)
        if ok:
            conn_ok = True
            checks.append(PreflightCheck(
                name="connectivity",
                status="ok",
                detail=f"{resolved_provider} API reachable",
            ))
        else:
            err_str = err or "unknown error"
            proxy_vars = [v for v in PROXY_ENV_VARS if os.getenv(v)]
            if "401" in err_str or "403" in err_str or "Authentication" in err_str or "authentication" in err_str:
                api_key_env = "ANTHROPIC_API_KEY" if resolved_provider == "anthropic" else "OPENAI_API_KEY"
                checks.append(PreflightCheck(
                    name="connectivity",
                    status="fail",
                    detail=f"authentication failed — API key is set but invalid.",
                    fix=f"verify your {api_key_env} value is a valid, active key.",
                ))
            elif proxy_vars:
                var_list = ", ".join(proxy_vars)
                checks.append(PreflightCheck(
                    name="connectivity",
                    status="fail",
                    detail=f"cannot reach {resolved_provider} API — {err_str}.",
                    fix=(
                        f"proxy env vars detected ({var_list}). A broken proxy may be blocking requests.\n"
                        f"       Try unsetting: unset {' '.join(proxy_vars)}"
                    ),
                ))
            else:
                checks.append(PreflightCheck(
                    name="connectivity",
                    status="fail",
                    detail=f"cannot reach {resolved_provider} API — {err_str}.",
                    fix="check your internet connection.",
                ))

    if not conn_ok:
        # Short-circuit: skip model quality
        _add_target_checks(checks, target)
        return PreflightResult(
            checks=checks,
            ready=False,
            provider=resolved_provider,
            model=config.resolved_model() if config else detected_model,
        )

    # 3.4 Model quality
    model_name = config.resolved_model() if config else (detected_model or "")
    if config:
        ok_q, err_q = probe_model_quality(config)
        if ok_q:
            checks.append(PreflightCheck(
                name="model_quality",
                status="ok",
                detail=f"{model_name} returned valid summary",
            ))
        elif err_q == "timeout":
            checks.append(PreflightCheck(
                name="model_quality",
                status="fail",
                detail=f"{model_name} did not respond within 60 seconds.",
                fix=(
                    "the model may be too large for your hardware, or the provider is overloaded.\n"
                    "       Try a smaller model or retry later."
                ),
            ))
        elif err_q is None:
            checks.append(PreflightCheck(
                name="model_quality",
                status="fail",
                detail=f"{model_name} returned an empty or unusable summary.",
                fix=(
                    "try a different model. For local providers, ensure you're using a model\n"
                    "       with at least 7B parameters (e.g., llama3.2, mistral)."
                ),
            ))
        else:
            checks.append(PreflightCheck(
                name="model_quality",
                status="fail",
                detail=f"{model_name} returned an error — {err_q}.",
                fix="verify the model name is correct. Run `ollama list` or check your provider dashboard.",
            ))

    # 3.5 Target directory checks
    _add_target_checks(checks, target)

    ready = all(c.status != "fail" for c in checks)
    return PreflightResult(
        checks=checks,
        ready=ready,
        provider=resolved_provider,
        model=model_name,
    )


def _add_target_checks(checks: list[PreflightCheck], target: Path) -> None:
    if not target.is_dir():
        checks.append(PreflightCheck(
            name="target",
            status="fail",
            detail=f"{target} is not a directory or does not exist.",
            fix=f"ensure {target} exists and is a directory before running ctx.",
        ))
        return

    # 3.5b Write permissions
    try:
        fd, tmp = tempfile.mkstemp(dir=target, prefix=".ctx-preflight-")
        os.close(fd)
        os.unlink(tmp)
        checks.append(PreflightCheck(
            name="target",
            status="ok",
            detail=f"{target.resolve()} is writable",
        ))
    except OSError as exc:
        checks.append(PreflightCheck(
            name="target",
            status="fail",
            detail=f"cannot write to {target} — {exc}",
            fix=f"check write permissions on {target}.",
        ))

    # 3.5c Git status
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=target,
            capture_output=True,
            check=True,
            timeout=5,
        )
        checks.append(PreflightCheck(
            name="git",
            status="ok",
            detail="repository detected.",
        ))
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        checks.append(PreflightCheck(
            name="git",
            status="info",
            detail="not a git repository. ctx will use incremental refresh (mtime-based).",
        ))

    # 3.5d .ctxignore status
    ctxignore = target / ".ctxignore"
    if ctxignore.exists():
        checks.append(PreflightCheck(
            name="ignore",
            status="ok",
            detail=f".ctxignore found at {ctxignore.resolve()}.",
        ))
    else:
        checks.append(PreflightCheck(
            name="ignore",
            status="info",
            detail="no .ctxignore found. Using built-in defaults.\n       See: https://pypi.org/project/ctx-tool/ for customization.",
        ))
