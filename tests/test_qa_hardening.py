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
    HOOK_GUARD_FILE,
    HOOK_NAMES,
    PID_FILE,
    _acquire_pid,
    _release_pid,
    init_project,
    uninit_project,
)
from ctx.llm import CachingLLMClient, DEFAULT_PROMPT_TEMPLATES, FileSummary, LLMResult, SubdirSummary
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

    # Persistent kernel guard inode must exist and remain stable across stale reclamation
    guard_file = tmp_path / ".ctx-cache" / ".lock.guard"
    assert guard_file.is_file()
    guard_inode_before = guard_file.stat().st_ino

    # Concurrent stale-lock reclamation also admits at most one winner without replacing guard inode
    lock_file = tmp_path / ".ctx-cache" / "lock"
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
            # Payload on disk must always be complete and parseable while held
            assert lock._read_lock() is not None
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
    assert guard_file.stat().st_ino == guard_inode_before


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


def test_hook_acquire_pid_kernel_lock_exclusivity_across_threads_and_processes(tmp_path: Path) -> None:
    """Concurrent hook contenders (threads and subprocesses) must lock persistent .ctx/.hook.guard exclusively."""
    pid_path = tmp_path / PID_FILE
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    # Pre-seed a corrupt/stale PID file to exercise reclamation under contention
    pid_path.write_text("not-a-pid", encoding="utf-8")

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
    guard_path = tmp_path / HOOK_GUARD_FILE
    assert guard_path.is_file()
    guard_inode = guard_path.stat().st_ino
    assert int(pid_path.read_text(encoding="utf-8").strip()) == os.getpid()
    _release_pid(tmp_path)
    assert not pid_path.exists()
    assert guard_path.stat().st_ino == guard_inode

    # Multi-process race over a stale PID file must also admit exactly 1 winner
    pid_path.write_text("99999999", encoding="utf-8")
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONPATH=src_dir)
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from ctx.init import _acquire_pid, _release_pid\n"
        "root, ready, go = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])\n"
        "ready.write_text('1')\n"
        "while not go.exists():\n"
        "    time.sleep(0.005)\n"
        "if _acquire_pid(root):\n"
        "    print('WON')\n"
        "    time.sleep(0.15)\n"
        "    _release_pid(root)\n"
        "else:\n"
        "    print('SKIPPED')\n"
    )
    go_flag = tmp_path / "hook_go"
    procs = []
    for idx in range(3):
        ready_flag = tmp_path / f"hook_ready_{idx}"
        procs.append(
            (
                ready_flag,
                subprocess.Popen(
                    [sys.executable, "-c", script, str(tmp_path), str(ready_flag), str(go_flag)],
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
    assert outputs.count("WON") == 1
    assert outputs.count("SKIPPED") == 2
    assert guard_path.stat().st_ino == guard_inode


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


def test_transactional_tier2_to_tier1_transition_preserves_tier2_on_failure(tmp_path: Path) -> None:
    """Failed `ctx init --force` on a Tier 2 repo must preserve working Tier 2 mode and exports."""
    repo = _init_git_repo(tmp_path / "repo")
    sub = repo / "src"
    sub.mkdir()
    (sub / "service.py").write_text("def serve() -> int:\n    return 200\n", encoding="utf-8")
    init_project(repo, tier2=True)

    meta_before = json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))
    c0_before = (repo / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8")
    assert meta_before["mode"] == "tier2"

    # 1. Runtime/provider failure before generation must not touch metadata.json or exports
    with patch("ctx.api._build_generation_runtime", side_effect=RuntimeError("provider unreachable")):
        with pytest.raises(RuntimeError, match="provider unreachable"):
            init_project(repo, force=True, tier2=False)

    meta_after_conn_fail = json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))
    assert meta_after_conn_fail["mode"] == "tier2"
    assert (repo / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8") == c0_before
    assert not (repo / "CONTEXT.md").exists()
    assert CtxProject.load(repo, walk_parents=False).is_stale() is False

    # 2. Partial generation failure (leaf succeeds, root fails) must roll back leaf CONTEXT.md and keep Tier 2
    class _FailingRootClient(_SimpleFakeClient):
        def summarize_directory(self, dir_path: Path, file_summaries: list, subdir_summaries: list) -> LLMResult:
            if dir_path.resolve() == repo.resolve():
                raise RuntimeError("root LLM summarization failed")
            return super().summarize_directory(dir_path, file_summaries, subdir_summaries)

    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")
    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(repo), _FailingRootClient()),
    ):
        with pytest.raises(RuntimeError, match="root LLM summarization failed"):
            init_project(repo, force=True, tier2=False)

    meta_after_gen_fail = json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))
    assert meta_after_gen_fail["mode"] == "tier2"
    assert (repo / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8") == c0_before
    assert not (repo / "CONTEXT.md").exists()
    assert not (sub / "CONTEXT.md").exists()
    assert CtxProject.load(repo, walk_parents=False).is_stale() is False


def test_preflight_merges_conflicting_ctx_base_url_over_ctxconfig_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CTX_BASE_URL pointing to Ollama must override a cloud-proxy base_url in .ctxconfig."""
    (tmp_path / ".ctxconfig").write_text(
        "base_url: https://cloud-proxy.example.com/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CTX_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

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


def test_subtree_ignore_honors_wildcard_root_gitignore_and_tier2_subtree_dispatch(
    tmp_path: Path,
) -> None:
    """Wildcard root rules (/src/*/private.txt) must hold on src/pkg, and Tier 2 subtree refresh must stay Tier 2."""
    repo = _init_git_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("/src/*/private.txt\n/src/**/generated/*.py\n", encoding="utf-8")
    (repo / ".ctxignore").write_text("!/src/*/keep_private.txt\n", encoding="utf-8")
    pkg = repo / "src" / "pkg"
    (pkg / "generated").mkdir(parents=True)
    (pkg / "private.txt").write_text("top secret\n", encoding="utf-8")
    (pkg / "keep_private.txt").write_text("allowed\n", encoding="utf-8")
    (pkg / "generated" / "auto.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "public.py").write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")

    pkg_spec = load_ignore_patterns(pkg)
    assert should_ignore(pkg / "private.txt", pkg_spec, pkg) is True
    assert should_ignore(pkg / "generated" / "auto.py", pkg_spec, pkg) is True
    assert should_ignore(pkg / "keep_private.txt", pkg_spec, pkg) is False
    assert should_ignore(pkg / "public.py", pkg_spec, pkg) is False

    # Tier 2 repository: running refresh/check/export on `repo / "src"` must dispatch Tier 2 at `repo`
    init_project(repo, tier2=True)
    (pkg / "public.py").write_text(
        "def ok() -> int:\n    return 1\n\ndef added_via_subtree_refresh() -> None:\n    pass\n",
        encoding="utf-8",
    )
    sub_refresh = api_module.refresh(repo / "src")
    assert sub_refresh.strategy == "tier2"
    assert not (repo / "src" / "CONTEXT.md").exists()
    assert not (pkg / "CONTEXT.md").exists()
    assert "added_via_subtree_refresh" in (repo / CTX_DIR / "CONTEXT-0.md").read_text(encoding="utf-8")

    sub_check = api_module.check(repo / "src", verify=True)
    assert sub_check.summary.get("tier2") is True
    assert sub_check.summary["invalid"] == 0

    sub_export = api_module.export_context(repo / "src", depth=0)
    assert "added_via_subtree_refresh" in sub_export.content


def test_repo_named_test_work_anchors_headings_consistently(tmp_path: Path) -> None:
    """A real repository named `test-work` must anchor identically for root and subtree commands."""
    repo = _init_git_repo(tmp_path / "test-work")
    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "worker.py").write_text("def work() -> None:\n    pass\n", encoding="utf-8")

    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")
    client = _SimpleFakeClient()
    generate_tree(repo, cfg, client, load_ignore_patterns(repo))

    src_manifest = read_manifest(src_dir)
    assert src_manifest is not None and src_manifest.body.startswith("# src\n")
    assert api_module.check(src_dir, verify=True).summary["invalid"] == 0
    assert api_module.check(repo, verify=True).summary["invalid"] == 0


def test_exact_batch_token_accounting_and_default_prompt_cache_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-file batch hits credit exact totals only on full-batch hits, and default prompt edits invalidate disk cache."""

    class _BatchProviderClient:
        model = "gpt-4o-mini"
        prompt_templates: dict[str, str] = {}

        def __init__(self) -> None:
            self.dir_calls = 0

        def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
            # Mimics AnthropicClient/OpenAIClient _build_batch_results: aggregate usage on index 0
            results = [LLMResult(text=f"Summary {f['name']}.") for f in files]
            if results:
                results[0] = LLMResult(
                    text=results[0].text,
                    input_tokens=500,
                    output_tokens=100,
                )
            return results

        def summarize_directory(self, dir_path: Path, file_summaries: list, subdir_summaries: list) -> LLMResult:
            self.dir_calls += 1
            prompt = DEFAULT_PROMPT_TEMPLATES["directory_summary"][:12]
            return LLMResult(text=f"# .\n\nDir ({prompt}) #{self.dir_calls}.\n", input_tokens=120, output_tokens=30)

    cache_path = tmp_path / "batch_cache.json"
    f_a = {"name": "a.py", "content": "a = 1"}
    f_b = {"name": "b.py", "content": "b = 2" * 100}

    c1 = CachingLLMClient(_BatchProviderClient(), cache_path=cache_path)
    c1.summarize_files(tmp_path, [f_a, f_b])

    # Partial batch hit (only f_a): must NOT report an estimated character-length allocation
    c_partial = CachingLLMClient(_BatchProviderClient(), cache_path=cache_path)
    c_partial.summarize_files(tmp_path, [f_a])
    assert c_partial.cache_hits == 1
    assert c_partial.tokens_saved == 0
    assert c_partial.input_tokens_saved == 0
    assert c_partial.output_tokens_saved == 0

    # Full batch hit ([f_a, f_b]): avoids the exact measured batch call (500 in + 100 out = 600)
    c_full = CachingLLMClient(_BatchProviderClient(), cache_path=cache_path)
    c_full.summarize_files(tmp_path, [f_a, f_b])
    assert c_full.cache_hits == 2
    assert c_full.input_tokens_saved == 500
    assert c_full.output_tokens_saved == 100
    assert c_full.tokens_saved == 600

    # Changing DEFAULT_PROMPT_TEMPLATES["directory_summary"] invalidates cached directory summary
    fs = [FileSummary(name="a.py", summary="Summary a.py.")]
    d_client_1 = _BatchProviderClient()
    dc1 = CachingLLMClient(d_client_1, cache_path=cache_path)
    d_res_1 = dc1.summarize_directory(tmp_path, fs, [], content_hash="sha256:fixed")
    assert d_client_1.dir_calls == 1

    monkeypatch.setitem(
        DEFAULT_PROMPT_TEMPLATES,
        "directory_summary",
        "UPDATED DEFAULT DIRECTORY PROMPT: {json_payload}",
    )
    d_client_2 = _BatchProviderClient()
    dc2 = CachingLLMClient(d_client_2, cache_path=cache_path)
    d_res_2 = dc2.summarize_directory(tmp_path, fs, [], content_hash="sha256:fixed")
    assert d_client_2.dir_calls == 1
    assert d_res_2.text != d_res_1.text


def test_config_entrypoints_exclude_test_fixtures_and_respect_capsule_depth(tmp_path: Path) -> None:
    """package.json and pyproject.toml entrypoints must reject test/fixture targets and filter at capsule depth=0."""
    fixture_js = tmp_path / "tests" / "fixtures"
    fixture_js.mkdir(parents=True)
    (fixture_js / "main.js").write_text("export function fixture() {}\n", encoding="utf-8")

    deep_bin = tmp_path / "packages" / "cli" / "bin"
    deep_bin.mkdir(parents=True)
    (deep_bin / "run.js").write_text("export function run() {}\n", encoding="utf-8")

    deep_py = tmp_path / "src" / "pkg" / "nested"
    deep_py.mkdir(parents=True)
    (deep_py / "tool.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    (tmp_path / "root_entry.js").write_text("export function boot() {}\n", encoding="utf-8")

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo-pkg",
                "main": "tests/fixtures/main.js",
                "bin": {
                    "deep-js": "packages/cli/bin/run.js",
                    "root-js": "./root_entry.js",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\nfixture-cli = "tests.fixtures.cli:main"\ndeep-py = "pkg.nested.tool:main"\n',
        encoding="utf-8",
    )

    sk = extract_skeleton(tmp_path)
    assert not any("tests/fixtures" in ep for ep in sk.entrypoints)
    assert not any("fixture-cli" in ep for ep in sk.entrypoints)
    assert "npm:bin:deep-js -> packages/cli/bin/run.js" in sk.entrypoints
    assert "npm:bin:root-js -> ./root_entry.js" in sk.entrypoints
    assert "cli:deep-py -> pkg.nested.tool:main" in sk.entrypoints

    cap0 = api_module.build_fleet_capsule(tmp_path, depth=0)
    assert "npm:bin:root-js -> ./root_entry.js" in cap0.entrypoints
    assert "npm:bin:deep-js -> packages/cli/bin/run.js" not in cap0.entrypoints
    assert "cli:deep-py -> pkg.nested.tool:main" not in cap0.entrypoints
    assert "packages/cli/bin/run.js" not in cap0.capsule_markdown
    assert "pkg.nested.tool:main" not in cap0.capsule_markdown


def test_mode_transition_publication_rollback_and_locked_mode_revalidation(tmp_path: Path) -> None:
    """Mid-publication failures roll back leaf manifests + .ctx/, and waiting refreshes revalidate mode under CtxLock."""
    import ctx.init as init_mod

    repo = _init_git_repo(tmp_path / "repo")
    (repo / "src").mkdir()
    (repo / "src" / "service.py").write_text("def handle() -> int:\n    return 1\n", encoding="utf-8")
    init_project(repo, tier2=True)

    c0_before = (repo / CTX_DIR / "CONTEXT-0.md").read_bytes()
    c1_before = (repo / CTX_DIR / "CONTEXT-1.md").read_bytes()
    cfull_before = (repo / CTX_DIR / "CONTEXT.md").read_bytes()
    meta_before = (repo / CTX_DIR / "metadata.json").read_bytes()

    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")

    # 1. Fail mid-publication AFTER CONTEXT.md export was written, while writing metadata.json
    real_write_text = init_mod.write_text_atomic
    write_calls = 0

    def _fail_on_third_export(path: Path, content: str) -> None:
        nonlocal write_calls
        write_calls += 1
        if path.name == "CONTEXT-0.md":
            raise OSError("disk full during Tier 1 export publication")
        real_write_text(path, content)

    with (
        patch("ctx.api._build_generation_runtime", return_value=(cfg, load_ignore_patterns(repo), _SimpleFakeClient())),
        patch("ctx.init.write_text_atomic", side_effect=_fail_on_third_export),
    ):
        with pytest.raises(OSError, match="disk full during Tier 1 export publication"):
            init_project(repo, force=True, tier2=False)

    assert write_calls >= 2
    assert not (repo / "CONTEXT.md").exists()
    assert not (repo / "src" / "CONTEXT.md").exists()
    assert (repo / CTX_DIR / "CONTEXT-0.md").read_bytes() == c0_before
    assert (repo / CTX_DIR / "CONTEXT-1.md").read_bytes() == c1_before
    assert (repo / CTX_DIR / "CONTEXT.md").read_bytes() == cfull_before
    assert (repo / CTX_DIR / "metadata.json").read_bytes() == meta_before
    assert CtxProject.load(repo, walk_parents=False).is_stale() is False

    # 2. Concurrent mode transition while a refresh that initially selected Tier 2 waits on CtxLock
    entered_tier2_dispatch = threading.Event()
    proceed_to_lock = threading.Event()
    real_refresh_tier2 = api_module._refresh_tier2

    def _delayed_refresh_tier2(root_arg: Path, **kwargs: object) -> api_module.RefreshResult:
        entered_tier2_dispatch.set()
        proceed_to_lock.wait(timeout=5.0)
        return real_refresh_tier2(root_arg, **kwargs)

    refresh_out: list[api_module.RefreshResult] = []
    refresh_err: list[Exception] = []

    with (
        patch("ctx.api._build_generation_runtime", return_value=(cfg, load_ignore_patterns(repo), _SimpleFakeClient())),
        patch("ctx.api._refresh_tier2", side_effect=_delayed_refresh_tier2),
    ):
        def _run_refresh() -> None:
            try:
                refresh_out.append(api_module.refresh(repo))
            except Exception as exc:  # pragma: no cover
                refresh_err.append(exc)

        t = threading.Thread(target=_run_refresh)
        t.start()
        assert entered_tier2_dispatch.wait(timeout=5.0)

        # While t is paused between Tier 2 selection and CtxLock acquisition, transition repo to standard Tier 1!
        init_project(repo, force=True, tier2=False)
        assert json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))["mode"] == "standard"

        proceed_to_lock.set()
        t.join(timeout=10.0)

    assert refresh_err == []
    assert len(refresh_out) == 1
    assert refresh_out[0].strategy != "tier2"
    assert json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))["mode"] == "standard"
    assert (repo / "CONTEXT.md").is_file()
    assert CtxProject.load(repo, walk_parents=False).is_stale() is False


def test_global_stats_dot_ctx_never_hijacks_project_anchor_or_sdk_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """~/.ctx/run_stats.json (without metadata.json) must never anchor non-git projects under HOME."""
    from ctx.config import resolve_project_anchor
    from ctx.sdk import CtxProjectNotFoundError

    fake_home = tmp_path / "fake_home"
    global_ctx = fake_home / ".ctx"
    global_ctx.mkdir(parents=True)
    (global_ctx / "run_stats.json").write_text('{"repos": {}, "totals": {}}\n', encoding="utf-8")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: fake_home))

    demo = fake_home / "work" / "demo"
    (demo / "src").mkdir(parents=True)
    (demo / ".ctxconfig").write_text("provider: ollama\nmodel: fake-qa-model\n", encoding="utf-8")
    (demo / "src" / "main.py").write_text("def run() -> int:\n    return 0\n", encoding="utf-8")

    assert resolve_project_anchor(demo) == demo.resolve()
    assert resolve_project_anchor(demo / "src") == demo.resolve()

    with pytest.raises(CtxProjectNotFoundError):
        CtxProject.load(demo / "src", walk_parents=True)

    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")
    generate_tree(demo, cfg, _SimpleFakeClient(), load_ignore_patterns(demo))

    root_manifest = read_manifest(demo)
    src_manifest = read_manifest(demo / "src")
    assert root_manifest is not None and root_manifest.body.startswith("# .\n")
    assert src_manifest is not None and src_manifest.body.startswith("# src\n")
    assert api_module.check(demo, verify=True).summary["invalid"] == 0
    assert api_module.check(demo / "src", verify=True).summary["invalid"] == 0


def test_descendant_gitignore_cannot_resurrect_excluded_parent_while_ctxignore_can(tmp_path: Path) -> None:
    """A child .gitignore !negation beneath an excluded parent directory must stay ignored; .ctxignore ! overrides win."""
    repo = _init_git_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("/src/private/\n", encoding="utf-8")
    priv = repo / "src" / "private"
    priv.mkdir(parents=True)
    (priv / ".gitignore").write_text("!secret.txt\n", encoding="utf-8")
    secret = priv / "secret.txt"
    secret.write_text("do not leak\n", encoding="utf-8")
    other = priv / "other.txt"
    other.write_text("also excluded\n", encoding="utf-8")

    root_spec = load_ignore_patterns(repo)
    src_spec = load_ignore_patterns(repo / "src")
    priv_spec = load_ignore_patterns(priv)

    assert should_ignore(priv, root_spec, repo) is True
    assert should_ignore(secret, root_spec, repo) is True
    assert should_ignore(priv, src_spec, repo / "src") is True
    assert should_ignore(secret, src_spec, repo / "src") is True
    assert should_ignore(secret, priv_spec, priv) is True
    assert should_ignore(other, priv_spec, priv) is True

    # Explicit .ctxignore override IS authorized to include a specific file while keeping siblings ignored
    allowed = priv / "allowed.txt"
    allowed.write_text("curated doc\n", encoding="utf-8")
    (repo / ".ctxignore").write_text("!/src/private/allowed.txt\n", encoding="utf-8")

    root_spec_override = load_ignore_patterns(repo)
    priv_spec_override = load_ignore_patterns(priv)
    assert should_ignore(priv, root_spec_override, repo) is False
    assert should_ignore(allowed, root_spec_override, repo) is False
    assert should_ignore(secret, root_spec_override, repo) is True
    assert should_ignore(allowed, priv_spec_override, priv) is False
    assert should_ignore(secret, priv_spec_override, priv) is True
    assert should_ignore(other, priv_spec_override, priv) is True


def test_uninit_coordinates_with_live_hook_and_preserves_persistent_hook_guard_inode(tmp_path: Path) -> None:
    """uninit_project must refuse teardown while a live hook holds .ctx-cache/.hook.guard and preserve guard inode."""
    from ctx.init import InitError, run_hook

    repo = _init_git_repo(tmp_path / "repo")
    init_project(repo, tier2=True)

    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONPATH=src_dir)
    ready_file = tmp_path / "hook_holding"
    release_file = tmp_path / "hook_release"
    holder_script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from ctx.init import _acquire_pid, _release_pid\n"
        "root, ready, rel = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])\n"
        "assert _acquire_pid(root)\n"
        "ready.write_text('1')\n"
        "while not rel.exists():\n"
        "    time.sleep(0.01)\n"
        "_release_pid(root)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", holder_script, str(repo), str(ready_file), str(release_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        deadline = time.time() + 5.0
        while not ready_file.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert ready_file.exists()

        guard_path = repo / HOOK_GUARD_FILE
        assert guard_path.is_file()
        assert ".ctx-cache" in guard_path.parts
        guard_inode = guard_path.stat().st_ino

        # Teardown while hook holds the persistent kernel guard must fail cleanly without unlinking guard or .ctx/
        with pytest.raises(InitError, match="Cannot uninitialize while a background ctx hook is running"):
            uninit_project(repo, wait_timeout=0.05)
        assert (repo / CTX_DIR).is_dir()
        assert guard_path.stat().st_ino == guard_inode

        release_file.write_text("1", encoding="utf-8")
        proc.communicate(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    # Now teardown succeeds, .ctx/ is gone, persistent guard inode survives, and post-uninit hook is a no-op
    uninit_project(repo)
    assert not (repo / CTX_DIR).exists()
    assert guard_path.is_file()
    assert guard_path.stat().st_ino == guard_inode

    run_hook(repo, "post-commit")
    assert not (repo / CTX_DIR).exists()

    init_project(repo, tier2=True)
    assert guard_path.stat().st_ino == guard_inode


def test_frozen_live_lock_owner_is_reclaimed_exclusively_after_stale_timeout(tmp_path: Path) -> None:
    """A suspended/frozen live owner holding flock past STALE_TIMEOUT_SECONDS must be reclaimed safely by 1 winner."""
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONPATH=src_dir)
    repo = tmp_path / "repo"
    frozen_ready = tmp_path / "frozen_ready"
    frozen_wake = tmp_path / "frozen_wake"

    frozen_script = (
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "from ctx.lock import CtxLock, STALE_TIMEOUT_SECONDS\n"
        "root, ready, wake = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])\n"
        "lock = CtxLock(root, command='frozen-holder', heartbeat_interval=3600.0)\n"
        "lock.acquire()\n"
        "lock._stop_heartbeat()\n"
        "stale_ts = time.time() - STALE_TIMEOUT_SECONDS - 60.0\n"
        "lock_file = root / '.ctx-cache' / 'lock'\n"
        "guard_file = root / '.ctx-cache' / '.lock.guard'\n"
        "lock_file.write_text(f'pid={os.getpid()}\\ntimestamp={stale_ts}\\ncommand=frozen-holder\\ntoken={lock._token}\\n')\n"
        "os.utime(guard_file, (stale_ts, stale_ts))\n"
        "ready.write_text('1')\n"
        "while not wake.exists():\n"
        "    time.sleep(0.01)\n"
        "lock.release()\n"
        "print('FROZEN_RELEASED')\n"
    )
    frozen_proc = subprocess.Popen(
        [sys.executable, "-c", frozen_script, str(repo), str(frozen_ready), str(frozen_wake)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        deadline = time.time() + 5.0
        while not frozen_ready.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert frozen_ready.exists()
        assert frozen_proc.poll() is None  # Frozen process is alive and still holds open kernel flock fd!

        reclaim_go = tmp_path / "reclaim_go"
        reclaim_done = tmp_path / "reclaim_release_winner"
        winner_holding = tmp_path / "winner_holding"
        contender_script = (
            "import sys, time\n"
            "from pathlib import Path\n"
            "from ctx.lock import CtxLock, LockHeldError\n"
            "root, ready, go, holding, done = [Path(a) for a in sys.argv[1:6]]\n"
            "ready.write_text('1')\n"
            "while not go.exists():\n"
            "    time.sleep(0.005)\n"
            "try:\n"
            "    with CtxLock(root, command='reclaimer'):\n"
            "        holding.write_text('1')\n"
            "        print('RECLAIMED')\n"
            "        while not done.exists():\n"
            "            time.sleep(0.01)\n"
            "except LockHeldError:\n"
            "    print('HELD')\n"
        )
        contenders = []
        for idx in range(3):
            c_ready = tmp_path / f"c_ready_{idx}"
            contenders.append(
                (
                    c_ready,
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            contender_script,
                            str(repo),
                            str(c_ready),
                            str(reclaim_go),
                            str(winner_holding),
                            str(reclaim_done),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=env,
                    ),
                )
            )
        while any(not r.exists() for r, _ in contenders) and time.time() < deadline:
            time.sleep(0.01)
        reclaim_go.write_text("1", encoding="utf-8")

        while not winner_holding.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert winner_holding.exists()

        # Wake the superseded frozen owner while the new winner holds the lock:
        # its release() must fence itself off and NEVER delete the new winner's lock file!
        frozen_wake.write_text("1", encoding="utf-8")
        frozen_out, _ = frozen_proc.communicate(timeout=5)
        assert "FROZEN_RELEASED" in frozen_out
        active_lock_text = (repo / ".ctx-cache" / "lock").read_text(encoding="utf-8")
        assert "command=reclaimer" in active_lock_text

        reclaim_done.write_text("1", encoding="utf-8")
        outputs = [p.communicate(timeout=10)[0].strip() for _, p in contenders]
        assert outputs.count("RECLAIMED") == 1
        assert outputs.count("HELD") == 2
    finally:
        if frozen_proc.poll() is None:
            frozen_proc.kill()
            frozen_proc.communicate()


def test_partial_batch_hit_stats_board_records_zero_and_parallel_cache_writes_are_threadsafe(
    tmp_path: Path,
) -> None:
    """Partial-batch refresh hits must record 0 saved tokens on the stats board, and concurrent cache writes must not race."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("B = 2\n", encoding="utf-8")

    class _BatchOnlyUsageClient:
        model = "gpt-4o-mini"
        prompt_templates: dict[str, str] = {}

        def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
            out = [LLMResult(text=f"Summary of {f['name']}.") for f in files]
            if out:
                out[0] = LLMResult(text=out[0].text, input_tokens=400, output_tokens=100)
            return out

        def summarize_directory(self, dir_path: Path, file_summaries: list, subdir_summaries: list) -> LLMResult:
            return LLMResult(text="# .\n\nBatch test root.\n", input_tokens=100, output_tokens=20)

    cache_file = tmp_path / "cache" / "llm_cache.json"
    cfg = Config(provider="openai", model="gpt-4o-mini", api_key="sk-test", cache_path=str(cache_file))

    # Run 1: summarizes [a.py, b.py] as a 2-file batch
    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(repo), _BatchOnlyUsageClient()),
    ):
        r1 = api_module.refresh(repo, force=True)
    assert r1.tokens_used == 620

    # Run 2: modify b.py only -> a.py is a partial-batch cache hit (1 hit), b.py + directory are misses (2 misses)
    (repo / "b.py").write_text("B = 999\n", encoding="utf-8")
    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(repo), _BatchOnlyUsageClient()),
    ):
        r2 = api_module.refresh(repo)

    assert r2.cache_hits == 1
    assert r2.cache_misses == 2
    assert r2.tokens_saved == 0
    assert r2.tokens_saved_exact is True

    stats_ledger = json.loads((cache_file.parent / "run_stats.json").read_text(encoding="utf-8"))
    latest_run = stats_ledger["runs"][-1]
    assert latest_run["cache_hits"] == 1
    assert latest_run["cache_misses"] == 2
    assert latest_run["tokens_saved"] == 0
    assert latest_run["cost_saved_usd"] == 0.0

    # F7: Concurrent threads writing batches, evicting entries, and serializing sidecar token metadata
    stress_cache = tmp_path / "stress" / "llm_cache.json"
    shared_client = CachingLLMClient(_BatchOnlyUsageClient(), cache_path=stress_cache, max_cache_entries=10)
    thread_errors: list[Exception] = []
    err_lock = threading.Lock()
    start_barrier = threading.Barrier(8)

    def _worker(tid: int) -> None:
        start_barrier.wait()
        try:
            for step in range(8):
                batch = [
                    {"name": f"f_{tid}_{step}_a.py", "content": f"x = {tid} + {step}"},
                    {"name": f"f_{tid}_{step}_b.py", "content": f"y = {tid} * {step}"},
                ]
                shared_client.summarize_files(repo, batch)
                shared_client.summarize_directory(
                    repo,
                    [FileSummary(name=batch[0]["name"], summary="s")],
                    [],
                    content_hash=f"sha256:{tid}:{step}",
                )
        except Exception as exc:  # pragma: no cover
            with err_lock:
                thread_errors.append(exc)

    workers = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    assert thread_errors == []
    parsed_cache = json.loads(stress_cache.read_text(encoding="utf-8"))
    assert len(parsed_cache) <= 10


def test_config_entrypoints_reject_parent_traversal_and_preserve_dot_directories(tmp_path: Path) -> None:
    """../missing.js must be rejected even if repo/missing.js exists, while .bin/tool.js resolves accurately."""
    repo = tmp_path / "repo"
    (repo / ".bin").mkdir(parents=True)
    # Decoy file inside repo that a buggy .lstrip('./') on '../missing.js' would falsely match!
    (repo / "missing.js").write_text("export const decoy = true;\n", encoding="utf-8")
    (repo / ".bin" / "tool.js").write_text("export function runTool() {}\n", encoding="utf-8")

    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "edge-pkg",
                "main": "../missing.js",
                "bin": {
                    "dot-tool": ".bin/tool.js",
                    "abs-escape": "/etc/passwd",
                },
            }
        ),
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "edge"\n[project.scripts]\nbad-cli = "..outside:main"\n',
        encoding="utf-8",
    )

    sk = extract_skeleton(repo)
    assert "npm:main -> ../missing.js" not in sk.entrypoints
    assert not any("abs-escape" in ep for ep in sk.entrypoints)
    assert not any("bad-cli" in ep for ep in sk.entrypoints)
    assert "npm:bin:dot-tool -> .bin/tool.js" in sk.entrypoints

    cap0 = api_module.build_fleet_capsule(repo, depth=0)
    assert "npm:bin:dot-tool -> .bin/tool.js" not in cap0.entrypoints
    cap1 = api_module.build_fleet_capsule(repo, depth=1)
    assert "npm:bin:dot-tool -> .bin/tool.js" in cap1.entrypoints


def test_composite_action_checkout_detection_handles_git_dirs_worktrees_and_explicit_modes(
    tmp_path: Path,
) -> None:
    """The composite action's checkout guard must skip checkout on normal .git dirs, worktrees, and subdirs."""
    import yaml

    action_path = Path(__file__).resolve().parents[1] / ".github" / "actions" / "ctx-check" / "action.yml"
    action_data = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    assert "checkout" in action_data["inputs"]
    detect_step = next(s for s in action_data["runs"]["steps"] if s.get("id") == "detect_checkout")
    script = detect_step["run"]

    def _eval_checkout(target_dir: Path, mode: str = "auto") -> subprocess.CompletedProcess[str]:
        out_file = tmp_path / f"gh_out_{time.time_ns()}"
        out_file.write_text("", encoding="utf-8")
        proc = subprocess.run(
            ["bash", "-c", script],
            env=dict(
                os.environ,
                CTX_TARGET_PATH=str(target_dir),
                CTX_CHECKOUT_MODE=mode,
                GITHUB_OUTPUT=str(out_file),
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        proc.stdout = out_file.read_text(encoding="utf-8").strip()
        return proc

    repo = _init_git_repo(tmp_path / "normal_repo")
    (repo / "sub").mkdir()
    (repo / "sub" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    wt = tmp_path / "linked_wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-b", "wt-ci", str(wt)], capture_output=True, check=True)
    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()

    # 1. Normal .git/ directory -> should_checkout=false
    assert _eval_checkout(repo, "auto").stdout == "should_checkout=false"
    # 2. Subdirectory inside existing git checkout -> should_checkout=false
    assert _eval_checkout(repo / "sub", "auto").stdout == "should_checkout=false"
    # 3. Git worktree (.git pointer file) -> should_checkout=false
    assert _eval_checkout(wt, "auto").stdout == "should_checkout=false"
    # 4. Empty workspace -> should_checkout=true
    assert _eval_checkout(empty_ws, "auto").stdout == "should_checkout=true"
    # 5. Explicit overrides + invalid input validation
    assert _eval_checkout(empty_ws, "false").stdout == "should_checkout=false"
    assert _eval_checkout(repo, "true").stdout == "should_checkout=true"
    assert _eval_checkout(repo, "invalid-mode").returncode != 0


def test_r1_superseded_frozen_writer_cannot_publish_or_rollback_manifests_or_exports(
    tmp_path: Path,
) -> None:
    """A frozen writer whose CtxLock was reclaimed must abort with LockSupersededError and modify 0 bytes."""
    import subprocess
    import sys

    repo = _init_git_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    (repo / "sub" / "worker.py").write_text("def run() -> int:\n    return 1\n", encoding="utf-8")

    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    frozen_ready = tmp_path / "r1_frozen_ready"
    frozen_wake = tmp_path / "r1_frozen_wake"
    reclaimer_ready = tmp_path / "r1_reclaimer_ready"
    reclaimer_release = tmp_path / "r1_reclaimer_release"

    frozen_writer_script = (
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "from unittest.mock import patch\n"
        "from ctx.config import Config\n"
        "from ctx.ignore import load_ignore_patterns\n"
        "from ctx.init import init_project\n"
        "from ctx.llm import LLMResult\n"
        "from ctx.lock import LockSupersededError, STALE_TIMEOUT_SECONDS, _ACTIVE_LOCKS\n"
        "repo, ready, wake = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])\n"
        "class _FreezingClient:\n"
        "    model = 'frozen-model'\n"
        "    def summarize_files(self, d, files):\n"
        "        return [LLMResult(text=f'STALE_FROZEN_{f[\"name\"]}') for f in files]\n"
        "    def summarize_directory(self, d, files, subdirs):\n"
        "        if d.resolve() == repo.resolve():\n"
        "            locks = _ACTIVE_LOCKS[repo.resolve()]\n"
        "            active = locks[0]\n"
        "            active._stop_heartbeat()\n"
        "            stale_ts = time.time() - STALE_TIMEOUT_SECONDS - 120.0\n"
        "            lock_file = repo / '.ctx-cache' / 'lock'\n"
        "            guard_file = repo / '.ctx-cache' / '.lock.guard'\n"
        "            lock_file.write_text(\n"
        "                f'pid={os.getpid()}\\ntimestamp={stale_ts}\\ncommand=refresh\\ntoken={active._token}\\n'\n"
        "            )\n"
        "            os.utime(guard_file, (stale_ts, stale_ts))\n"
        "            ready.write_text('1')\n"
        "            while not wake.exists():\n"
        "                time.sleep(0.01)\n"
        "        return LLMResult(text=f'# {d.name}\\n\\nSTALE_FROZEN_DIR_PURPOSE.')\n"
        "cfg = Config(provider='ollama', model='frozen-model', api_key='none', cache_path='')\n"
        "with patch('ctx.api._build_generation_runtime', return_value=(cfg, load_ignore_patterns(repo), _FreezingClient())):\n"
        "    try:\n"
        "        init_project(repo, force=True, tier2=False)\n"
        "        print('UNEXPECTED_SUCCESS')\n"
        "    except LockSupersededError:\n"
        "        print('SUPERSEDED_ABORTED')\n"
    )

    reclaimer_script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from unittest.mock import patch\n"
        "from ctx.config import Config\n"
        "from ctx.generator import generate_tree\n"
        "from ctx.ignore import load_ignore_patterns\n"
        "from ctx.init import _populate_ctx_dir\n"
        "from ctx.llm import LLMResult\n"
        "from ctx.lock import CtxLock\n"
        "from ctx.stats_board import save_json_atomic, write_text_atomic\n"
        "repo, ready, release_flag = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])\n"
        "class _ReplacementClient:\n"
        "    model = 'replacement-model'\n"
        "    def summarize_files(self, d, files):\n"
        "        return [LLMResult(text=f'REPLACEMENT_CANONICAL_{f[\"name\"]}') for f in files]\n"
        "    def summarize_directory(self, d, files, subdirs):\n"
        "        return LLMResult(text=f'# {d.name}\\n\\nREPLACEMENT_CANONICAL_PURPOSE.')\n"
        "cfg = Config(provider='ollama', model='replacement-model', api_key='none', cache_path='')\n"
        "spec = load_ignore_patterns(repo)\n"
        "with CtxLock(repo, command='replacement-refresh'):\n"
        "    write_text_atomic(repo / '.gitignore', '.ctx/\\n')\n"
        "    spec = load_ignore_patterns(repo)\n"
        "    generate_tree(repo, cfg, _ReplacementClient(), spec)\n"
        "    ctx_dir = repo / '.ctx'\n"
        "    ctx_dir.mkdir(exist_ok=True)\n"
        "    write_text_atomic(ctx_dir / '.gitignore', '*\\n')\n"
        "    _populate_ctx_dir(repo, ctx_dir)\n"
        "    save_json_atomic(ctx_dir / 'metadata.json', {'schema_version': 1, 'mode': 'standard', 'owner': 'replacement'})\n"
        "    ready.write_text('1')\n"
        "    while not release_flag.exists():\n"
        "        time.sleep(0.01)\n"
        "print('REPLACEMENT_DONE')\n"
    )

    frozen_proc = subprocess.Popen(
        [sys.executable, "-c", frozen_writer_script, str(repo), str(frozen_ready), str(frozen_wake)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    reclaimer_proc: subprocess.Popen[str] | None = None
    try:
        deadline = time.time() + 10.0
        while not frozen_ready.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert frozen_ready.exists()
        assert frozen_proc.poll() is None

        reclaimer_proc = subprocess.Popen(
            [sys.executable, "-c", reclaimer_script, str(repo), str(reclaimer_ready), str(reclaimer_release)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        while not reclaimer_ready.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert reclaimer_ready.exists(), reclaimer_proc.stderr.read() if reclaimer_proc.poll() is not None else ""
        assert reclaimer_proc.poll() is None

        # Snapshot every manifest, export, metadata, gitignore, and lock file while replacement owner is active
        tracked_paths = [
            repo / "CONTEXT.md",
            repo / "sub" / "CONTEXT.md",
            repo / ".gitignore",
            repo / CTX_DIR / "CONTEXT.md",
            repo / CTX_DIR / "CONTEXT-1.md",
            repo / CTX_DIR / "CONTEXT-0.md",
            repo / CTX_DIR / "metadata.json",
            repo / ".ctx-cache" / "lock",
        ]
        expected_bytes = {p: p.read_bytes() for p in tracked_paths}
        assert b"REPLACEMENT_CANONICAL" in expected_bytes[repo / "CONTEXT.md"]
        assert b"REPLACEMENT_CANONICAL" in expected_bytes[repo / "sub" / "CONTEXT.md"]
        assert b"REPLACEMENT_CANONICAL" in expected_bytes[repo / CTX_DIR / "CONTEXT-0.md"]

        # Resume the frozen writer while the replacement owner remains active!
        frozen_wake.write_text("1", encoding="utf-8")
        frozen_out, frozen_err = frozen_proc.communicate(timeout=10.0)
        assert "SUPERSEDED_ABORTED" in frozen_out, f"stdout={frozen_out!r} stderr={frozen_err!r}"
        assert "UNEXPECTED_SUCCESS" not in frozen_out

        # Not a single byte of manifests, exports, metadata, gitignore, or lock may be modified or rolled back!
        for path, before_bytes in expected_bytes.items():
            assert path.is_file(), f"Superseded writer unlinked {path}"
            assert path.read_bytes() == before_bytes, f"Superseded writer modified {path}"

        reclaimer_release.write_text("1", encoding="utf-8")
        rec_out, rec_err = reclaimer_proc.communicate(timeout=10.0)
        assert "REPLACEMENT_DONE" in rec_out, f"stdout={rec_out!r} stderr={rec_err!r}"
    finally:
        for proc in (frozen_proc, reclaimer_proc):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()


def test_r2_failed_or_contended_transition_never_clobbers_concurrent_committed_state(
    tmp_path: Path,
) -> None:
    """Failed provider setup or LockHeldError in init_project must never restore stale snapshots over concurrent work."""
    repo = _init_git_repo(tmp_path / "repo")
    init_project(repo, tier2=True)

    s0_c0 = (repo / CTX_DIR / "CONTEXT-0.md").read_bytes()
    entered_runtime = threading.Event()
    fail_runtime = threading.Event()

    def _pausing_failing_runtime(*args: object, **kwargs: object) -> tuple[object, object, object]:
        entered_runtime.set()
        fail_runtime.wait(timeout=5.0)
        raise RuntimeError("Pre-flight check failed: simulated provider outage")

    err_holder: list[BaseException] = []

    with patch("ctx.api._build_generation_runtime", side_effect=_pausing_failing_runtime):
        def _run_init_a() -> None:
            try:
                init_project(repo, force=True, tier2=False)
            except BaseException as exc:
                err_holder.append(exc)

        t_a = threading.Thread(target=_run_init_a)
        t_a.start()
        assert entered_runtime.wait(timeout=5.0)

        # While A is paused in provider setup, Writer B adds a public function and commits Tier 2 refresh S1!
        (repo / "hello.py").write_text("def published_s1_api() -> str:\n    return 'S1'\n", encoding="utf-8")
        b_res = api_module.refresh(repo)
        assert b_res.strategy == "tier2"
        s1_c0 = (repo / CTX_DIR / "CONTEXT-0.md").read_bytes()
        s1_c1 = (repo / CTX_DIR / "CONTEXT-1.md").read_bytes()
        s1_full = (repo / CTX_DIR / "CONTEXT.md").read_bytes()
        s1_meta = (repo / CTX_DIR / "metadata.json").read_bytes()
        s1_gitignore = (repo / ".gitignore").read_bytes()
        assert s1_c0 != s0_c0
        assert b"published_s1_api" in s1_full

        # Now let A's provider setup fail: A must NOT restore S0 over B's S1!
        fail_runtime.set()
        t_a.join(timeout=5.0)

    assert len(err_holder) == 1
    assert isinstance(err_holder[0], RuntimeError)
    assert (repo / CTX_DIR / "CONTEXT-0.md").read_bytes() == s1_c0
    assert (repo / CTX_DIR / "CONTEXT-1.md").read_bytes() == s1_c1
    assert (repo / CTX_DIR / "CONTEXT.md").read_bytes() == s1_full
    assert (repo / CTX_DIR / "metadata.json").read_bytes() == s1_meta
    assert (repo / ".gitignore").read_bytes() == s1_gitignore

    # Also verify LockHeldError while Writer B actively holds CtxLock never triggers rollback
    cfg = Config(provider="ollama", model="fake-qa-model", api_key="not-needed", cache_path="")
    with CtxLock(repo, command="active-writer"):
        (repo / CTX_DIR / "CONTEXT-0.md").write_bytes(s1_c0 + b"\n<!-- active-writer-s2 -->\n")
        s2_c0 = (repo / CTX_DIR / "CONTEXT-0.md").read_bytes()
        with patch(
            "ctx.api._build_generation_runtime",
            return_value=(cfg, load_ignore_patterns(repo), _SimpleFakeClient()),
        ):
            with pytest.raises(LockHeldError):
                init_project(repo, force=True, tier2=False)
        assert (repo / CTX_DIR / "CONTEXT-0.md").read_bytes() == s2_c0
        assert (repo / CTX_DIR / "metadata.json").read_bytes() == s1_meta


def test_r3_mode_revalidation_on_until_complete_cycles_and_tier2_fallback(
    tmp_path: Path,
) -> None:
    """Mode must be revalidated on every CtxLock acquisition across --until-complete passes and Tier 2 fallbacks."""
    # 1. --until-complete mid-cooldown transition from Tier 1 -> Tier 2
    repo = _init_git_repo(tmp_path / "repo_uc")
    (repo / "sub1").mkdir()
    (repo / "sub1" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8")
    (repo / "sub2").mkdir()
    (repo / "sub2" / "b.py").write_text("def b() -> int:\n    return 2\n", encoding="utf-8")

    class _TokenCountingClient:
        model = "budget-model"

        def summarize_files(self, d: Path, files: list[dict]) -> list[LLMResult]:
            return [LLMResult(text=f"Summary of {f['name']}.", input_tokens=40, output_tokens=20) for f in files]

        def summarize_directory(self, d: Path, files: list, subdirs: list) -> LLMResult:
            return LLMResult(text=f"# {d.name}\n\nDirectory purpose.\n", input_tokens=30, output_tokens=10)

    cfg = Config(
        provider="ollama",
        model="budget-model",
        api_key="none",
        cache_path="",
        token_budget=50,
        max_concurrent_dirs=1,
        resume_cooldown_seconds=0.01,
    )

    transitioned_during_cooldown = False

    def _cooldown_hook(_seconds: float) -> None:
        nonlocal transitioned_during_cooldown
        if not transitioned_during_cooldown:
            transitioned_during_cooldown = True
            # Another invocation resets leaf manifests and transitions repo to Tier 2 while lock is released!
            api_module.reset(repo, yes=True)
            init_project(repo, force=True, tier2=True)

    with (
        patch("ctx.api._build_generation_runtime", return_value=(cfg, load_ignore_patterns(repo), _TokenCountingClient())),
        patch("ctx.api._time.sleep", side_effect=_cooldown_hook),
    ):
        uc_res = api_module.refresh(repo, until_complete=True)

    assert transitioned_during_cooldown is True
    assert uc_res.strategy == "tier2"
    assert json.loads((repo / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))["mode"] == "tier2"
    assert not (repo / "CONTEXT.md").exists()
    assert not (repo / "sub1" / "CONTEXT.md").exists()
    assert not (repo / "sub2" / "CONTEXT.md").exists()

    # 2. _refresh_tier2 fallback racing with a transition BACK to Tier 2 during _build_generation_runtime
    repo2 = _init_git_repo(tmp_path / "repo_fb")
    (repo2 / "pkg").mkdir()
    (repo2 / "pkg" / "mod.py").write_text("def mod() -> int:\n    return 3\n", encoding="utf-8")
    init_project(repo2, tier2=True)

    entered_tier2 = threading.Event()
    proceed_tier2 = threading.Event()
    entered_fallback_runtime = threading.Event()
    proceed_fallback_runtime = threading.Event()

    real_refresh_tier2 = api_module._refresh_tier2
    first_tier2_call = True

    def _hooked_refresh_tier2(root_arg: Path, **kwargs: object) -> api_module.RefreshResult:
        nonlocal first_tier2_call
        if first_tier2_call:
            first_tier2_call = False
            entered_tier2.set()
            proceed_tier2.wait(timeout=5.0)
        return real_refresh_tier2(root_arg, **kwargs)

    cfg_fb = Config(provider="ollama", model="fake-qa-model", api_key="none", cache_path="")

    def _hooked_runtime(root_arg: Path, **kwargs: object) -> tuple[Config, object, object]:
        # Only pause the fallback refresh thread (init_project passes _force_tier1=True directly, so filter by thread name)
        if threading.current_thread().name == "fallback-refresh-thread":
            entered_fallback_runtime.set()
            proceed_fallback_runtime.wait(timeout=5.0)
        return cfg_fb, load_ignore_patterns(root_arg), _SimpleFakeClient()

    fb_out: list[api_module.RefreshResult] = []
    fb_err: list[BaseException] = []

    with (
        patch("ctx.api._refresh_tier2", side_effect=_hooked_refresh_tier2),
        patch("ctx.api._build_generation_runtime", side_effect=_hooked_runtime),
    ):
        t_fb = threading.Thread(
            target=lambda: fb_out.append(api_module.refresh(repo2)),
            name="fallback-refresh-thread",
        )
        t_fb.start()
        assert entered_tier2.wait(timeout=5.0)

        # Transition Tier 2 -> Tier 1 while t_fb is about to acquire CtxLock in _refresh_tier2
        init_project(repo2, force=True, tier2=False)
        assert (repo2 / "CONTEXT.md").is_file()

        # Let t_fb observe mode == 'standard' under CtxLock and fall back to refresh()
        proceed_tier2.set()
        assert entered_fallback_runtime.wait(timeout=5.0)

        # While t_fb is building its Tier 1 runtime, reset leaf manifests and transition BACK to Tier 2!
        api_module.reset(repo2, yes=True)
        init_project(repo2, force=True, tier2=True)
        assert not (repo2 / "CONTEXT.md").exists()

        proceed_fallback_runtime.set()
        t_fb.join(timeout=10.0)

    assert fb_err == []
    assert len(fb_out) == 1
    assert fb_out[0].strategy == "tier2"
    assert json.loads((repo2 / CTX_DIR / "metadata.json").read_text(encoding="utf-8"))["mode"] == "tier2"
    assert not (repo2 / "CONTEXT.md").exists()
    assert not (repo2 / "pkg" / "CONTEXT.md").exists()


def test_r4_custom_hooks_path_inside_worktree_stays_fresh_and_rolls_back_on_failure(
    tmp_path: Path,
) -> None:
    """Installing hooks into a non-ignored core.hooksPath directory must leave Tier 1 & Tier 2 100% fresh and roll back cleanly."""
    import ctx.init as init_mod

    repo = _init_git_repo(tmp_path / "repo_hooks")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("def start() -> None:\n    pass\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"],
        capture_output=True,
        check=True,
    )

    cfg = Config(provider="ollama", model="fake-qa-model", api_key="none", cache_path="")

    # 1. Failed Tier 1 initialization must roll back newly created .githooks/, leaf manifests, .ctx/, and .gitignore
    real_write_text = init_mod.write_text_atomic

    def _fail_on_c0(path: Path, content: str) -> None:
        if path.name == "CONTEXT-0.md":
            raise OSError("simulated export failure after hooks installed")
        real_write_text(path, content)

    with (
        patch("ctx.api._build_generation_runtime", return_value=(cfg, load_ignore_patterns(repo), _SimpleFakeClient())),
        patch("ctx.init.write_text_atomic", side_effect=_fail_on_c0),
    ):
        with pytest.raises(OSError, match="simulated export failure after hooks installed"):
            init_project(repo, tier2=False)

    assert not (repo / ".githooks").exists()
    assert not (repo / "CONTEXT.md").exists()
    assert not (repo / CTX_DIR).exists()
    assert not (repo / ".gitignore").exists()

    # 2. Tier 2 init with core.hooksPath=.githooks must include .githooks in hashes and report 0 staleness
    init_project(repo, tier2=True)
    for hook_name in ("post-commit", "post-checkout", "post-merge"):
        assert (repo / ".githooks" / hook_name).is_file()
    proj_t2 = CtxProject.load(repo, walk_parents=False)
    assert proj_t2 is not None
    assert proj_t2.is_stale() is False
    t2_check = api_module.check(repo, verify=True)
    assert t2_check.summary["stale"] == 0
    assert t2_check.summary["invalid"] == 0

    # 3. Tier 1 init --force with core.hooksPath=.githooks must generate .githooks/CONTEXT.md and pass --verify
    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(repo), _SimpleFakeClient()),
    ):
        init_project(repo, force=True, tier2=False)

    assert (repo / ".githooks" / "CONTEXT.md").is_file()
    githooks_manifest = (repo / ".githooks" / "CONTEXT.md").read_text(encoding="utf-8")
    assert "**post-commit**" in githooks_manifest
    assert "**post-checkout**" in githooks_manifest
    assert "**post-merge**" in githooks_manifest
    root_manifest = (repo / "CONTEXT.md").read_text(encoding="utf-8")
    assert "**.githooks/**" in root_manifest

    t1_check = api_module.check(repo, verify=True)
    assert t1_check.summary["stale"] == 0
    assert t1_check.summary["missing"] == 0
    assert t1_check.summary["invalid"] == 0
    assert t1_check.summary["invalid_body"] == 0

    proj_t1 = CtxProject.load(repo, walk_parents=False)
    assert proj_t1 is not None
    assert proj_t1.is_stale() is False


def test_r1_post_validation_pause_blocks_reclamation_and_fences_subsequent_writes(
    tmp_path: Path,
) -> None:
    """Publication fence holds .lock.reclaim.guard across validation+os.replace so TOCTOU overwrite is impossible."""
    repo = _init_git_repo(tmp_path / "repo_r1_fence")
    (repo / "sub").mkdir()
    (repo / "sub" / "worker.py").write_text("def work() -> int:\n    return 1\n", encoding="utf-8")

    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    in_fence_ready = tmp_path / "in_fence_ready"
    resume_commit = tmp_path / "resume_commit"
    post_fence_frozen = tmp_path / "post_fence_frozen"
    wake_frozen = tmp_path / "wake_frozen"
    reclaimer_ready = tmp_path / "reclaimer_ready"
    reclaimer_release = tmp_path / "reclaimer_release"

    writer_a_script = (
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "from unittest.mock import patch\n"
        "import ctx.lock as lock_mod\n"
        "from ctx.config import Config\n"
        "from ctx.ignore import load_ignore_patterns\n"
        "from ctx.init import init_project\n"
        "from ctx.llm import LLMResult\n"
        "from ctx.lock import LockSupersededError, STALE_TIMEOUT_SECONDS, _ACTIVE_LOCKS\n"
        "repo, in_fence, resume_c, post_frozen, wake_f = [Path(p) for p in sys.argv[1:6]]\n"
        "sub_manifest = (repo / 'sub' / 'CONTEXT.md').resolve()\n"
        "paused_once = False\n"
        "def _post_validation_hook(target: Path) -> None:\n"
        "    global paused_once\n"
        "    if not paused_once and target.resolve() == sub_manifest:\n"
        "        paused_once = True\n"
        "        active = _ACTIVE_LOCKS[repo.resolve()][0]\n"
        "        active._stop_heartbeat()\n"
        "        stale_ts = time.time() - STALE_TIMEOUT_SECONDS - 120.0\n"
        "        (repo / '.ctx-cache' / 'lock').write_text(\n"
        "            f'pid={os.getpid()}\\ntimestamp={stale_ts}\\ncommand=refresh\\ntoken={active._token}\\n'\n"
        "        )\n"
        "        os.utime(repo / '.ctx-cache' / '.lock.guard', (stale_ts, stale_ts))\n"
        "        in_fence.write_text('1')\n"
        "        while not resume_c.exists():\n"
        "            time.sleep(0.01)\n"
        "lock_mod._POST_FENCE_VALIDATION_HOOK = _post_validation_hook\n"
        "class _TwoStageClient:\n"
        "    model = 'writer-a'\n"
        "    def summarize_files(self, d, files):\n"
        "        return [LLMResult(text=f'WRITER_A_{f[\"name\"]}') for f in files]\n"
        "    def summarize_directory(self, d, files, subdirs):\n"
        "        if d.resolve() == repo.resolve():\n"
        "            post_frozen.write_text('1')\n"
        "            while not wake_f.exists():\n"
        "                time.sleep(0.01)\n"
        "        return LLMResult(text=f'# {d.name}\\n\\nWRITER_A_PURPOSE.')\n"
        "cfg = Config(provider='ollama', model='writer-a', api_key='none', cache_path='')\n"
        "with patch('ctx.api._build_generation_runtime', return_value=(cfg, load_ignore_patterns(repo), _TwoStageClient())):\n"
        "    try:\n"
        "        init_project(repo, force=True, tier2=False)\n"
        "        print('UNEXPECTED_A_SUCCESS')\n"
        "    except LockSupersededError:\n"
        "        print('WRITER_A_FENCED')\n"
    )

    reclaimer_b_script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from ctx.config import Config\n"
        "from ctx.generator import generate_tree\n"
        "from ctx.ignore import load_ignore_patterns\n"
        "from ctx.init import _populate_ctx_dir\n"
        "from ctx.llm import LLMResult\n"
        "from ctx.lock import CtxLock\n"
        "from ctx.stats_board import save_json_atomic, write_text_atomic\n"
        "repo, ready, rel = [Path(p) for p in sys.argv[1:4]]\n"
        "class _CanonicalBClient:\n"
        "    model = 'canonical-b'\n"
        "    def summarize_files(self, d, files):\n"
        "        return [LLMResult(text=f'CANONICAL_B_{f[\"name\"]}') for f in files]\n"
        "    def summarize_directory(self, d, files, subdirs):\n"
        "        return LLMResult(text=f'# {d.name}\\n\\nCANONICAL_B_PURPOSE.')\n"
        "cfg = Config(provider='ollama', model='canonical-b', api_key='none', cache_path='')\n"
        "with CtxLock(repo, command='canonical-b'):\n"
        "    write_text_atomic(repo / '.gitignore', '.ctx/\\n')\n"
        "    spec = load_ignore_patterns(repo)\n"
        "    generate_tree(repo, cfg, _CanonicalBClient(), spec)\n"
        "    ctx_dir = repo / '.ctx'\n"
        "    write_text_atomic(ctx_dir / '.gitignore', '*\\n')\n"
        "    _populate_ctx_dir(repo, ctx_dir)\n"
        "    save_json_atomic(ctx_dir / 'metadata.json', {'schema_version': 1, 'mode': 'standard', 'owner': 'B'})\n"
        "    ready.write_text('1')\n"
        "    while not rel.exists():\n"
        "        time.sleep(0.01)\n"
        "print('CANONICAL_B_DONE')\n"
    )

    proc_a = subprocess.Popen(
        [
            sys.executable,
            "-c",
            writer_a_script,
            str(repo),
            str(in_fence_ready),
            str(resume_commit),
            str(post_fence_frozen),
            str(wake_frozen),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    proc_b: subprocess.Popen[str] | None = None
    try:
        deadline = time.time() + 10.0
        while not in_fence_ready.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert in_fence_ready.exists(), proc_a.stderr.read() if proc_a.poll() is not None else ""

        # Writer A has ALREADY passed verify_ownership() inside publication_fence() and is paused right before os.replace!
        # Even though lock timestamp + .lock.guard mtime are stale, reclamation MUST be blocked by .lock.reclaim.guard!
        with pytest.raises(LockHeldError):
            with CtxLock(repo, command="premature-reclaimer"):
                pass

        # Allow Writer A to finish committing sub/CONTEXT.md, exit publication_fence(), and freeze before root CONTEXT.md
        resume_commit.write_text("1", encoding="utf-8")
        while not post_fence_frozen.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert post_fence_frozen.exists()

        # Now Writer A is outside publication_fence() and genuinely frozen -> Reclaimer B MUST reclaim and publish CANONICAL_B!
        proc_b = subprocess.Popen(
            [sys.executable, "-c", reclaimer_b_script, str(repo), str(reclaimer_ready), str(reclaimer_release)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        while not reclaimer_ready.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert reclaimer_ready.exists(), proc_b.stderr.read() if proc_b.poll() is not None else ""

        tracked = [
            repo / "CONTEXT.md",
            repo / "sub" / "CONTEXT.md",
            repo / ".gitignore",
            repo / CTX_DIR / "CONTEXT.md",
            repo / CTX_DIR / "CONTEXT-1.md",
            repo / CTX_DIR / "CONTEXT-0.md",
            repo / CTX_DIR / "metadata.json",
            repo / ".ctx-cache" / "lock",
        ]
        snap_b = {p: p.read_bytes() for p in tracked}
        assert b"CANONICAL_B" in snap_b[repo / "sub" / "CONTEXT.md"]
        assert b"CANONICAL_B" in snap_b[repo / "CONTEXT.md"]

        # Wake Writer A: its next fenced commit (root CONTEXT.md) and rollback MUST abort without touching a single byte!
        wake_frozen.write_text("1", encoding="utf-8")
        out_a, err_a = proc_a.communicate(timeout=10.0)
        assert "WRITER_A_FENCED" in out_a, f"stdout={out_a!r} stderr={err_a!r}"

        for p, expected in snap_b.items():
            assert p.is_file()
            assert p.read_bytes() == expected

        reclaimer_release.write_text("1", encoding="utf-8")
        out_b, err_b = proc_b.communicate(timeout=10.0)
        assert "CANONICAL_B_DONE" in out_b, f"stdout={out_b!r} stderr={err_b!r}"
    finally:
        for p in (proc_a, proc_b):
            if p is not None and p.poll() is None:
                p.kill()
                p.communicate()


def test_r5_hook_telemetry_holds_hook_guard_and_never_recreates_ctx_after_uninit(
    tmp_path: Path,
) -> None:
    """run_hook must retain .ctx-cache/.hook.guard through _append_hook_log so uninit never leaves .ctx/hook_log.json."""
    import ctx.init as init_mod
    from ctx.init import InitError, _acquire_pid, run_hook

    repo = _init_git_repo(tmp_path / "repo_r5")
    (repo / "app.py").write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    init_project(repo, tier2=True)

    entered_telemetry = threading.Event()
    release_telemetry = threading.Event()
    real_append_log = init_mod._append_hook_log

    def _pausing_append_log(ctx_dir: Path, entry: dict) -> None:
        entered_telemetry.set()
        release_telemetry.wait(timeout=5.0)
        real_append_log(ctx_dir, entry)

    uninit_done = threading.Event()
    uninit_err: list[BaseException] = []

    with patch("ctx.init._append_hook_log", side_effect=_pausing_append_log):
        hook_thread = threading.Thread(target=run_hook, args=(repo, "post-commit"))
        hook_thread.start()
        assert entered_telemetry.wait(timeout=5.0)

        # 1. While run_hook is paused at telemetry publication, .hook.guard MUST still be held!
        with pytest.raises(InitError, match="Cannot uninitialize while a background ctx hook is running"):
            uninit_project(repo, wait_timeout=0.04)

        # 2. A waiting uninit_project waits for telemetry + _release_pid, then removes .ctx/ completely
        def _run_waiting_uninit() -> None:
            try:
                uninit_project(repo, wait_timeout=5.0)
            except BaseException as exc:  # pragma: no cover
                uninit_err.append(exc)
            finally:
                uninit_done.set()

        uninit_thread = threading.Thread(target=_run_waiting_uninit)
        uninit_thread.start()
        time.sleep(0.05)
        assert not uninit_done.is_set()

        release_telemetry.set()
        hook_thread.join(timeout=5.0)
        uninit_thread.join(timeout=5.0)

    assert uninit_err == []
    assert not (repo / CTX_DIR).exists()

    # 3. Late _acquire_pid(..., _active_hook=True) after teardown must return False without creating .ctx/
    assert _acquire_pid(repo, _active_hook=True) is False
    assert not (repo / CTX_DIR).exists()

    # 4. Subsequent init_project without --force must succeed cleanly
    init_project(repo, tier2=True)
    assert (repo / CTX_DIR / "metadata.json").is_file()


def test_r6_concurrent_worktree_init_and_peer_uninit_preserve_shared_hooks_and_clean_rollback(
    tmp_path: Path,
) -> None:
    """Shared worktree hooks must serialize concurrent peer init/uninit and clean up accurately on failure or dual uninit."""
    from ctx.init import CTX_HOOK_START, HOOK_NAMES, _resolve_hooks_dir

    repo_a = _init_git_repo(tmp_path / "repo_a")
    (repo_a / "mod.py").write_text("def f() -> int:\n    return 1\n", encoding="utf-8")
    wt_b = tmp_path / "wt_b"
    subprocess.run(
        ["git", "-C", str(repo_a), "worktree", "add", "-b", "feature-wt-b", str(wt_b)],
        capture_output=True,
        check=True,
    )
    shared_hooks_dir = _resolve_hooks_dir(repo_a).resolve()
    assert _resolve_hooks_dir(wt_b).resolve() == shared_hooks_dir

    cfg = Config(provider="ollama", model="fake-qa-model", api_key="none", cache_path="")

    # 1. repo_a is initialized; wt_b pauses mid-init AFTER _install_hooks and BEFORE wt_b/.ctx/metadata.json exists,
    #    while repo_a runs uninit_project(repo_a). Shared hooks MUST survive for wt_b!
    init_project(repo_a, tier2=True)
    b_hooks_installed_pause = threading.Event()
    b_resume_publish = threading.Event()

    class _PausingClient(_SimpleFakeClient):
        def summarize_directory(self, d: Path, files: list, subdirs: list) -> LLMResult:
            if d.resolve() == wt_b.resolve():
                b_hooks_installed_pause.set()
                b_resume_publish.wait(timeout=5.0)
            return super().summarize_directory(d, files, subdirs)

    b_err: list[BaseException] = []
    a_uninit_res: list[dict] = []
    a_err: list[BaseException] = []

    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(wt_b), _PausingClient()),
    ):
        t_b = threading.Thread(target=lambda: init_project(wt_b, tier2=False))
        t_b.start()
        assert b_hooks_installed_pause.wait(timeout=5.0)
        assert not (wt_b / CTX_DIR / "metadata.json").exists()

        def _uninit_a() -> None:
            try:
                a_uninit_res.append(uninit_project(repo_a))
            except BaseException as exc:  # pragma: no cover
                a_err.append(exc)

        t_a = threading.Thread(target=_uninit_a)
        t_a.start()
        time.sleep(0.05)
        # t_a must wait on _shared_hooks_lock while t_b finishes publishing wt_b/.ctx/metadata.json
        assert t_a.is_alive()

        b_resume_publish.set()
        t_b.join(timeout=10.0)
        t_a.join(timeout=10.0)

    assert b_err == []
    assert a_err == []
    assert not (repo_a / CTX_DIR).exists()
    assert (wt_b / CTX_DIR / "metadata.json").is_file()
    assert a_uninit_res[0]["hooks_removed"] == []
    for hook_name in HOOK_NAMES:
        hook_file = shared_hooks_dir / hook_name
        assert hook_file.is_file(), f"Peer uninit deleted shared hook {hook_name} needed by wt_b!"
        assert CTX_HOOK_START in hook_file.read_text(encoding="utf-8")

    # 2. Dual concurrent uninit(repo_a) + uninit(wt_b) when BOTH are initialized -> neither remains initialized AND hooks are removed!
    init_project(repo_a, tier2=True)
    barrier = threading.Barrier(2)
    dual_results: list[dict] = []
    dual_lock = threading.Lock()

    def _barrier_uninit(target: Path) -> None:
        barrier.wait(timeout=5.0)
        res = uninit_project(target)
        with dual_lock:
            dual_results.append(res)

    t1 = threading.Thread(target=_barrier_uninit, args=(repo_a,))
    t2 = threading.Thread(target=_barrier_uninit, args=(wt_b,))
    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    assert len(dual_results) == 2
    assert not (repo_a / CTX_DIR).exists()
    assert not (wt_b / CTX_DIR).exists()
    for hook_name in HOOK_NAMES:
        assert not (shared_hooks_dir / hook_name).exists()

    # 3. Failing init_project(wt_b) concurrent with uninit_project(repo_a) -> clean rollback + hooks removed when neither remains initialized
    pre_step3_wt_b_manifest = (wt_b / "CONTEXT.md").read_bytes()
    (wt_b / "step3_sub").mkdir()
    (wt_b / "step3_sub" / "extra.py").write_text("X = 3\n", encoding="utf-8")
    init_project(repo_a, tier2=True)
    b_fail_pause = threading.Event()
    b_trigger_fail = threading.Event()

    class _FailingClient(_SimpleFakeClient):
        def summarize_directory(self, d: Path, files: list, subdirs: list) -> LLMResult:
            if d.resolve() == wt_b.resolve():
                b_fail_pause.set()
                b_trigger_fail.wait(timeout=5.0)
                raise RuntimeError("simulated mid-init LLM crash in wt_b")
            return super().summarize_directory(d, files, subdirs)

    b_fail_exc: list[BaseException] = []
    a_uninit_after_fail: list[dict] = []

    with patch(
        "ctx.api._build_generation_runtime",
        return_value=(cfg, load_ignore_patterns(wt_b), _FailingClient()),
    ):
        def _failing_init_b() -> None:
            try:
                init_project(wt_b, force=True, tier2=False)
            except BaseException as exc:
                b_fail_exc.append(exc)

        tb_fail = threading.Thread(target=_failing_init_b)
        tb_fail.start()
        assert b_fail_pause.wait(timeout=5.0)
        assert (wt_b / "step3_sub" / "CONTEXT.md").is_file()

        ta_uninit = threading.Thread(target=lambda: a_uninit_after_fail.append(uninit_project(repo_a)))
        ta_uninit.start()
        time.sleep(0.05)
        assert ta_uninit.is_alive()

        b_trigger_fail.set()
        tb_fail.join(timeout=10.0)
        ta_uninit.join(timeout=10.0)

    assert len(b_fail_exc) == 1
    assert not (wt_b / CTX_DIR).exists()
    assert not (wt_b / "step3_sub" / "CONTEXT.md").exists()
    assert (wt_b / "CONTEXT.md").read_bytes() == pre_step3_wt_b_manifest
    assert not (repo_a / CTX_DIR).exists()
    assert len(a_uninit_after_fail) == 1
    assert set(a_uninit_after_fail[0]["hooks_removed"]) == set(HOOK_NAMES)
    for hook_name in HOOK_NAMES:
        assert not (shared_hooks_dir / hook_name).exists()


