# Phase 27.1 — Deterministic Static-Oracle Navigation & Blast-Radius Benchmark

- **Generated:** `2026-11-14T10:10:43Z`
- **Generator:** `ctx/2.0.0` (`phase-27.1-v3-static-oracle-f1`)
- **Methodology:** `deterministic_static_oracle_retrieval`
- **Maintenance Cost Basis:** `modeled_analytical_estimate`
- **Repositories Evaluated:** 3
- **Reproduce:** `ctx benchmark <repo1> [repo2 ...] --out-file docs/benchmarks/phase27-1-navigation-benchmark.md`

## Methodology & Scope

This benchmark deterministically evaluates retrieval context-token efficiency, recall, precision, and F1 across three scripted retrieval workflows (`raw_grep`, `tier1_manifests`, and `tier2_plus_impact`) against a separate static Abstract Syntax Tree (AST) and filesystem reference oracle built directly from raw files on disk:

- **Condition A (`raw_grep`):** Lists the file tree, reads root docs (`README.md`, `AGENTS.md`, `CLAUDE.md`) plus up to 2 architecture/governance docs discovered in the file tree, reads candidate entrypoints and the focal module, and runs line-by-line regex grep (`\b<stem>\b`) over production and test files.
- **Condition B (`tier1_manifests`):** Reads depth-0/1 `CONTEXT.md` manifests (`ctx export --depth 1`), reads the primary entrypoint, and runs symbol-augmented regex grep (`\b(?:<stem>|<exported_symbols>)\b`).
- **Condition C (`tier2_plus_impact`):** Reads `.ctx/CONTEXT-0.md` and `ctx impact <focal_target> --output json`.

**Scope Disclosures:** Both the reference oracle and `ctx.impact` evaluate static import graphs rather than dynamic runtime dispatch. Per-commit maintenance token figures in the rightmost column are **modeled analytical estimates** rather than live billing logs.

## Executive Summary

Across **3** repositories and **4** static-oracle retrieval dimensions (Authority & Architecture Orientation, Public Operational Surface Discovery, Multi-Hop Blast-Radius Tracing, and Coupled Test Selection), **Condition C (`tier2_plus_impact`: `.ctx/CONTEXT-0.md` + `ctx impact`)** achieves:

- **87.9% context-token reduction** vs `raw_grep` (`3217.3` vs `26509.7` mean tokens)
- **84.2% retrieval-step reduction** vs `raw_grep` (`2.0` vs `12.67` mean steps)
- **+17.0 percentage points static-oracle mean recall delta** (`0.9052` vs `0.7354`) and **+26.7 percentage points blast-radius F1 delta** (`1.0000` vs `0.7327`)
- **0 LLM maintenance tokens** across both implementation-only commits and structural commits (100% deterministic local AST & import-graph extraction)

## Aggregate Condition Comparison

| Condition | Mean Steps | Mean Context Tokens | Mean Recall | Blast Recall / Prec / F1 | Surface Recall | Modeled Maint. Tokens (Impl / Minor Struct) |
|-----------|-----------:|--------------------:|------------:|-------------------------:|---------------:|--------------------------------------------:|
| A. `raw_grep` (No `ctx`) | 12.67 | 26509.7 | 0.7354 | 0.734 / 0.763 / 0.733 | 0.9493 | 0 / 0 |
| B. `tier1_manifests` (Per-dir `CONTEXT.md`) | 4.00 | 3074.7 | 0.5854 | 0.734 / 0.763 / 0.733 | 0.1750 | 6311 / 6311 |
| C. `tier2_plus_impact` (`CONTEXT-0.md` + `ctx impact`) | 2.00 | 3217.3 | 0.9052 | 1.000 / 1.000 / 1.000 | 1.0000 | 0 / 0 |

## Per-Repository Results

### `context-project` (136 files, 8 subsystems, 111 internal edges, 23 public surfaces)

- **Focal High-Fan-In Target:** `src/ctx/__init__.py` (6 direct prod dependents, 10 transitive prod dependents, 14 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 13 | 20357 | 0.5556 | 1.0000 | 0.400 / 0.667 / 0.500 | 0.357 / 0.714 / 0.476 | **0.5782** |
| `tier1_manifests` | 4 | 2349 | 1.0000 | 0.2174 | 0.400 / 0.667 / 0.500 | 0.357 / 0.833 / 0.500 | **0.4936** |
| `tier2_plus_impact` | 2 | 2515 | 0.8889 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.9722** |

### `project-ledger` (133 files, 10 subsystems, 244 internal edges, 33 public surfaces)

- **Focal High-Fan-In Target:** `ledger/identity.py` (12 direct prod dependents, 13 transitive prod dependents, 26 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 13 | 34314 | 0.4545 | 1.0000 | 0.923 / 0.706 / 0.800 | 0.846 / 0.957 / 0.898 | **0.8059** |
| `tier1_manifests` | 4 | 4174 | 0.8182 | 0.2424 | 0.923 / 0.706 / 0.800 | 0.846 / 0.957 / 0.898 | **0.7075** |
| `tier2_plus_impact` | 2 | 3675 | 0.5455 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.8864** |

### `machina` (509 files, 13 subsystems, 168 internal edges, 46 public surfaces)

- **Focal High-Fan-In Target:** `src/machina/runtime.py` (22 direct prod dependents, 25 transitive prod dependents, 13 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 12 | 24858 | 0.7143 | 0.8478 | 0.880 / 0.917 / 0.898 | 0.846 / 1.000 / 0.917 | **0.8221** |
| `tier1_manifests` | 4 | 2701 | 0.4286 | 0.0652 | 0.880 / 0.917 / 0.898 | 0.846 / 1.000 / 0.917 | **0.5550** |
| `tier2_plus_impact` | 2 | 3462 | 0.4286 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.8571** |

