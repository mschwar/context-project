"""Type 1 Jev (System-One) bounded decision layer for ctx.

Implements the fleet Determinism Gradient (`code -> judge -> deliberate -> authorize`)
for codebase architecture and invariant decisions using TypeSafe AI's System-One
decision model (`jev-1.13.0` via `POST /v1/systemone`) paired with deterministic
`pre_rule` short-circuiting and `code` fallback rules.

Design invariants:
- Pure standard library; zero eager third-party SDK imports.
- Never raises on provider-side failure: missing credentials, `CTX_JEV=off`,
  network errors, timeouts, or malformed responses become explicit abstentions
  that route cleanly to the head's fallback tier (`code` or `deliberate`).
- Raw API keys and HTTP error bodies are NEVER printed, logged, persisted, or
  surfaced in exception/abstention strings.
- Cross-platform decision trace ledger (`.ctx-cache/jev_decisions.jsonl`) uses
  `ctx.lock.try_acquire_os_lock` so Linux, macOS, and Windows all work cleanly.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ctx.config import load_config
from ctx.lock import release_os_lock, try_acquire_os_lock

DEFAULT_JEV_BASE_URL = "https://api.typesafe.ai"
DEFAULT_JEV_MODEL = "jev-1.13.0"
JEV_TIMEOUT_SECONDS = 10.0
JEV_USD_PER_INPUT_TOKEN = 0.042 / 1_000_000

HEAD_TYPES = ("noul", "choice", "score")
TIERS = ("code", "judge", "deliberate", "authorize")
LADDER = ("SHADOW", "ADVISORY", "ROUTING", "ACTUATING")
PROVIDERS = ("jev", "code")
AUTHORITY_CEILING = "ADVISORY"
_DISABLED_TOKENS = frozenset({"off", "none", "false", "0", "disabled"})
_MODE_TO_LADDER = {
    "shadow": "SHADOW",
    "advisory": "ADVISORY",
    "routing": "ROUTING",
    "actuating": "ACTUATING",
}

REQUIRED_HEAD_FIELDS = (
    "id",
    "version",
    "type",
    "instructions",
    "criteria",
    "state_keys",
    "tier",
    "promotion_state",
    "ceiling",
    "provider",
    "thresholds",
    "fallback",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _rank(state: str) -> int:
    return LADDER.index(state)


def is_pinned_model(model: str | None) -> bool:
    return isinstance(model, str) and bool(model.strip()) and "latest" not in model.lower()


def is_authority_head(head: dict[str, Any]) -> bool:
    return bool(head.get("authority")) or head.get("tier") == "authorize"


def noul_decision_from_prob(
    p_true: float,
    positive_threshold: float = 0.5,
) -> tuple[bool, float]:
    """Classify a binary `noul` probability against `positive_threshold` in (0, 1)."""
    if (
        isinstance(p_true, bool)
        or not isinstance(p_true, (int, float))
        or not math.isfinite(float(p_true))
        or not (0.0 <= float(p_true) <= 1.0)
    ):
        raise ValueError(f"p_true must be a finite probability in [0, 1], got {p_true!r}")
    if (
        isinstance(positive_threshold, bool)
        or not isinstance(positive_threshold, (int, float))
        or not math.isfinite(float(positive_threshold))
        or not (0.0 < float(positive_threshold) < 1.0)
    ):
        raise ValueError(
            f"positive_threshold must be a finite number in (0, 1), got {positive_threshold!r}"
        )
    p = float(p_true)
    t = float(positive_threshold)
    if t == 0.5:
        return (p >= 0.5, min(1.0, max(0.5, max(p, 1.0 - p))))
    if p >= t:
        conf = 0.5 + 0.5 * (p - t) / (1.0 - t)
    else:
        conf = 0.5 + 0.5 * (t - p) / t
    return (p >= t, min(1.0, max(0.5, conf)))


def valid_outputs(head: dict[str, Any]) -> list[Any]:
    if head["type"] == "noul":
        return [True, False]
    if head["type"] == "choice":
        return list(head["criteria"])
    return list(range(len(head["criteria"])))


def _output_key(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def positive_threshold(head: dict[str, Any]) -> float:
    if head.get("type") != "noul":
        return 0.5
    thresholds = head.get("thresholds")
    if isinstance(thresholds, dict) and thresholds.get("positive_threshold") is not None:
        raw = thresholds["positive_threshold"]
        if (
            isinstance(raw, bool)
            or not isinstance(raw, (int, float))
            or not math.isfinite(float(raw))
            or not (0.0 < float(raw) < 1.0)
        ):
            raise ValueError(
                f"thresholds.positive_threshold must be a finite number in (0, 1), got {raw!r}"
            )
        return float(raw)
    return 0.5


# ── Deterministic pre-rules & fallback code rules ──────────────────────────

_HIGH_CONTRACT_TOKENS = (
    "lock",
    "fence",
    "auth",
    "token",
    "secret",
    "schema",
    "protocol",
    "contract",
    "api",
    "cli",
    "mcp",
    "server",
    "hook",
    "init",
    "cache",
    "config",
    "manifest",
    "skeleton",
    "security",
)


def _pre_invariant_drift_material(state: dict[str, Any]) -> bool | None:
    bdocs = state.get("boundary_docs_changed") or []
    eps = state.get("entrypoints_changed") or []
    surfaces = state.get("operational_surfaces_changed") or []
    removed = state.get("removed_symbols") or []
    added = state.get("added_symbols") or []
    imports = state.get("changed_imports") or []

    if bdocs or eps or surfaces or removed:
        return True
    if not added and not imports:
        return False
    return None


def _rule_invariant_drift_material(state: dict[str, Any]) -> bool:
    pre = _pre_invariant_drift_material(state)
    if pre is not None:
        return pre
    added = [str(s).lower() for s in (state.get("added_symbols") or [])]
    imports = [str(i).lower() for i in (state.get("changed_imports") or [])]
    touched = list(state.get("touched_subsystems") or [])
    if len(touched) >= 2 or len(added) >= 4 or len(imports) >= 3:
        return True
    combined = " ".join([*added, *imports])
    return any(tok in combined for tok in _HIGH_CONTRACT_TOKENS)


def _pre_subsystem_arch_role(state: dict[str, Any]) -> str | None:
    raw_path = str(state.get("path") or "").strip().lower().strip("/")
    tokens = {tok for tok in re.split(r"[/_\-.]+", raw_path) if tok}
    if tokens & {"tests", "test", "benchmarks", "benchmark", "qa", "e2e", "specs", "fixtures"}:
        return "verification_tooling"
    if tokens & {"docs", "doc", "adr", "adrs", "documents", "archive", "designs", "rfcs"}:
        return "docs_governance"
    return None


def _rule_subsystem_arch_role(state: dict[str, Any]) -> str:
    pre = _pre_subsystem_arch_role(state)
    if pre is not None:
        return pre
    raw_path = str(state.get("path") or "").strip().lower().strip("/")
    path_tokens = {tok for tok in re.split(r"[/_\-.]+", raw_path) if tok}
    symbols = " ".join(str(s).lower() for s in (state.get("key_symbols") or []))
    ext_deps = {str(d).lower() for d in (state.get("external_deps") or [])}
    surfaces = {str(k).lower() for k in (state.get("operational_surface_kinds") or [])}
    langs = {str(lang).lower() for lang in (state.get("languages") or [])}

    if not langs or langs <= {"markdown"}:
        if raw_path in {".", ""} and not symbols:
            return "docs_governance"
    if ext_deps & {"anthropic", "openai", "httpx", "requests", "boto3", "psycopg", "redis", "sqlalchemy"} or (
        path_tokens & {"adapter", "adapters", "provider", "providers", "client", "clients", "git", "hook", "hooks", "storage", "db", "connector", "connectors"}
    ):
        if not (path_tokens & {"core", "domain"}):
            return "adapter_integration"
    if surfaces & {"cli_command", "http_route", "mcp_tool", "mcp_resource"} or (
        path_tokens & {"cli", "cmd", "server", "routes", "web", "ui", "mcp", "frontend"}
    ):
        if not (path_tokens & {"core", "engine"}):
            return "entrypoint_interface"
    if path_tokens & {"util", "utils", "common", "shared", "helper", "helpers", "config", "types"}:
        return "shared_utility"
    if symbols or langs:
        return "core_domain"
    return "shared_utility"


def _pre_operational_surface_exposure(state: dict[str, Any]) -> str | None:
    name = str(state.get("name") or "").strip()
    file_path = str(state.get("file") or "").strip().lower()
    detail = str(state.get("detail") or "").strip().lower()
    if any(part in {"tests", "test", "benchmarks", "scripts"} for part in file_path.split("/")):
        return "diagnostic_dev"
    tokens = name.split()
    leaf = tokens[-1] if tokens else name
    if leaf.startswith("_") or "internal:" in detail or "hidden=true" in detail:
        return "internal_plumbing"
    upper_name = name.upper()
    if any(tag in upper_name for tag in ("DEBUG", "BENCHMARK", "TRACE_DEV", "TEST_ONLY")):
        return "diagnostic_dev"
    return None


def _rule_operational_surface_exposure(state: dict[str, Any]) -> str:
    pre = _pre_operational_surface_exposure(state)
    if pre is not None:
        return pre
    kind = str(state.get("kind") or "").strip().lower()
    if kind in {"cli_command", "http_route", "mcp_tool", "mcp_resource", "env_var"}:
        return "public_contract"
    return "internal_plumbing"


RULES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "pre_invariant_drift_material": _pre_invariant_drift_material,
    "rule_invariant_drift_material": _rule_invariant_drift_material,
    "pre_subsystem_arch_role": _pre_subsystem_arch_role,
    "rule_subsystem_arch_role": _rule_subsystem_arch_role,
    "pre_operational_surface_exposure": _pre_operational_surface_exposure,
    "rule_operational_surface_exposure": _rule_operational_surface_exposure,
}


BUILTIN_HEADS: dict[str, dict[str, Any]] = {
    "invariant_drift_material": {
        "id": "invariant_drift_material",
        "version": "1.0.0",
        "type": "noul",
        "instructions": (
            "Decide whether the repository structural delta in `state` represents material "
            "architectural or governance drift that requires re-synthesizing repository invariants."
        ),
        "criteria": {
            "true": (
                "Any entry in `boundary_docs_changed` (e.g. AGENTS.md, architecture.md), "
                "`entrypoints_changed`, `operational_surfaces_changed`, or `removed_symbols`, "
                "OR new cross-file `changed_imports` / `added_symbols` introducing locking, "
                "fencing, concurrency, security, config, or protocol contracts."
            ),
            "false": (
                "No boundary docs, entrypoints, operational surfaces, or symbols removed, AND "
                "changes are either empty implementation edits or a localized presentation/formatting "
                "helper with no new cross-module contract or import coupling."
            ),
        },
        "state_keys": [
            "repo_name",
            "boundary_docs_changed",
            "entrypoints_changed",
            "operational_surfaces_changed",
            "added_symbols",
            "removed_symbols",
            "changed_imports",
            "touched_subsystems",
        ],
        "tier": "judge",
        "promotion_state": "ROUTING",
        "ceiling": "ACTUATING",
        "provider": {"name": "jev", "model": DEFAULT_JEV_MODEL},
        "pre_rule": "pre_invariant_drift_material",
        "rule": "rule_invariant_drift_material",
        "thresholds": {"act_min_confidence": 0.70, "positive_threshold": 0.45},
        "fallback": "deliberate",
    },
    "subsystem_arch_role": {
        "id": "subsystem_arch_role",
        "version": "1.0.0",
        "type": "choice",
        "instructions": (
            "Classify the primary architectural role of the repository subsystem described in `state` "
            "using its `path`, `languages`, `key_symbols`, `internal_deps`, `external_deps`, and "
            "`operational_surface_kinds`."
        ),
        "criteria": {
            "entrypoint_interface": (
                "CLI command layer, HTTP/REST API server, MCP protocol handler, or user/agent-facing dispatch surface."
            ),
            "core_domain": (
                "Primary domain engine, structural compiler, graph analyzer, state machine, or core business logic."
            ),
            "adapter_integration": (
                "External service/LLM provider client, git/filesystem/OS hook adapter, or persistence driver."
            ),
            "shared_utility": (
                "Cross-cutting helper, configuration loader, hashing/formatting utility, or shared type definitions."
            ),
            "verification_tooling": (
                "Automated test suite, adversarial QA harness, benchmark runner, or test fixture package."
            ),
            "docs_governance": (
                "Architecture decision records, operator runbooks, agent contracts, or documentation assets."
            ),
        },
        "state_keys": [
            "path",
            "file_count",
            "languages",
            "key_symbols",
            "internal_deps",
            "external_deps",
            "operational_surface_kinds",
        ],
        "tier": "judge",
        "promotion_state": "ACTUATING",
        "ceiling": "ACTUATING",
        "provider": {"name": "jev", "model": DEFAULT_JEV_MODEL},
        "pre_rule": "pre_subsystem_arch_role",
        "rule": "rule_subsystem_arch_role",
        "thresholds": {"act_min_confidence": 0.65},
        "fallback": "code",
    },
    "operational_surface_exposure": {
        "id": "operational_surface_exposure",
        "version": "1.0.0",
        "type": "choice",
        "authority": True,
        "instructions": (
            "Determine the external contract exposure tier of the operational surface in `state` "
            "(`kind`, `name`, `file`, `detail`)."
        ),
        "criteria": {
            "public_contract": (
                "Supported external CLI command, HTTP route, MCP tool/resource, or documented configuration variable."
            ),
            "internal_plumbing": (
                "Hidden hook callback, private worker entrypoint, or internal coordination plumbing not for external callers."
            ),
            "diagnostic_dev": (
                "Development benchmark, debug flag, test harness helper, or local-only diagnostic utility."
            ),
        },
        "state_keys": ["kind", "name", "file", "detail"],
        "tier": "judge",
        "promotion_state": "ADVISORY",
        "ceiling": "ADVISORY",
        "provider": {"name": "jev", "model": DEFAULT_JEV_MODEL},
        "pre_rule": "pre_operational_surface_exposure",
        "rule": "rule_operational_surface_exposure",
        "thresholds": {"act_min_confidence": 0.70},
        "fallback": "code",
    },
}


# ── Head validation, loading & configuration ───────────────────────────────


def validate_head(head: Any, expected_id: str | None = None) -> list[str]:
    if not isinstance(head, dict):
        return ["head spec must be a JSON object"]
    errors = [f"missing field: {k}" for k in REQUIRED_HEAD_FIELDS if k not in head]
    if errors:
        return errors
    if expected_id is not None and head["id"] != expected_id:
        errors.append(f"id {head['id']!r} does not match expected {expected_id!r}")
    for key in ("id", "version", "instructions"):
        if not isinstance(head[key], str) or not head[key].strip():
            errors.append(f"{key} must be a non-empty string")
    if head["type"] not in HEAD_TYPES:
        errors.append(f"type must be one of {HEAD_TYPES}")
    elif head["type"] == "noul":
        crit = head["criteria"]
        if crit is not None and (not isinstance(crit, dict) or not set(crit) <= {"true", "false"}):
            errors.append("noul criteria must be null or map true/false")
    elif head["type"] == "choice":
        crit = head["criteria"]
        if not isinstance(crit, dict) or not (2 <= len(crit) <= 255):
            errors.append("choice criteria must map 2-255 options to descriptions")
    elif head["type"] == "score":
        crit = head["criteria"]
        if not isinstance(crit, list) or not (2 <= len(crit) <= 10):
            errors.append("score criteria must be a list of 2-10 ordered levels")

    if not isinstance(head["state_keys"], list) or not all(isinstance(k, str) for k in head["state_keys"]):
        errors.append("state_keys must be a list of strings")
    for key in ("tier", "fallback"):
        if head[key] not in TIERS:
            errors.append(f"{key} must be one of {TIERS}")
    for key in ("promotion_state", "ceiling"):
        if head[key] not in LADDER:
            errors.append(f"{key} must be one of {LADDER}")
    if not errors:
        if _rank(head["promotion_state"]) > _rank(head["ceiling"]):
            errors.append("promotion_state exceeds ceiling")
        if is_authority_head(head) and _rank(head["ceiling"]) > _rank(AUTHORITY_CEILING):
            errors.append(f"authority heads have permanent ceiling {AUTHORITY_CEILING}")

    thresholds = head["thresholds"]
    act_min = thresholds.get("act_min_confidence") if isinstance(thresholds, dict) else None
    if not isinstance(act_min, (int, float)) or isinstance(act_min, bool) or not (0.0 <= act_min <= 1.0):
        errors.append("thresholds.act_min_confidence must be in [0, 1]")

    provider = head["provider"]
    if not isinstance(provider, dict) or provider.get("name") not in PROVIDERS:
        errors.append(f"provider.name must be one of {PROVIDERS}")
    elif provider["name"] == "jev":
        if not isinstance(provider.get("model"), str) or not provider["model"].strip():
            errors.append("provider.model is required for jev")
        elif _rank(head["promotion_state"]) > _rank("SHADOW") and not is_pinned_model(provider.get("model")):
            errors.append("model aliases are only permitted in SHADOW; pin an exact Jev model version")

    for rule_field in ("pre_rule", "rule"):
        rname = head.get(rule_field)
        if rname is not None and (not isinstance(rname, str) or rname not in RULES):
            errors.append(f"{rule_field} {rname!r} is not a registered deterministic rule")
    return errors


_HEAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def list_head_ids(root: Path | None = None) -> list[str]:
    ids = set(BUILTIN_HEADS.keys())
    if root is not None:
        custom_dir = root.resolve() / ".ctx" / "heads"
        if custom_dir.is_dir():
            for p in custom_dir.glob("*.json"):
                if _HEAD_ID_RE.fullmatch(p.stem):
                    ids.add(p.stem)
    return sorted(ids)


def load_head(head_id: str, root: Path | None = None) -> dict[str, Any]:
    if not isinstance(head_id, str) or not _HEAD_ID_RE.fullmatch(head_id):
        raise ValueError(
            f"Invalid Jev head ID {head_id!r}: must match ^[A-Za-z0-9_-]+$"
        )
    if root is not None:
        custom_dir = (root.resolve() / ".ctx" / "heads").resolve()
        custom = (custom_dir / f"{head_id}.json").resolve()
        if custom.parent == custom_dir and custom.is_file():
            try:
                raw = json.loads(custom.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Malformed custom head {head_id}: {exc}") from exc
            errs = validate_head(raw, expected_id=head_id)
            if errs:
                raise ValueError(f"Invalid head {head_id}: {'; '.join(errs)}")
            return deepcopy(raw)
    if head_id not in BUILTIN_HEADS:
        raise ValueError(f"Unknown Jev head: {head_id!r}. Available: {', '.join(sorted(BUILTIN_HEADS))}")
    head = deepcopy(BUILTIN_HEADS[head_id])
    errs = validate_head(head, expected_id=head_id)
    if errs:
        raise ValueError(f"Invalid builtin head {head_id}: {'; '.join(errs)}")
    return head


def list_heads_safe(root: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Load all governed Jev heads safely, skipping or falling back on malformed custom files."""
    heads: list[dict[str, Any]] = []
    warnings: list[str] = []
    for hid in list_head_ids(root):
        try:
            heads.append(load_head(hid, root))
        except ValueError as exc:
            warnings.append(str(exc))
            if hid in BUILTIN_HEADS:
                heads.append(load_head(hid, None))
    return heads, warnings


def check_state(head: dict[str, Any], state: Any) -> None:
    if not isinstance(state, dict):
        raise ValueError(f"Head {head['id']} requires a dict state")
    missing = [k for k in head["state_keys"] if k not in state]
    if missing:
        raise ValueError(f"State missing required keys for head {head['id']}: {', '.join(missing)}")


def effective_jev_mode(root: Path | None = None) -> str:
    """Resolve Jev operating mode: 'off' | 'auto' | 'shadow' | 'advisory' | 'routing' | 'actuating'."""
    env_val = os.environ.get("CTX_JEV")
    if env_val is not None:
        cleaned = env_val.strip().lower()
        if cleaned in _DISABLED_TOKENS:
            return "off"
        if cleaned in {"auto", "on", "1", "true", "yes"}:
            return "auto"
        if cleaned in _MODE_TO_LADDER:
            return cleaned
    if root is not None and root.exists():
        start_dir = root.resolve() if root.is_dir() else root.resolve().parent
        try:
            cfg = load_config(start_dir, require_api_key=False)
            cleaned = str(cfg.jev_mode or "auto").strip().lower()
            if cleaned in _DISABLED_TOKENS:
                return "off"
            if cleaned in _MODE_TO_LADDER:
                return cleaned
            return "auto"
        except Exception:
            return "auto"
    return "auto"


def resolve_jev_base_url() -> str:
    for env_key in ("TYPESAFE_BASE_URL", "CTX_JEV_URL", "CTX_JEV_BASE_URL"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    return DEFAULT_JEV_BASE_URL


def _resolve_api_key(*, allow_vault: bool = False) -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    use_vault = allow_vault or os.environ.get("CTX_JEV_USE_OP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not use_vault:
        return None
    vault_ref = (
        os.environ.get("CTX_JEV_OP_REF", "").strip()
        or os.environ.get("TYPESAFE_OP_REF", "").strip()
    )
    if not vault_ref or vault_ref.lower() in _DISABLED_TOKENS:
        return None
    try:
        proc = subprocess.run(
            ["op", "read", vault_ref],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


# ── Provider execution (`code` & `jev`) ────────────────────────────────────


def _result(
    provider: str,
    model: str | None,
    *,
    output: Any = None,
    distribution: dict[str, float] | None = None,
    confidence: float | None = None,
    confidence_source: str | None = None,
    abstain_reason: str | None = None,
    latency_ms: float = 0.0,
    input_tokens: int = 0,
    expected_score: Any = None,
) -> dict[str, Any]:
    abstained = abstain_reason is not None
    res: dict[str, Any] = {
        "output": None if abstained else output,
        "distribution": None if abstained else distribution,
        "confidence": None if abstained else confidence,
        "confidence_source": None if abstained else confidence_source,
        "abstained": abstained,
        "abstain_reason": abstain_reason,
        "latency_ms": round(latency_ms, 3),
        "input_tokens": input_tokens,
        "cost_usd": round(input_tokens * JEV_USD_PER_INPUT_TOKEN, 9) if provider == "jev" else 0.0,
        "provider": provider,
        "model": model,
    }
    if expected_score is not None and not abstained:
        res["expected_score"] = expected_score
    return res


def _try_pre_rule(head: dict[str, Any], state: dict[str, Any], *, provider: str, model: str | None) -> dict[str, Any] | None:
    pre_name = head.get("pre_rule")
    rule = RULES.get(pre_name) if isinstance(pre_name, str) else None
    if rule is None:
        return None
    started = time.perf_counter()
    try:
        out = rule(state)
    except Exception:
        out = None
    elapsed = (time.perf_counter() - started) * 1000
    opts = valid_outputs(head)
    if out is not None and out in opts:
        dist = {_output_key(o): (1.0 if o == out else 0.0) for o in opts}
        return _result(
            provider,
            model,
            output=out,
            distribution=dist,
            confidence=1.0,
            confidence_source=f"pre_rule:{pre_name}",
            latency_ms=elapsed,
            input_tokens=0,
        )
    return None


def run_code(head: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    rule_name = head.get("rule")
    rule = RULES.get(rule_name) if isinstance(rule_name, str) else None
    if rule is None:
        return _result("code", None, abstain_reason=f"RULE_MISSING: {rule_name}")
    model = f"rule:{rule_name}"
    started = time.perf_counter()
    try:
        out = rule(state)
    except Exception as exc:
        return _result(
            "code",
            model,
            abstain_reason=f"RULE_ERROR: {type(exc).__name__}",
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    elapsed = (time.perf_counter() - started) * 1000
    if out is None:
        return _result("code", model, abstain_reason="RULE_NO_MATCH", latency_ms=elapsed)
    opts = valid_outputs(head)
    if out not in opts:
        return _result("code", model, abstain_reason=f"RULE_INVALID_OUTPUT: {out!r}", latency_ms=elapsed)
    dist = {_output_key(o): (1.0 if o == out else 0.0) for o in opts}
    return _result(
        "code",
        model,
        output=out,
        distribution=dist,
        confidence=1.0,
        confidence_source="rule",
        latency_ms=elapsed,
    )


def _question_payload(head: dict[str, Any]) -> dict[str, Any]:
    q: dict[str, Any] = {"type": head["type"], "instructions": head["instructions"]}
    if head.get("criteria") is not None:
        q["criteria"] = head["criteria"]
    return q


def _parse_jev_answer(head: dict[str, Any], answer: Any) -> dict[str, Any]:
    if not isinstance(answer, dict):
        return {"abstain_reason": "JEV_BAD_RESPONSE: missing answer"}
    if head["type"] == "noul":
        p = answer.get("noul")
        if (
            not isinstance(p, (int, float))
            or isinstance(p, bool)
            or not math.isfinite(float(p))
            or not (0.0 <= float(p) <= 1.0)
        ):
            return {"abstain_reason": "JEV_BAD_RESPONSE: noul probability missing"}
        tau = positive_threshold(head)
        out_bool, conf = noul_decision_from_prob(float(p), tau)
        return {
            "output": out_bool,
            "distribution": {"true": float(p), "false": 1.0 - float(p)},
            "confidence": conf,
            "confidence_source": "derived",
        }

    probs = answer.get("probabilities")
    distribution = (
        {str(k): float(v) for k, v in probs.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if isinstance(probs, dict)
        else None
    )
    extra: dict[str, Any] = {}
    if head["type"] == "choice":
        output = answer.get("choice")
    else:
        if not distribution:
            return {"abstain_reason": "JEV_BAD_RESPONSE: score probabilities missing"}
        modal = max(distribution, key=distribution.get)  # type: ignore[arg-type]
        output = int(modal) if modal.isdigit() else None
        extra["expected_score"] = answer.get("score")

    if output not in valid_outputs(head):
        return {"abstain_reason": f"JEV_INVALID_OUTPUT: {output!r}"}
    confidence = answer.get("confidence")
    source = "vendor"
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = max(distribution.values()) if distribution else None
        source = "derived" if confidence is not None else None
    return {
        "output": output,
        "distribution": distribution,
        "confidence": None if confidence is None else float(confidence),
        "confidence_source": source,
        **extra,
    }


def _split_tokens(total: int, n: int) -> list[int]:
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def run_jev(
    heads: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    root: Path | None = None,
    model: str | None = None,
    allow_vault: bool = False,
    skip_pre_rule: bool = False,
) -> dict[str, dict[str, Any]]:
    """Evaluate one or more heads on a shared `state` in a single TypeSafe `/v1/systemone` request."""
    if not heads:
        return {}
    resolved_model = model or heads[0].get("provider", {}).get("model") or DEFAULT_JEV_MODEL
    results: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []

    for head in heads:
        if not skip_pre_rule:
            short = _try_pre_rule(head, state, provider="jev", model=resolved_model)
            if short is not None:
                results[head["id"]] = short
                continue
        pending.append(head)

    if not pending:
        return results

    def _abstain_all(reason: str, latency_ms: float = 0.0) -> dict[str, dict[str, Any]]:
        for h in pending:
            results[h["id"]] = _result("jev", resolved_model, abstain_reason=reason, latency_ms=latency_ms)
        return results

    mode = effective_jev_mode(root)
    if mode == "off":
        return _abstain_all("JEV_UNAVAILABLE: disabled (CTX_JEV=off)")

    key = _resolve_api_key(allow_vault=allow_vault)
    if not key:
        return _abstain_all("JEV_UNAVAILABLE: no key")

    base_url = resolve_jev_base_url().rstrip("/")
    body = {
        "model": resolved_model,
        "state": state,
        "questions": {h["id"]: _question_payload(h) for h in pending},
    }
    req = urllib.request.Request(
        f"{base_url}/v1/systemone",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=JEV_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        exc.close()  # never leak upstream error body
        return _abstain_all(f"JEV_UNAVAILABLE: HTTP {exc.code}", (time.perf_counter() - started) * 1000)
    except urllib.error.URLError as exc:
        reason = type(exc.reason).__name__ if not isinstance(exc.reason, str) else "URLError"
        return _abstain_all(f"JEV_UNAVAILABLE: network {reason}", (time.perf_counter() - started) * 1000)
    except TimeoutError:
        return _abstain_all("JEV_UNAVAILABLE: timeout", (time.perf_counter() - started) * 1000)
    except OSError as exc:
        return _abstain_all(f"JEV_UNAVAILABLE: {type(exc).__name__}", (time.perf_counter() - started) * 1000)

    latency_ms = (time.perf_counter() - started) * 1000
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _abstain_all("JEV_BAD_RESPONSE: invalid JSON", latency_ms)
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        return _abstain_all("JEV_BAD_RESPONSE: missing answers", latency_ms)

    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    in_tok = usage.get("input_tokens", 0)
    if not isinstance(in_tok, int) or isinstance(in_tok, bool) or in_tok < 0:
        in_tok = 0
    shares = _split_tokens(in_tok, len(pending))
    served_model = payload.get("model") if isinstance(payload.get("model"), str) else resolved_model

    for head, tok_share in zip(pending, shares):
        parsed = _parse_jev_answer(head, payload["answers"].get(head["id"]))
        res = _result("jev", served_model, latency_ms=latency_ms, input_tokens=tok_share, **parsed)
        res["batch_size"] = len(pending)
        results[head["id"]] = res
    return results


# ── Governor routing & decision tracing ────────────────────────────────────


def effective_promotion_state(head: dict[str, Any], root: Path | None = None) -> str:
    mode = effective_jev_mode(root)
    head_state = str(head["promotion_state"])
    ceiling = str(head["ceiling"])
    if is_authority_head(head) and _rank(ceiling) > _rank(AUTHORITY_CEILING):
        ceiling = AUTHORITY_CEILING
    if mode in _MODE_TO_LADDER:
        requested = _MODE_TO_LADDER[mode]
        clamped_rank = min(_rank(requested), _rank(ceiling))
        return LADDER[clamped_rank]
    clamped_rank = min(_rank(head_state), _rank(ceiling))
    return LADDER[clamped_rank]


def route_decision(
    head: dict[str, Any],
    result: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    fallback = f"fallback:{head['fallback']}"
    pstate = effective_promotion_state(head, root)
    if pstate == "SHADOW":
        return {"route": fallback, "acted": False, "promotion_state": pstate, "reason": "SHADOW: recorded only"}
    threshold = float(head["thresholds"]["act_min_confidence"])
    confidence = result.get("confidence")
    if pstate == "ADVISORY":
        gov: dict[str, Any] = {
            "route": fallback,
            "acted": False,
            "promotion_state": pstate,
            "reason": "ADVISORY: fallback decides",
        }
        if not result["abstained"] and confidence is not None and confidence >= threshold:
            gov["recommendation"] = result["output"]
        return gov
    if result["abstained"]:
        return {
            "route": fallback,
            "acted": False,
            "promotion_state": pstate,
            "reason": f"{pstate}: abstained ({result['abstain_reason']})",
        }
    if confidence is None or confidence < threshold:
        return {
            "route": fallback,
            "acted": False,
            "promotion_state": pstate,
            "reason": f"{pstate}: confidence {confidence} below {threshold}",
        }
    return {
        "route": "head",
        "acted": True,
        "promotion_state": pstate,
        "reason": f"{pstate}: confidence >= {threshold}",
    }


def decisions_trace_path(root: Path) -> Path:
    return root.resolve() / ".ctx-cache" / "jev_decisions.jsonl"


def append_decision_traces(root: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []
    trace_file = decisions_trace_path(root)
    guard_file = trace_file.parent / ".jev_decisions.guard"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    fd: int | None = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        fd = try_acquire_os_lock(guard_file)
        if fd is not None:
            break
        time.sleep(0.01)
    if fd is None:
        raise OSError("Timed out acquiring Jev trace guard lock")

    try:
        existing_count: int | None = 0
        if trace_file.is_file():
            st_size = trace_file.stat().st_size
            if st_size <= 262_144:
                with trace_file.open("r", encoding="utf-8") as fh:
                    existing_count = sum(1 for line in fh if line.strip())
            else:
                existing_count = None
        written: list[dict[str, Any]] = []
        with trace_file.open("a", encoding="utf-8") as fh:
            for offset, rec in enumerate(records, start=1):
                entry: dict[str, Any] = {"ts": _utc_now(), **rec}
                if existing_count is not None:
                    entry["sequence"] = existing_count + offset
                fh.write(_canonical_json(entry) + "\n")
                written.append(entry)
            fh.flush()
        return written
    finally:
        release_os_lock(fd)


def read_decision_traces(root: Path) -> list[dict[str, Any]]:
    trace_file = decisions_trace_path(root)
    if not trace_file.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def decide(
    head_ids: list[str],
    state: dict[str, Any],
    *,
    root: Path | None = None,
    provider: str | None = None,
    allow_vault: bool = False,
    record_trace: bool = True,
) -> dict[str, Any]:
    """Run one or more governed heads on `state`, resolving fallback outputs when needed."""
    heads = [load_head(hid, root) for hid in head_ids]
    for head in heads:
        check_state(head, state)

    by_provider: dict[str, list[dict[str, Any]]] = {}
    for head in heads:
        pname = provider or head["provider"]["name"]
        if pname not in PROVIDERS:
            raise ValueError(f"Unknown Jev provider {pname!r}; expected one of {PROVIDERS}")
        by_provider.setdefault(pname, []).append(head)

    raw_results: dict[str, dict[str, Any]] = {}
    for pname, group in by_provider.items():
        if pname == "code":
            for h in group:
                raw_results[h["id"]] = run_code(h, state)
        else:
            raw_results.update(run_jev(group, state, root=root, allow_vault=allow_vault))

    decisions: list[dict[str, Any]] = []
    for head in heads:
        res = raw_results[head["id"]]
        gov = route_decision(head, res, root=root)
        effective_output = res["output"] if gov["acted"] else None
        effective_tier = "judge" if (gov["acted"] and res["provider"] == "jev") else ("code" if res["provider"] == "code" else head["fallback"])
        is_unavailable = bool(res["abstained"]) and str(res.get("abstain_reason") or "").startswith("JEV_UNAVAILABLE")
        if not gov["acted"] and (head["fallback"] == "code" or (is_unavailable and head.get("rule"))):
            code_fb = run_code(head, state)
            if not code_fb["abstained"]:
                effective_output = code_fb["output"]
                effective_tier = "code"
        elif gov["acted"] and res["provider"] == "code":
            effective_tier = "code"

        rec = {
            "type": "decision",
            "id": uuid.uuid4().hex,
            "head_id": head["id"],
            "head_version": head["version"],
            "head_digest": _digest(head),
            "promotion_state": gov["promotion_state"],
            "tier": effective_tier,
            "provider": res["provider"],
            "model": res["model"],
            "state_digest": _digest(state),
            "output": res["output"],
            "effective_output": effective_output,
            "distribution": res["distribution"],
            "confidence": res["confidence"],
            "confidence_source": res["confidence_source"],
            "abstained": res["abstained"],
            "abstain_reason": res["abstain_reason"],
            "latency_ms": res["latency_ms"],
            "input_tokens": res["input_tokens"],
            "cost_usd": res["cost_usd"],
            "route": gov["route"],
            "acted": gov["acted"],
            "route_reason": gov["reason"],
            "recommendation": gov.get("recommendation"),
        }
        if "expected_score" in res:
            rec["expected_score"] = res["expected_score"]
        decisions.append(rec)

    if record_trace and root is not None:
        try:
            decisions = append_decision_traces(root, decisions)
        except OSError:
            pass
    return {"result": "DECIDED", "decisions": decisions}


# ── Gold evaluation corpus & benchmark runner ──────────────────────────────

GOLD_EVAL_CASES: list[dict[str, Any]] = [
    # 1. invariant_drift_material cases
    {
        "case_id": "drift_01_boundary_doc_updated",
        "head_id": "invariant_drift_material",
        "expected": True,
        "state": {
            "repo_name": "ctx-tool",
            "boundary_docs_changed": ["AGENTS.md"],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": [],
            "removed_symbols": [],
            "changed_imports": [],
            "touched_subsystems": ["."],
        },
    },
    {
        "case_id": "drift_02_noop_implementation_edit",
        "head_id": "invariant_drift_material",
        "expected": False,
        "state": {
            "repo_name": "ctx-tool",
            "boundary_docs_changed": [],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": [],
            "removed_symbols": [],
            "changed_imports": [],
            "touched_subsystems": ["src/ctx"],
        },
    },
    {
        "case_id": "drift_03_minor_sparkline_helper",
        "head_id": "invariant_drift_material",
        "expected": False,
        "state": {
            "repo_name": "ctx-tool",
            "boundary_docs_changed": [],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": ["stats_board.py:fn format_ascii_bar"],
            "removed_symbols": [],
            "changed_imports": [],
            "touched_subsystems": ["src/ctx"],
        },
    },
    {
        "case_id": "drift_04_lock_publication_fence_contract",
        "head_id": "invariant_drift_material",
        "expected": True,
        "state": {
            "repo_name": "ctx-tool",
            "boundary_docs_changed": [],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": [
                "lock.py:fn lock_publication_fence_for_path",
                "lock.py:class LockSupersededError",
            ],
            "removed_symbols": [],
            "changed_imports": ["init.py -> ctx.lock"],
            "touched_subsystems": ["src/ctx"],
        },
    },
    {
        "case_id": "drift_05_removed_public_api_symbol",
        "head_id": "invariant_drift_material",
        "expected": True,
        "state": {
            "repo_name": "ctx-tool",
            "boundary_docs_changed": [],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": [],
            "removed_symbols": ["api.py:fn build_fleet_capsule"],
            "changed_imports": [],
            "touched_subsystems": ["src/ctx"],
        },
    },
    # 2. subsystem_arch_role cases
    {
        "case_id": "role_01_tests_suite",
        "head_id": "subsystem_arch_role",
        "expected": "verification_tooling",
        "state": {
            "path": "tests",
            "file_count": 44,
            "languages": ["Python"],
            "key_symbols": ["test_api.py:fn test_refresh_incremental"],
            "internal_deps": ["ctx.api"],
            "external_deps": ["pytest"],
            "operational_surface_kinds": [],
        },
    },
    {
        "case_id": "role_02_adr_docs",
        "head_id": "subsystem_arch_role",
        "expected": "docs_governance",
        "state": {
            "path": "docs/adr",
            "file_count": 6,
            "languages": ["Markdown"],
            "key_symbols": [],
            "internal_deps": [],
            "external_deps": [],
            "operational_surface_kinds": [],
        },
    },
    {
        "case_id": "role_03_cli_and_mcp_surface",
        "head_id": "subsystem_arch_role",
        "expected": "entrypoint_interface",
        "state": {
            "path": "src/server_routes",
            "file_count": 3,
            "languages": ["Python"],
            "key_symbols": ["cli.py:fn cli", "mcp_server.py:class CtxMCPServer"],
            "internal_deps": ["app.core"],
            "external_deps": ["click", "fastapi"],
            "operational_surface_kinds": ["cli_command", "http_route", "mcp_tool"],
        },
    },
    {
        "case_id": "role_04_llm_provider_adapters",
        "head_id": "subsystem_arch_role",
        "expected": "adapter_integration",
        "state": {
            "path": "src/providers",
            "file_count": 4,
            "languages": ["Python"],
            "key_symbols": ["anthropic_client.py:class AnthropicAdapter", "openai_client.py:class OpenAIAdapter"],
            "internal_deps": ["app.config"],
            "external_deps": ["anthropic", "openai", "httpx"],
            "operational_surface_kinds": [],
        },
    },
    {
        "case_id": "role_05_core_graph_compiler",
        "head_id": "subsystem_arch_role",
        "expected": "core_domain",
        "state": {
            "path": "src/compiler",
            "file_count": 8,
            "languages": ["Python"],
            "key_symbols": ["graph.py:fn build_dependency_graph", "resolver.py:class IdentityCompiler"],
            "internal_deps": ["app.models"],
            "external_deps": ["pathspec"],
            "operational_surface_kinds": [],
        },
    },
    # 3. operational_surface_exposure cases
    {
        "case_id": "surface_01_public_cli_refresh",
        "head_id": "operational_surface_exposure",
        "expected": "public_contract",
        "state": {
            "kind": "cli_command",
            "name": "ctx refresh",
            "file": "src/ctx/cli.py",
            "detail": "flags: --force, --setup, --watch, --dry-run, --until-complete",
        },
    },
    {
        "case_id": "surface_02_hidden_git_hook_callback",
        "head_id": "operational_surface_exposure",
        "expected": "internal_plumbing",
        "state": {
            "kind": "cli_command",
            "name": "ctx _hook",
            "file": "src/ctx/cli.py",
            "detail": "hidden=true; flags: --trigger, --root",
        },
    },
    {
        "case_id": "surface_03_benchmark_debug_env",
        "head_id": "operational_surface_exposure",
        "expected": "diagnostic_dev",
        "state": {
            "kind": "env_var",
            "name": "CTX_DEBUG_BENCHMARK_SEED",
            "file": "tests/helpers.py",
            "detail": "os.getenv",
        },
    },
    {
        "case_id": "surface_04_public_mcp_tool",
        "head_id": "operational_surface_exposure",
        "expected": "public_contract",
        "state": {
            "kind": "mcp_tool",
            "name": "ctx_impact",
            "file": "src/ctx/mcp_server.py",
            "detail": "Analyze directed dependency blast radius and coupled tests",
        },
    },
    # 4. Held-out segment-disambiguation & non-pre-rule cases
    {
        "case_id": "role_06_api_client_segment_disambiguation",
        "head_id": "subsystem_arch_role",
        "expected": "adapter_integration",
        "state": {
            "path": "src/api_client",
            "file_count": 3,
            "languages": ["Python"],
            "key_symbols": ["http_transport.py:class RemoteApiClient"],
            "internal_deps": ["app.models"],
            "external_deps": ["httpx"],
            "operational_surface_kinds": [],
        },
    },
    {
        "case_id": "role_07_build_guide_core_disambiguation",
        "head_id": "subsystem_arch_role",
        "expected": "core_domain",
        "state": {
            "path": "src/query_builder",
            "file_count": 5,
            "languages": ["Python"],
            "key_symbols": ["planner.py:class QueryPlanCompiler", "feedback_loop.py:fn rank_results"],
            "internal_deps": ["app.ast_nodes"],
            "external_deps": [],
            "operational_surface_kinds": [],
        },
    },
    {
        "case_id": "drift_06_localized_color_formatter",
        "head_id": "invariant_drift_material",
        "expected": False,
        "state": {
            "repo_name": "ctx-tool",
            "boundary_docs_changed": [],
            "entrypoints_changed": [],
            "operational_surfaces_changed": [],
            "added_symbols": ["table_printer.py:fn pad_cell_width"],
            "removed_symbols": [],
            "changed_imports": [],
            "touched_subsystems": ["src/ctx"],
        },
    },
    {
        "case_id": "surface_05_public_http_route",
        "head_id": "operational_surface_exposure",
        "expected": "public_contract",
        "state": {
            "kind": "http_route",
            "name": "GET /mcp/context/{directory}",
            "file": "src/ctx/server.py",
            "detail": "FastAPI GET route returning directory CONTEXT.md",
        },
    },
]


def _brier_contribution(head: dict[str, Any], distribution: dict[str, float] | None, expected: Any) -> float | None:
    if not distribution:
        return None
    opts = valid_outputs(head)
    total = 0.0
    for opt in opts:
        key = _output_key(opt)
        prob = float(distribution.get(key, 0.0))
        target = 1.0 if opt == expected else 0.0
        total += (prob - target) ** 2
    return total / max(1, len(opts))


def evaluate_heads(
    root: Path | None = None,
    *,
    provider: str = "code",
    head_ids: list[str] | None = None,
    cases: list[dict[str, Any]] | None = None,
    allow_vault: bool = False,
    skip_pre_rule_for_jev: bool = False,
) -> dict[str, Any]:
    """Evaluate governed Jev heads against `GOLD_EVAL_CASES` (or custom cases)."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider {provider!r}; expected one of {PROVIDERS}")

    selected_cases = list(cases if cases is not None else GOLD_EVAL_CASES)
    if head_ids:
        wanted = set(head_ids)
        selected_cases = [c for c in selected_cases if c["head_id"] in wanted]

    case_results: list[dict[str, Any]] = []
    per_head_counts: dict[str, dict[str, Any]] = {}
    brier_scores: list[float] = []
    total_tokens = 0
    total_cost = 0.0
    latencies: list[float] = []
    pre_rule_hits = 0
    live_model_calls = 0

    for case in selected_cases:
        hid = case["head_id"]
        head = load_head(hid, root)
        check_state(head, case["state"])
        if provider == "code":
            res = run_code(head, case["state"])
        else:
            res = run_jev(
                [head],
                case["state"],
                root=root,
                allow_vault=allow_vault,
                skip_pre_rule=skip_pre_rule_for_jev,
            )[hid]

        abstained = bool(res["abstained"])
        conf_src = str(res.get("confidence_source") or "")
        if conf_src.startswith("pre_rule:"):
            pre_rule_hits += 1
        elif provider == "jev" and not abstained:
            live_model_calls += 1
        correct = (not abstained) and (res["output"] == case["expected"])
        brier = None if abstained else _brier_contribution(head, res["distribution"], case["expected"])
        if brier is not None:
            brier_scores.append(brier)
        total_tokens += int(res["input_tokens"])
        total_cost += float(res["cost_usd"])
        latencies.append(float(res["latency_ms"]))

        bucket = per_head_counts.setdefault(
            hid,
            {"total": 0, "evaluated": 0, "abstained": 0, "correct": 0, "brier_values": []},
        )
        bucket["total"] += 1
        if abstained:
            bucket["abstained"] += 1
        else:
            bucket["evaluated"] += 1
            if correct:
                bucket["correct"] += 1
            if brier is not None:
                bucket["brier_values"].append(brier)

        case_results.append(
            {
                "case_id": case["case_id"],
                "head_id": hid,
                "expected": case["expected"],
                "output": res["output"],
                "correct": correct,
                "abstained": abstained,
                "abstain_reason": res["abstain_reason"],
                "confidence": res["confidence"],
                "confidence_source": res["confidence_source"],
                "brier": round(brier, 6) if brier is not None else None,
                "input_tokens": res["input_tokens"],
                "cost_usd": res["cost_usd"],
                "latency_ms": res["latency_ms"],
                "model": res["model"],
            }
        )

    total = len(case_results)
    evaluated = sum(1 for r in case_results if not r["abstained"])
    abstained_total = total - evaluated
    correct_total = sum(1 for r in case_results if r["correct"])

    per_head_summary: dict[str, dict[str, Any]] = {}
    for hid, b in sorted(per_head_counts.items()):
        ev = b["evaluated"]
        bv = b["brier_values"]
        per_head_summary[hid] = {
            "total": b["total"],
            "evaluated": ev,
            "abstained": b["abstained"],
            "coverage": round(ev / b["total"], 4) if b["total"] else 0.0,
            "accuracy": round(b["correct"] / ev, 4) if ev else None,
            "brier_score": round(sum(bv) / len(bv), 6) if bv else None,
        }

    return {
        "provider": provider,
        "skip_pre_rule": skip_pre_rule_for_jev,
        "total": total,
        "evaluated": evaluated,
        "abstained": abstained_total,
        "pre_rule_hits": pre_rule_hits,
        "live_model_calls": live_model_calls,
        "coverage": round(evaluated / total, 4) if total else 0.0,
        "accuracy": round(correct_total / evaluated, 4) if evaluated else None,
        "brier_score": round(sum(brier_scores) / len(brier_scores), 6) if brier_scores else None,
        "total_input_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 9),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "per_head": per_head_summary,
        "cases": case_results,
    }
