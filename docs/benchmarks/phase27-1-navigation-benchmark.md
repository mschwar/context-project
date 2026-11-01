# Phase 27.1 — Deterministic Static-Oracle Navigation & Blast-Radius Benchmark

- **Generated:** `2026-11-01T04:27:38Z`
- **Generator:** `ctx/1.1.0` (`phase-27.1-v3-static-oracle-f1`)
- **Methodology:** `deterministic_static_oracle_retrieval`
- **Maintenance Cost Basis:** `modeled_analytical_estimate`
- **Repositories Evaluated:** 3
- **Reproduce:** `ctx benchmark <repo1> [repo2 ...] --out-file docs/benchmarks/phase27-1-navigation-benchmark.md`

## Methodology & Scope

This benchmark deterministically evaluates retrieval context-token efficiency, recall, precision, and F1 across three scripted retrieval workflows (`raw_grep`, `tier1_manifests`, and `tier2_plus_impact`) against a separate static AST/filesystem reference oracle built directly from raw files on disk:

- **Condition A (`raw_grep`):** Lists the file tree, reads root docs (`README.md`, `AGENTS.md`, `CLAUDE.md`) plus up to 2 architecture/governance docs discovered in the file tree, reads candidate entrypoints and the focal module, and runs line-by-line regex grep (`\b<stem>\b`) over production and test files.
- **Condition B (`tier1_manifests`):** Reads depth-0/1 `CONTEXT.md` manifests (`ctx export --depth 1`), reads the primary entrypoint, and runs symbol-augmented regex grep (`\b(?:<stem>|<exported_symbols>)\b`).
- **Condition C (`tier2_plus_impact`):** Reads `.ctx/CONTEXT-0.md` and `ctx impact <focal_target> --output json`.

**Scope Disclosures:** Both the reference oracle and `ctx.impact` evaluate static import graphs (measuring static-graph retrieval recall/precision vs lexical grep rather than dynamic runtime dispatch), and per-commit maintenance token figures in the rightmost column are **modeled analytical estimates** rather than live billing logs.

## Executive Summary

Across **3** repositories and **4** static-oracle retrieval dimensions (Authority & Architecture Orientation, Public Operational Surface Discovery, Multi-Hop Blast-Radius Tracing, and Coupled Test Selection), **Condition C (`tier2_plus_impact`: `.ctx/CONTEXT-0.md` + `ctx impact`)** achieves:

- **90.0% context-token reduction** vs `raw_grep` (`3463.0` vs `34625.7` mean tokens)
- **82.9% retrieval-step reduction** vs `raw_grep` (`2.0` vs `11.67` mean steps)
- **+12.6 percentage points static-oracle mean recall delta** (`0.8735` vs `0.7479`) and **+71.1 percentage points blast-radius F1 delta** (`1.0000` vs `0.2891`)
- **0 modeled Type-II LLM maintenance tokens** on implementation-only commits (`should_invoke_llm() == False`) and non-material structural tweaks gated by Type 1 Jev (`invariant_drift_material`, ~215 modeled System-One input tokens @ `$0.042/1M`)

## Aggregate Condition Comparison

| Condition | Mean Steps | Mean Context Tokens | Mean Recall | Blast Recall / Prec / F1 | Surface Recall | Modeled Maint. Tokens (Impl / Minor Struct) |
|-----------|-----------:|--------------------:|------------:|-------------------------:|---------------:|--------------------------------------------:|
| A. `raw_grep` (No `ctx`) | 11.67 | 34625.7 | 0.7479 | 0.854 / 0.182 / 0.289 | 0.9229 | 0 / 0 |
| B. `tier1_manifests` (Per-dir `CONTEXT.md`) | 4.00 | 9119.0 | 0.6343 | 0.854 / 0.180 / 0.287 | 0.2289 | 8577 / 8577 |
| C. `tier2_plus_impact` (`CONTEXT-0.md` + `ctx impact`) | 2.00 | 3463.0 | 0.8735 | 1.000 / 1.000 / 1.000 | 1.0000 | 0 / 0 (+215 Jev T1) |

## Per-Repository Results

### `context-project` (160 files, 11 subsystems, 242 internal edges, 33 public surfaces)

- **Focal High-Fan-In Target:** `src/ctx/config.py` (14 direct prod dependents, 19 transitive prod dependents, 25 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 12 | 35024 | 0.4000 | 0.9394 | 0.737 / 0.275 / 0.400 | 0.640 / 0.889 / 0.744 | **0.6791** |
| `tier1_manifests` | 4 | 11081 | 0.9000 | 0.3636 | 0.737 / 0.269 / 0.394 | 0.640 / 0.727 / 0.681 | **0.6601** |
| `tier2_plus_impact` | 2 | 3974 | 0.8000 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.9500** |

### `project-ledger` (153 files, 12 subsystems, 214 internal edges, 32 public surfaces)

- **Focal High-Fan-In Target:** `ledger/identity.py` (11 direct prod dependents, 12 transitive prod dependents, 25 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 12 | 37482 | 0.4000 | 1.0000 | 0.917 / 0.186 / 0.310 | 0.840 / 0.700 / 0.764 | **0.7892** |
| `tier1_manifests` | 4 | 8143 | 0.8000 | 0.2500 | 0.917 / 0.186 / 0.310 | 0.840 / 0.700 / 0.764 | **0.7017** |
| `tier2_plus_impact` | 2 | 3471 | 0.5000 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.8750** |

### `machina` (600 files, 13 subsystems, 124 internal edges, 41 public surfaces)

- **Focal High-Fan-In Target:** `src/machina/runtime.py` (20 direct prod dependents, 22 transitive prod dependents, 8 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 11 | 31371 | 0.3636 | 0.8293 | 0.909 / 0.086 / 0.158 | 1.000 / 0.727 / 0.842 | **0.7755** |
| `tier1_manifests` | 4 | 8133 | 0.1818 | 0.0732 | 0.909 / 0.086 / 0.156 | 1.000 / 0.727 / 0.842 | **0.5410** |
| `tier2_plus_impact` | 2 | 2944 | 0.1818 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.7955** |

