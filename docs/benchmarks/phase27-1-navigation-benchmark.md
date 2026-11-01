# Phase 27.1 — Deterministic Static-Oracle Navigation & Blast-Radius Benchmark

- **Generated:** `2026-11-01T03:48:22Z`
- **Generator:** `ctx/1.1.0` (`phase-27.1-v2-static-oracle`)
- **Methodology:** `deterministic_static_oracle_retrieval`
- **Repositories Evaluated:** 3
- **Reproduce:** `ctx benchmark <repo1> [repo2 ...] --out-file docs/benchmarks/phase27-1-navigation-benchmark.md`

## Methodology & Scope

This benchmark deterministically evaluates retrieval context-token efficiency and recall across three fixed navigation workflows (`raw_grep`, `tier1_manifests`, and `tier2_plus_impact`) against an **independent static AST/filesystem ground-truth oracle** built directly from raw files on disk (without calling `ctx.skeleton` or `ctx.impact`). Condition A executes real file reads and real line-by-line regex grep (`\b<stem>\b`) over repository files; Condition B reads depth-0/1 `CONTEXT.md` manifests plus regex grep; Condition C reads rendered `.ctx/CONTEXT-0.md` plus `ctx impact <focal_target> --output json`. All four recall scores are computed strictly by set intersection / identifier presence against the independent oracle (no stochastic LLM agent rollouts and no hardcoded recall constants).

## Executive Summary

Across **3** repositories and **4** static-oracle retrieval tasks (Authority & Architecture Orientation, Public Operational Surface Discovery, Multi-Hop Blast-Radius Tracing, and Coupled Test Selection), **Condition C (`tier2_plus_impact`: `.ctx/CONTEXT-0.md` + `ctx impact`)** achieves:

- **88.0% fewer context tokens ingested** vs `raw_grep` (`3458.0` vs `28832.3` mean tokens)
- **79.3% fewer retrieval turns** vs `raw_grep` (`2.0` vs `9.67` mean turns)
- **+18.0 percentage points higher static-oracle recall** (`0.8735` vs `0.6934`), driven by multi-hop transitive reverse-dependency & operational surface extraction
- **0 Type-II LLM maintenance tokens** on implementation-only commits (`should_invoke_llm() == False`) and non-material structural tweaks gated by Type 1 Jev (`invariant_drift_material`, ~1373 System-One input tokens @ `$0.042/1M`)

## Aggregate Condition Comparison

| Condition | Mean Turns | Mean Context Tokens | Mean Overall Recall | Blast-Radius Recall | Surface Recall | Maint. Type-II LLM Tokens (Impl / Minor Struct) |
|-----------|-----------:|--------------------:|--------------------:|--------------------:|---------------:|------------------------------------------------:|
| A. `raw_grep` (No `ctx`) | 9.67 | 28832.3 | 0.6934 | 0.8542 | 0.8985 | 0 / 0 |
| B. `tier1_manifests` (Per-dir `CONTEXT.md`) | 7.00 | 8849.7 | 0.6343 | 0.8542 | 0.2289 | 8445 / 8445 |
| C. `tier2_plus_impact` (`CONTEXT-0.md` + `ctx impact`) | 2.00 | 3458.0 | 0.8735 | 1.0000 | 1.0000 | 0 / 0 (+1373 Jev T1) |

## Per-Repository Results

### `context-project` (160 files, 11 subsystems, 242 internal edges, 33 public surfaces)

- **Focal High-Fan-In Target:** `src/ctx/config.py` (14 direct prod dependents, 19 transitive prod dependents, 25 coupled test suites)

| Condition | Turns | Context Tokens | Arch Recall | Surface Recall | Blast-Radius Recall | Coupled-Test Recall | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|--------------------:|--------------------:|------------:|
| `raw_grep` | 10 | 29120 | 0.2000 | 0.9394 | 0.7368 | 0.6400 | **0.6291** |
| `tier1_manifests` | 7 | 10589 | 0.9000 | 0.3636 | 0.7368 | 0.6400 | **0.6601** |
| `tier2_plus_impact` | 2 | 3959 | 0.8000 | 1.0000 | 1.0000 | 1.0000 | **0.9500** |

### `project-ledger` (153 files, 12 subsystems, 214 internal edges, 32 public surfaces)

- **Focal High-Fan-In Target:** `ledger/identity.py` (11 direct prod dependents, 12 transitive prod dependents, 25 coupled test suites)

| Condition | Turns | Context Tokens | Arch Recall | Surface Recall | Blast-Radius Recall | Coupled-Test Recall | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|--------------------:|--------------------:|------------:|
| `raw_grep` | 10 | 29952 | 0.2000 | 1.0000 | 0.9167 | 0.8400 | **0.7392** |
| `tier1_manifests` | 7 | 8093 | 0.8000 | 0.2500 | 0.9167 | 0.8400 | **0.7017** |
| `tier2_plus_impact` | 2 | 3471 | 0.5000 | 1.0000 | 1.0000 | 1.0000 | **0.8750** |

### `machina` (595 files, 13 subsystems, 124 internal edges, 41 public surfaces)

- **Focal High-Fan-In Target:** `src/machina/runtime.py` (20 direct prod dependents, 22 transitive prod dependents, 8 coupled test suites)

| Condition | Turns | Context Tokens | Arch Recall | Surface Recall | Blast-Radius Recall | Coupled-Test Recall | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|--------------------:|--------------------:|------------:|
| `raw_grep` | 9 | 27425 | 0.1818 | 0.7561 | 0.9091 | 1.0000 | **0.7118** |
| `tier1_manifests` | 7 | 7867 | 0.1818 | 0.0732 | 0.9091 | 1.0000 | **0.5410** |
| `tier2_plus_impact` | 2 | 2944 | 0.1818 | 1.0000 | 1.0000 | 1.0000 | **0.7955** |

