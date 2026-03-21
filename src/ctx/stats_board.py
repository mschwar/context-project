"""Persistent run-stats ledger for ctx.

Per-repo: {cache_dir}/run_stats.json   (full run history)
Global:   ~/.ctx/run_stats.json        (aggregated totals only)
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _run_stats_path(root: Path, config) -> Path | None:
    cache_path = getattr(config, "cache_path", None)
    if cache_path == "":
        return None
    if cache_path:
        cache_dir = Path(cache_path).parent
    else:
        cache_dir = root / ".ctx-cache"
    return cache_dir / "run_stats.json"


def _global_stats_path() -> Path:
    global_dir = Path.home() / ".ctx"
    if platform.system() == "Windows":
        global_dir.mkdir(exist_ok=True)
    else:
        global_dir.mkdir(mode=0o700, exist_ok=True)
    return global_dir / "run_stats.json"


def _load_json_safe(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return default


def _save_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _build_run_record(result, config) -> dict:
    hits = result.cache_hits
    misses = result.cache_misses
    total = hits + misses
    if total > 0:
        tokens_saved = round((hits / total) * result.tokens_used)
    else:
        tokens_saved = 0
    from ctx.config import estimate_cost
    cost_saved_usd = estimate_cost(tokens_saved, config.provider, config.resolved_model())
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "dirs_processed": result.dirs_processed,
        "dirs_skipped": result.dirs_skipped,
        "files_processed": result.files_processed,
        "tokens_used": result.tokens_used,
        "tokens_saved": tokens_saved,
        "est_cost_usd": result.est_cost_usd,
        "cost_saved_usd": cost_saved_usd,
        "cache_hits": hits,
        "cache_misses": misses,
        "strategy": result.strategy,
        "errors": len(result.errors),
        "budget_exhausted": result.budget_exhausted,
        "provider": config.provider,
        "model": config.resolved_model(),
    }


def _update_global(global_path: Path, repo_key: str, record: dict) -> None:
    existing = _load_json_safe(global_path, {"schema_version": 1, "repos": {}, "totals": {}})
    repos = existing.get("repos", {})
    if not isinstance(repos, dict):
        repos = {}

    repo = repos.get(repo_key, {})
    repo["last_run"] = record["ts"]
    repo["run_count"] = repo.get("run_count", 0) + 1
    repo["total_dirs_processed"] = repo.get("total_dirs_processed", 0) + record["dirs_processed"]
    repo["total_tokens_used"] = repo.get("total_tokens_used", 0) + record["tokens_used"]
    repo["total_tokens_saved"] = repo.get("total_tokens_saved", 0) + record["tokens_saved"]
    repo["total_cost_usd"] = round(repo.get("total_cost_usd", 0.0) + record["est_cost_usd"], 6)
    repo["total_cost_saved_usd"] = round(repo.get("total_cost_saved_usd", 0.0) + record["cost_saved_usd"], 6)
    repos[repo_key] = repo

    total_runs = sum(r.get("run_count", 0) for r in repos.values())
    totals = {
        "repos_touched": len(repos),
        "total_runs": total_runs,
        "total_dirs_processed": sum(r.get("total_dirs_processed", 0) for r in repos.values()),
        "total_tokens_used": sum(r.get("total_tokens_used", 0) for r in repos.values()),
        "total_tokens_saved": sum(r.get("total_tokens_saved", 0) for r in repos.values()),
        "total_cost_usd": round(sum(r.get("total_cost_usd", 0.0) for r in repos.values()), 6),
        "total_cost_saved_usd": round(sum(r.get("total_cost_saved_usd", 0.0) for r in repos.values()), 6),
    }

    _save_json_atomic(global_path, {"schema_version": 1, "repos": repos, "totals": totals})


def record_run(root: Path, result, config) -> None:
    try:
        record = _build_run_record(result, config)
        repo_key = str(root.resolve())

        per_repo_path = _run_stats_path(root, config)
        if per_repo_path is not None:
            existing = _load_json_safe(per_repo_path, {"schema_version": 1, "runs": []})
            runs = existing.get("runs", [])
            if not isinstance(runs, list):
                runs = []
            runs.append(record)
            _save_json_atomic(per_repo_path, {"schema_version": 1, "runs": runs})

        global_path = _global_stats_path()
        _update_global(global_path, repo_key, record)
    except Exception:
        pass


def read_board(root: Path, config) -> dict:
    per_repo_path = _run_stats_path(root, config)
    if per_repo_path is None:
        runs = []
    else:
        data = _load_json_safe(per_repo_path, {"schema_version": 1, "runs": []})
        runs = data.get("runs", [])
        if not isinstance(runs, list):
            runs = []

    run_count = len(runs)
    total_dirs = sum(r.get("dirs_processed", 0) for r in runs)
    total_tokens = sum(r.get("tokens_used", 0) for r in runs)
    total_tokens_saved = sum(r.get("tokens_saved", 0) for r in runs)
    total_cost = sum(r.get("est_cost_usd", 0.0) for r in runs)
    total_cost_saved = sum(r.get("cost_saved_usd", 0.0) for r in runs)
    total_hits = sum(r.get("cache_hits", 0) for r in runs)
    total_misses = sum(r.get("cache_misses", 0) for r in runs)
    hit_denom = total_hits + total_misses
    cache_hit_rate = round(total_hits / hit_denom, 4) if hit_denom > 0 else 0.0

    recent_runs = runs[-5:] if runs else []
    recent_runs = list(reversed(recent_runs))

    return {
        "schema_version": 1,
        "repo": str(root.resolve()),
        "aggregate": {
            "run_count": run_count,
            "total_dirs_processed": total_dirs,
            "total_tokens_used": total_tokens,
            "total_tokens_saved": total_tokens_saved,
            "total_cost_usd": round(total_cost, 6),
            "total_cost_saved_usd": round(total_cost_saved, 6),
            "cache_hit_rate": cache_hit_rate,
        },
        "recent_runs": recent_runs,
    }


def read_global_board(global_path: Path | None = None) -> dict:
    if global_path is None:
        global_path = _global_stats_path()
    data = _load_json_safe(global_path, {"schema_version": 1, "repos": {}, "totals": {}})
    return data
