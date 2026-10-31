"""Regression tests for foreign-model QA hardening across concurrency, worktrees, pricing, and skeleton extraction."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import ctx.api as api_module
from ctx.config import Config, load_config
from ctx.generator import (
    _estimate_tokens,
    _truncate_to_tokens,
    generate_tree,
)
from ctx.ignore import load_ignore_patterns, should_ignore
from ctx.init import (
    CTX_DIR,
    CTX_HOOK_START,
    HOOK_NAMES,
    PID_FILE,
    _acquire_pid,
    init_project,
    uninit_project,
)
from ctx.llm import CachingLLMClient, FileSummary, LLMResult, SubdirSummary
from ctx.lock import STALE_TIMEOUT_SECONDS, CtxLock, LockHeldError
from ctx.manifest import read_manifest
from ctx.preflight import run_preflight
from ctx.sdk import CtxProject
from ctx.skeleton import extract_skeleton
from ctx.stats_board import _build_run_record


class _SimpleFakeClient:
    model = "fake-qa-model"

    def __init__(self, *, in_tok: int = 10, out_tok: int = 5, prompt_templates: dict | None = None) -> None:
        self._in_tok = in_tok
        self._out_tok = out_tok
        self.prompt_templates = prompt_templates or {}
        self.dir_calls = 0

    def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
        return [
            LLMResult(
                text=f"Summary of {f['name']}.",
                input_tokens=self._in_tok,
                output_tokens=self._out_tok,
            )
            for f in files
        ]

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        self.dir_calls += 1
        tag = self.prompt_templates.get("directory_summary", "default")[:16]
        return LLMResult(
            text=f"# {dir_path.name}\n\nPurpose ({tag}) #{self.dir_calls}.\n",
            input_tokens=self._in_tok,
            output_tokens=self._out_tok,
        )


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "qa@test.local"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "QA"], capture_output=True, check=True)
    (path / "app.py").write_text("def main() -> int:\n    return 0\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "chore: initial"], capture_output=True, check=True)
    return path


def test_ctx_lock_exclusive_acquisition_and_initializing_grace(tmp_path: Path) -> None:
    """Concurrent CtxLock contenders (fresh and stale-reclaim) allow at most one owner."""
    barrier = threading.Barrier(6)
    winners: list[int] = []
    failures: list[Exception] = []
    guard = threading.Lock()

    def _contend(idx: int) -> None:
        lock = CtxLock(tmp_path, command=f"worker-{idx}")
        barrier.wait()
        try:
            lock.acquire()
            with guard:
                winners.append(idx)
            time.sleep(0.08)
            lock.release()
        except LockHeldError as exc:
            with guard:
                failures.append(exc)

    threads = [threading.Thread(target=_contend, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1
    assert len(failures) == 5

    # Newly created empty lock file (< grace window) must NOT be unlinked as corrupt
    lock_file = tmp_path / ".ctx-cache" / "lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("", encoding="utf-8")
    with pytest.raises(LockHeldError):
        CtxLock(tmp_path, command="racer").acquire()
    assert lock_file.exists()
    lock_file.unlink()

    # Concurrent stale-lock reclamation also admits at most one winner
    lock_file.write_text(
        f"pid={os.getpid()}\ntimestamp={time.time() - STALE_TIMEOUT_SECONDS - 50}\ncommand=old\n",
        encoding="utf-8",
    )
    winners.clear()
    failures.clear()
    barrier2 = threading.Barrier(4)

    def _reclaim(idx: int) -> None:
        lock = CtxLock(tmp_path, command=f"reclaim-{idx}")
        barrier2.wait()
        try:
            lock.acquire()
            with guard:
                winners.append(idx)
            time.sleep(0.08)
            lock.release()
        except LockHeldError as exc:
            with guard:
                failures.append(exc)

    threads2 = [threading.Thread(target=_reclaim, args=(i,)) for i in range(4)]
    for t in threads2:
        t.start()
    for t in threads2:
        t.join()

    assert len(winners) == 1
    assert len(failures) == 3


def test_ctx_lock_multiprocess_exclusivity(tmp_path: Path) -> None:
    """Two separate OS processes racing on CtxLock must never both enter the critical section."""
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONPATH=src_dir)
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from ctx.lock import CtxLock, LockHeldError\n"
        "root = Path(sys.argv[1])\n"
        "ready = Path(sys.argv[2])\n"
        "go = Path(sys.argv[3])\n"
        "ready.write_text('1')\n"
        "while not go.exists():\n"
        "    time.sleep(0.005)\n"
        "try:\n"
        "    with CtxLock(root, command='mp'):\n"
        "        print('ACQUIRED')\n"
        "        time.sleep(0.15)\n"
        "except LockHeldError:\n"
        "    print('HELD')\n"
    )
    go_flag = tmp_path / "go"
    procs = []
    for idx in range(3):
        ready_flag = tmp_path / f"ready-{idx}"
        procs.append(
            (
                ready_flag,
                subprocess.Popen(
                    [sys.executable, "-c", script, str(tmp_path / "repo"), str(ready_flag), str(go_flag)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                ),
            )
        )
    deadline = time.time() + 5.0
    while any(not r.exists() for r, _ in procs) and time.time() < deadline:
        time.sleep(0.01)
    go_flag.write_text("1", encoding="utf-8")

    outputs = [p.communicate(timeout=10)[0].strip() for _, p in procs]
    assert outputs.count("ACQUIRED") == 1
    assert outputs.count("HELD") == 2


def test_hook_acquire_pid_protects_initializing_empty_file_and_concurrent_reclaim(tmp_path: Path) -> None:
    """An empty newly created .ctx/hook.pid must not be unlinked by a racing hook process."""
    pid_path = tmp_path / PID_FILE
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("", encoding="utf-8")

    # Freshly created empty PID file (< 2s) is treated as initializing/held
    assert _acquire_pid(tmp_path) is False
    assert pid_path.exists()

    # Backdate mtime past grace window to simulate an abandoned corrupt PID file
    old_ts = time.time() - 10.0
    os.utime(pid_path, (old_ts, old_ts))

    barrier = threading.Barrier(4)
    results: list[bool] = []
    guard = threading.Lock()

    def _claim() -> None:
        barrier.wait()
        ok = _acquire_pid(tmp_path)
        with guard:
            results.append(ok)

    threads = [threading.Thread(target=_claim) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == 3


def test_shared_default_worktree_hooks_refresh_active_checkout_and_preserve_on_uninit(tmp_path: Path) -> None:
    """Default git worktrees share .git/hooks; each checkout must refresh itself and uninit safely."""
    repo_a = _init_git_repo(tmp_path / "repo_a")
    repo_b = tmp_path / "repo_b"
    subprocess.run(
        ["git", "-C", str(repo_a), "worktree", "add", "-b", "feature-b", str(repo_b)],
        capture_output=True,
        check=True,
    )

    init_project(repo_a, tier2=True)
    init_project(repo_b, tier2=True)

    shared_hook = repo_a / ".git" / "hooks" / "post-commit"
    assert shared_hook.is_file()
    hook_body = shared_hook.read_text(encoding="utf-8")
    assert 'git rev-parse --show-toplevel' in hook_body
    # Neither checkout's hardcoded path should hijack the shared hook
    assert f'--root "{repo_b.as_posix()}"' not in hook_body

    # Mutate repo_a only and invoke run_hook via the shell block's dynamic root resolution
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    (repo_a / "app.py").write_text("def main() -> int:\n    return 0\n\ndef only_in_a() -> None:\n    pass\n", encoding="utf-8")
    b_before = (repo_b / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8")

    sync_cmd = hook_body.replace("&", "").strip()
    subprocess.run(
        ["sh", "-c", sync_cmd],
        cwd=str(repo_a),
        env=dict(os.environ, PYTHONPATH=src_dir),
        capture_output=True,
        check=True,
    )
    assert "only_in_a" in (repo_a / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8")
    assert (repo_b / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8") == b_before

    # Uninitializing repo_b must NOT delete the shared hook while repo_a is still initialized
    uninit_b = uninit_project(repo_b)
    assert not (repo_b / CTX_DIR).exists()
    assert uninit_b["hooks_removed"] == []
    assert CTX_HOOK_START in shared_hook.read_text(encoding="utf-8")

    # Uninitializing the last remaining initialized worktree removes the shared hook
    uninit_a = uninit_project(repo_a)
    assert set(uninit_a["hooks_removed"]) == set(HOOK_NAMES)
    assert not shared_hook.exists()


def test_subtree_refresh_and_verify_preserve_repo_relative_headings(tmp_path: Path) -> None:
    """Subtree generation and verification must use the canonical project root anchor for headings."""
    repo = _init_git_repo(tmp_path / "repo")
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text("def helper() -> int:\n    return 1\n", encoding="utf-8")

    client = _SimpleFakeClient()
    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")

    # 1. Subtree-first generation (before root CONTEXT.md even exists!) in a git repo
    spec_src = load_ignore_patterns(repo / "src")
    generate_tree(repo / "src", cfg, client, spec_src)
    src_manifest = read_manifest(repo / "src")
    pkg_manifest = read_manifest(pkg)
    assert src_manifest is not None and src_manifest.body.startswith("# src\n")
    assert pkg_manifest is not None and pkg_manifest.body.startswith("# src/pkg\n")

    # 2. Full tree generation + subtree `api.check(repo / "src", verify=True)`
    spec_root = load_ignore_patterns(repo)
    generate_tree(repo, cfg, client, spec_root)
    sub_check = api_module.check(repo / "src", verify=True)
    assert sub_check.summary["invalid"] == 0
    assert sub_check.summary["invalid_body"] == 0

    root_check = api_module.check(repo, verify=True)
    assert root_check.summary["invalid"] == 0

    # 3. Non-git directory tree: subtree verify and subtree regeneration still anchor to root CONTEXT.md
    non_git = tmp_path / "extracted_archive"
    (non_git / "lib").mkdir(parents=True)
    (non_git / "readme.txt").write_text("root info\n", encoding="utf-8")
    (non_git / "lib" / "util.py").write_text("X = 1\n", encoding="utf-8")
    generate_tree(non_git, cfg, client, load_ignore_patterns(non_git))
    assert api_module.check(non_git / "lib", verify=True).summary["invalid"] == 0
    generate_tree(non_git / "lib", cfg, client, load_ignore_patterns(non_git / "lib"))
    assert api_module.check(non_git, verify=True).summary["invalid"] == 0


def test_tier2_refresh_rejects_setup_and_watch_and_init_force_transitions_modes(tmp_path: Path) -> None:
    """Tier 2 refresh must reject --setup/--watch explicitly, and `ctx init --force` must transition to Tier 1."""
    repo = _init_git_repo(tmp_path / "repo")
    init_project(repo, tier2=True)

    with pytest.raises(ValueError, match="--setup is not supported in Tier 2"):
        api_module.refresh(repo, setup=True)
    with pytest.raises(ValueError, match="--watch is not supported in Tier 2"):
        api_module.refresh(repo, watch=True)
    assert not (repo / "CONTEXT.md").exists()

    # Transition from Tier 2 -> Tier 1 via `init_project(repo, force=True)`
    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")
    client = _SimpleFakeClient()
    with patch("ctx.api._build_generation_runtime", return_value=(cfg, load_ignore_patterns(repo), client)):
        res = init_project(repo, force=True, tier2=False)

    assert "mode" not in res
    assert (repo / "CONTEXT.md").is_file()
    meta = json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "standard"
    assert CtxProject.load(repo, walk_parents=False).is_stale() is False


def test_base_url_only_infers_provider_in_load_config_and_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting only CTX_BASE_URL or .ctxconfig base_url must infer provider without requiring ANTHROPIC_API_KEY."""
    monkeypatch.setenv("CTX_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ambient-should-not-hijack")

    cfg = load_config(tmp_path)
    assert cfg.provider == "ollama"
    assert cfg.base_url == "http://127.0.0.1:11434/v1"

    with (
        patch("ctx.preflight._probe_local_models", return_value=(True, None)),
        patch("ctx.preflight.probe_model_quality", return_value=(True, None)),
    ):
        pf = run_preflight(str(tmp_path))
    assert pf.ready is True
    assert pf.provider == "ollama"

    # Also test .ctxconfig containing only base_url (no provider field, no API keys)
    monkeypatch.delenv("CTX_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".ctxconfig").write_text("base_url: http://localhost:1234/v1\n", encoding="utf-8")

    cfg2 = load_config(tmp_path)
    assert cfg2.provider == "lmstudio"
    with (
        patch("ctx.preflight._probe_local_models", return_value=(True, None)),
        patch("ctx.preflight.probe_model_quality", return_value=(True, None)),
    ):
        pf2 = run_preflight(str(tmp_path))
    assert pf2.ready is True
    assert pf2.provider == "lmstudio"


def test_split_input_output_pricing_connected_to_refresh_and_guardrail(tmp_path: Path) -> None:
    """Refresh cost accounting and USD guardrails must apply split input/output rates."""
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    cfg = Config(
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-test",
        cache_path="",
        max_usd_per_run=0.00070,
    )

    class _ExactUsageClient:
        model = "gpt-4o-mini"

        def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
            return [LLMResult(text="Module summary.", input_tokens=600, output_tokens=400)]

        def summarize_directory(self, dir_path: Path, file_summaries: list, subdir_summaries: list) -> LLMResult:
            return LLMResult(text="# .\n\nRoot purpose.\n", input_tokens=400, output_tokens=600)

    # 1,000 input * $0.15/1M + 1,000 output * $0.60/1M = $0.00015 + $0.00060 = $0.00075
    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(tmp_path), _ExactUsageClient()),
    ):
        result = api_module.refresh(tmp_path, force=True)

    assert result.input_tokens == 1000
    assert result.output_tokens == 1000
    assert result.est_cost_usd == pytest.approx(0.00075)
    assert result.budget_exhausted is True
    assert result.budget_guardrail is not None
    assert "$0.0008" in result.budget_guardrail or "$0.0007" in result.budget_guardrail


def test_caching_llm_client_exact_per_file_savings_concurrent_futures_and_prompt_keys(tmp_path: Path) -> None:
    """Cached token savings must be exact per file, resolve across in-flight Futures, and key on custom prompts."""

    class _VariableCostClient:
        model = "gpt-4o-mini"

        def __init__(self, prompt_templates: dict | None = None, delay: float = 0.0) -> None:
            self.prompt_templates = prompt_templates or {}
            self._delay = delay
            self.dir_calls = 0

        def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
            if self._delay:
                time.sleep(self._delay)
            out: list[LLMResult] = []
            for f in files:
                if f["name"] == "small.py":
                    out.append(LLMResult(text="Small file.", input_tokens=80, output_tokens=20))
                else:
                    out.append(LLMResult(text="Huge file.", input_tokens=700, output_tokens=200))
            return out

        def summarize_directory(self, dir_path: Path, file_summaries: list, subdir_summaries: list) -> LLMResult:
            self.dir_calls += 1
            tag = self.prompt_templates.get("directory_summary", "default")[:8]
            return LLMResult(text=f"# d\n\nDir {tag} v{self.dir_calls}.\n", input_tokens=50, output_tokens=25)

    cache_file = tmp_path / "cache.json"
    f_small = {"name": "small.py", "content": "x=1", "language": "Python", "metadata": {}}
    f_huge = {"name": "huge.py", "content": "y=2" * 200, "language": "Python", "metadata": {}}

    c1 = CachingLLMClient(_VariableCostClient(), cache_path=cache_file)
    c1.summarize_files(tmp_path, [f_small, f_huge])

    # Reload from disk and reuse ONLY small.py: must report 100 saved (80 in + 20 out), NOT 500!
    c2 = CachingLLMClient(_VariableCostClient(), cache_path=cache_file)
    c2.summarize_files(tmp_path, [f_small])
    assert c2.tokens_saved == 100
    assert c2.input_tokens_saved == 80
    assert c2.output_tokens_saved == 20

    # Stats board uses exact split input/output saved tokens for cost_saved_usd
    cfg = Config(provider="openai", model="gpt-4o-mini", api_key="sk-test")
    rr = api_module.RefreshResult(
        dirs_processed=1,
        dirs_skipped=0,
        files_processed=1,
        tokens_used=0,
        errors=[],
        budget_exhausted=False,
        strategy="incremental",
        est_cost_usd=0.0,
        stale_directories=[],
        cache_hits=1,
        cache_misses=0,
        tokens_saved=100,
        input_tokens_saved=80,
        output_tokens_saved=20,
    )
    rec = _build_run_record(rr, cfg)
    assert rec["cost_saved_usd"] == pytest.approx((80 * 0.15 + 20 * 0.60) / 1_000_000)

    # Concurrent in-flight Future hit must wait for resolution and record exact tokens_saved (100, not 0)
    c_concurrent = CachingLLMClient(_VariableCostClient(delay=0.06))
    b = threading.Barrier(2)

    def _call_same_file() -> None:
        b.wait()
        c_concurrent.summarize_files(tmp_path, [f_small])

    t1 = threading.Thread(target=_call_same_file)
    t2 = threading.Thread(target=_call_same_file)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert c_concurrent.cache_misses == 1
    assert c_concurrent.cache_hits == 1
    assert c_concurrent.tokens_saved == 100

    # Changing custom directory_summary prompt must invalidate directory cache
    fs = [FileSummary(name="small.py", summary="Small file.")]
    inner_a = _VariableCostClient(prompt_templates={"directory_summary": "Custom A {json_payload}"})
    inner_b = _VariableCostClient(prompt_templates={"directory_summary": "Custom B {json_payload}"})
    dir_cache = tmp_path / "dir_cache.json"
    ca = CachingLLMClient(inner_a, cache_path=dir_cache)
    res_a = ca.summarize_directory(tmp_path, fs, [], content_hash="sha256:same")
    cb = CachingLLMClient(inner_b, cache_path=dir_cache)
    res_b = cb.summarize_directory(tmp_path, fs, [], content_hash="sha256:same")
    assert inner_a.dir_calls == 1
    assert inner_b.dir_calls == 1
    assert res_a.text != res_b.text


def test_skeleton_module_prefixes_hash_import_classifications_and_extensions(tmp_path: Path) -> None:
    """Verify tsconfig aliases, Ruby require_relative, Kotlin kotlinx, C#/PHP variants, prefix hash, and extensions."""
    (tmp_path / "go.mod").write_text("module github.com/acme/alpha\n\ngo 1.22\n", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text(
        '// JSONC tsconfig with comments\n{\n  "compilerOptions": {\n    "paths": {\n      "@app/*": ["src/*"],\n    }\n  }\n}\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo\n\nOverview doc.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n[project.scripts]\ndemo='demo:main'\n", encoding="utf-8")

    src = tmp_path / "src"
    src.mkdir()
    (src / "main.go").write_text(
        'package main\nimport (\n  "fmt"\n  "github.com/acme/alpha/internal/db"\n  "github.com/spf13/cobra"\n)\nfunc main() {}\n',
        encoding="utf-8",
    )
    (src / "web.ts").write_text(
        'import { svc } from "@app/services/auth";\nimport { Injectable } from "@nestjs/common";\nexport function boot() {}\n',
        encoding="utf-8",
    )
    (src / "worker.rb").write_text(
        "require 'sidekiq'\nrequire_relative 'jobs/cleanup'\nclass Worker\nend\n",
        encoding="utf-8",
    )
    (src / "Flow.kt").write_text(
        "import kotlin.collections.List\nimport kotlinx.coroutines.launch\nclass FlowRunner\n",
        encoding="utf-8",
    )
    (src / "Program.cs").write_text(
        "global using Microsoft.Extensions.Logging;\nnamespace Demo {\n    using System.Text;\n    using Newtonsoft.Json;\n    public class Program {}\n}\n",
        encoding="utf-8",
    )
    (src / "Handler.php").write_text(
        "<?php\nuse Vendor\\Pkg\\Service as SvcAlias;\nuse Symfony\\Component\\{HttpFoundation\\Request, Console\\Command as Cmd};\nclass Handler {}\n",
        encoding="utf-8",
    )
    (src / "core.py").write_text("def run_core() -> None:\n    pass\n", encoding="utf-8")

    sk1 = extract_skeleton(tmp_path)
    sub = next(s for s in sk1.subsystems if s.path == "src")

    # Internal vs external classifications
    assert "github.com/acme/alpha/internal/db" in sub.internal_deps
    assert "@app/services/auth" in sub.internal_deps
    assert "./jobs/cleanup" in sub.internal_deps
    assert "workers" not in sub.external_deps and "jobs" not in sub.external_deps
    assert "github.com/spf13/cobra" in sub.external_deps
    assert "@nestjs/common" in sub.external_deps
    assert "sidekiq" in sub.external_deps
    assert "kotlinx" in sub.external_deps
    assert "kotlin" not in sub.external_deps
    assert "Microsoft" in sub.external_deps
    assert "Newtonsoft" in sub.external_deps
    assert "System" not in sub.external_deps
    assert "Vendor" in sub.external_deps
    assert "Symfony" in sub.external_deps

    # Changing go.mod module path MUST invalidate structural_hash
    (tmp_path / "go.mod").write_text("module github.com/acme/beta\n\ngo 1.22\n", encoding="utf-8")
    sk2 = extract_skeleton(tmp_path)
    assert sk2.structural_hash != sk1.structural_hash

    # Strict extensions=[".py"] filtering excludes README.md, non-.py files, and pyproject.toml cli entrypoints
    sk_py = extract_skeleton(tmp_path, extensions=[".py"])
    assert [f.relative_path for f in sk_py.files] == ["src/core.py"]
    assert sk_py.boundary_docs == []
    assert sk_py.entrypoints == []


def test_tiktoken_handles_literal_special_tokens_without_crashing(tmp_path: Path) -> None:
    """Source files containing literal <|endoftext|> or <|fim_prefix|> tokens must never crash."""
    sample = "prefix = '<|endoftext|>'\n" + ("x = 1\n" * 100) + "suffix = '<|fim_prefix|>'\n"
    assert _estimate_tokens(sample) > 10
    truncated, count = _truncate_to_tokens(sample, 25)
    assert 0 < count <= 25
    assert "<|endoftext|>" in truncated

    (tmp_path / "special.py").write_text(sample, encoding="utf-8")
    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", max_file_tokens=25, cache_path="")
    stats = generate_tree(tmp_path, cfg, _SimpleFakeClient(), load_ignore_patterns(tmp_path))
    assert stats.errors == []
    assert stats.files_processed == 1


def test_nested_and_ancestor_gitignore_sdk_staleness_and_capsule_depth_zero(tmp_path: Path) -> None:
    """Verify nested/ancestor .gitignore rules, full-tier SDK export staleness, and depth=0 capsule filtering."""
    repo = _init_git_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("*.secret\n/src/generated/\nkeep_me.secret\n", encoding="utf-8")
    (repo / ".ctxignore").write_text("!keep_me.secret\n", encoding="utf-8")
    (repo / "src" / "generated").mkdir(parents=True)
    (repo / "src" / "sub").mkdir(parents=True)
    (repo / "src" / "sub" / ".gitignore").write_text("nested_only.tmpdata\n", encoding="utf-8")

    # 1. Root spec honors nested .gitignore
    root_spec = load_ignore_patterns(repo)
    nested_secret = repo / "src" / "sub" / "nested_only.tmpdata"
    nested_secret.write_text("x", encoding="utf-8")
    other_file = repo / "src" / "nested_only.tmpdata"
    other_file.write_text("x", encoding="utf-8")
    assert should_ignore(nested_secret, root_spec, repo) is True
    assert should_ignore(other_file, root_spec, repo) is False

    # 2. Subtree spec (repo / "src") inherits ancestor .gitignore and .ctxignore negation
    sub_spec = load_ignore_patterns(repo / "src")
    (repo / "src" / " hidden.secret").write_text("x", encoding="utf-8")
    (repo / "src" / "keep_me.secret").write_text("x", encoding="utf-8")
    assert should_ignore(repo / "src" / "generated", sub_spec, repo / "src") is True
    assert should_ignore(repo / "src" / " hidden.secret", sub_spec, repo / "src") is True
    assert should_ignore(repo / "src" / "keep_me.secret", sub_spec, repo / "src") is False

    # Clean temporary test files before SDK/capsule checks
    for p in (nested_secret, other_file, repo / "src" / " hidden.secret", repo / "src" / "keep_me.secret"):
        p.unlink()

    # 3. Tier 1 SDK is_stale() detects stale/corrupted full .ctx/CONTEXT.md even when CONTEXT-0.md is fresh
    (repo / "src" / "cli.py").write_text("def cli_entry() -> None:\n    pass\n", encoding="utf-8")
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "adr" / "001-choice.md").write_text("# ADR 1\n\nDecision.\n", encoding="utf-8")
    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")
    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(repo), _SimpleFakeClient()),
    ):
        init_project(repo, force=True, tier2=False)

    proj = CtxProject.load(repo, walk_parents=False)
    assert proj.is_stale() is False

    # Corrupt full .ctx/CONTEXT.md without touching leaf source hashes or CONTEXT-0.md
    (repo / CTX_DIR / "CONTEXT.md").write_text("# outdated export\n", encoding="utf-8")
    assert proj.is_stale() is True

    # 4. Capsule depth=0 excludes deep entrypoints and deep ADRs
    (repo / "AGENTS.md").write_text("# AGENTS\n\nRoot governance.\n", encoding="utf-8")
    cap0 = api_module.build_fleet_capsule(repo, depth=0)
    assert all(b["path"] == "AGENTS.md" for b in cap0.authority_boundaries)
    assert "file:src/cli.py" not in cap0.entrypoints
    assert "001-choice.md" not in cap0.capsule_markdown
