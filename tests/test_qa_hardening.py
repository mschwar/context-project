"""Regression tests for concurrency, kernel-fenced locks, ignore precedence, and skeleton/capsule extraction."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
import yaml

import ctx.api as api_module
from ctx.config import resolve_project_anchor
from ctx.ignore import load_ignore_patterns, should_ignore
from ctx.init import CTX_DIR, init_project
from ctx.lock import STALE_TIMEOUT_SECONDS, CtxLock, LockHeldError
from ctx.sdk import CtxProject, CtxProjectNotFoundError
from ctx.skeleton import extract_skeleton


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

    guard_file = tmp_path / ".ctx-cache" / ".lock.guard"
    assert guard_file.is_file()
    guard_inode_before = guard_file.stat().st_ino

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

    (tmp_path / "go.mod").write_text("module github.com/acme/beta\n\ngo 1.22\n", encoding="utf-8")
    sk2 = extract_skeleton(tmp_path)
    assert sk2.structural_hash != sk1.structural_hash

    sk_py = extract_skeleton(tmp_path, extensions=[".py"])
    assert [f.relative_path for f in sk_py.files] == ["src/core.py"]
    assert sk_py.boundary_docs == []
    assert sk_py.entrypoints == []


def test_nested_and_ancestor_gitignore_sdk_staleness_and_capsule_depth_zero(tmp_path: Path) -> None:
    """Verify nested/ancestor .gitignore rules, full-tier SDK export staleness, and depth=0 capsule filtering."""
    repo = _init_git_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("*.secret\n/src/generated/\nkeep_me.secret\n", encoding="utf-8")
    (repo / ".ctxignore").write_text("!keep_me.secret\n", encoding="utf-8")
    (repo / "src" / "generated").mkdir(parents=True)
    (repo / "src" / "sub").mkdir(parents=True)
    (repo / "src" / "sub" / ".gitignore").write_text("nested_only.tmpdata\n", encoding="utf-8")

    root_spec = load_ignore_patterns(repo)
    nested_secret = repo / "src" / "sub" / "nested_only.tmpdata"
    nested_secret.write_text("x", encoding="utf-8")
    other_file = repo / "src" / "nested_only.tmpdata"
    other_file.write_text("x", encoding="utf-8")
    assert should_ignore(nested_secret, root_spec, repo) is True
    assert should_ignore(other_file, root_spec, repo) is False

    sub_spec = load_ignore_patterns(repo / "src")
    (repo / "src" / " hidden.secret").write_text("x", encoding="utf-8")
    (repo / "src" / "keep_me.secret").write_text("x", encoding="utf-8")
    assert should_ignore(repo / "src" / "generated", sub_spec, repo / "src") is True
    assert should_ignore(repo / "src" / " hidden.secret", sub_spec, repo / "src") is True
    assert should_ignore(repo / "src" / "keep_me.secret", sub_spec, repo / "src") is False

    for p in (nested_secret, other_file, repo / "src" / " hidden.secret", repo / "src" / "keep_me.secret"):
        p.unlink()

    (repo / "src" / "cli.py").write_text("def cli_entry() -> None:\n    pass\n", encoding="utf-8")
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "adr" / "001-choice.md").write_text("# ADR 1\n\nDecision.\n", encoding="utf-8")
    init_project(repo, force=True)

    proj = CtxProject.load(repo, walk_parents=False)
    assert proj.is_stale() is False

    (repo / CTX_DIR / "CONTEXT.md").write_text("# outdated export\n", encoding="utf-8")
    assert proj.is_stale() is True

    (repo / "AGENTS.md").write_text("# AGENTS\n\nRoot governance.\n", encoding="utf-8")
    cap0 = api_module.build_fleet_capsule(repo, depth=0)
    assert all(b["path"] == "AGENTS.md" for b in cap0.authority_boundaries)
    assert "file:src/cli.py" not in cap0.entrypoints
    assert "001-choice.md" not in cap0.capsule_markdown


def test_subtree_ignore_honors_wildcard_root_gitignore_and_subtree_dispatch(
    tmp_path: Path,
) -> None:
    """Wildcard root rules (/src/*/private.txt) hold on src/pkg, and subtree refresh/check/export resolve repo root."""
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

    init_project(repo)
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


def test_config_entrypoints_exclude_test_fixtures_and_respect_capsule_depth(tmp_path: Path) -> None:
    """package.json and pyproject.toml entrypoints reject test/fixture targets and filter at capsule depth=0."""
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


def test_global_dot_ctx_without_metadata_never_hijacks_project_anchor_or_sdk_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """~/.ctx/ without metadata.json must never anchor non-git projects under HOME."""
    fake_home = tmp_path / "fake_home"
    global_ctx = fake_home / ".ctx"
    global_ctx.mkdir(parents=True)
    (global_ctx / "some_file.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: fake_home))

    demo = fake_home / "work" / "demo"
    (demo / "src").mkdir(parents=True)
    (demo / ".ctxconfig").write_text("max_depth: 4\n", encoding="utf-8")
    (demo / "src" / "main.py").write_text("def run() -> int:\n    return 0\n", encoding="utf-8")

    assert resolve_project_anchor(demo) == demo.resolve()
    assert resolve_project_anchor(demo / "src") == demo.resolve()

    with pytest.raises(CtxProjectNotFoundError):
        CtxProject.load(demo / "src", walk_parents=True)


def test_descendant_gitignore_cannot_resurrect_excluded_parent_while_ctxignore_can(tmp_path: Path) -> None:
    """A child .gitignore !negation beneath an excluded parent directory stays ignored; .ctxignore ! overrides win."""
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX frozen-owner guard-inode rotation")
def test_frozen_live_lock_owner_is_reclaimed_exclusively_after_stale_timeout(tmp_path: Path) -> None:
    """A suspended/frozen live owner holding flock past STALE_TIMEOUT_SECONDS is reclaimed safely by 1 winner."""
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
        assert frozen_proc.poll() is None

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


def test_config_entrypoints_reject_parent_traversal_and_preserve_dot_directories(tmp_path: Path) -> None:
    """../missing.js is rejected even if repo/missing.js exists, while .bin/tool.js resolves accurately."""
    repo = tmp_path / "repo"
    (repo / ".bin").mkdir(parents=True)
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
    """The composite action's checkout guard skips checkout on normal .git dirs, worktrees, and subdirs."""
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

    assert _eval_checkout(repo, "auto").stdout == "should_checkout=false"
    assert _eval_checkout(repo / "sub", "auto").stdout == "should_checkout=false"
    assert _eval_checkout(wt, "auto").stdout == "should_checkout=false"
    assert _eval_checkout(empty_ws, "auto").stdout == "should_checkout=true"
    assert _eval_checkout(empty_ws, "false").stdout == "should_checkout=false"
    assert _eval_checkout(repo, "true").stdout == "should_checkout=true"
    assert _eval_checkout(repo, "invalid-mode").returncode != 0
