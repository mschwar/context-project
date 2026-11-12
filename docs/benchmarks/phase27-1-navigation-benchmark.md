# Phase 27.1 — Deterministic Static-Oracle Navigation & Blast-Radius Benchmark

- **Generated:** `2026-11-01T05:33:15Z`
- **Generator:** `ctx/1.1.0` (`phase-27.1-v3-static-oracle-f1`)
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

- **88.2% context-token reduction** vs `raw_grep` (`3517.7` vs `29836.7` mean tokens)
- **82.9% retrieval-step reduction** vs `raw_grep` (`2.0` vs `11.67` mean steps)
- **+12.4 percentage points static-oracle mean recall delta** (`0.8735` vs `0.7498`) and **+16.6 percentage points blast-radius F1 delta** (`1.0000` vs `0.8341`)
- **0 modeled Type-II LLM maintenance tokens** on implementation-only commits (`should_invoke_llm() == False`) and non-material structural tweaks gated by Type 1 Jev (`invariant_drift_material`, ~215 modeled System-One input tokens @ `$0.042/1M`)

## Aggregate Condition Comparison

| Condition | Mean Steps | Mean Context Tokens | Mean Recall | Blast Recall / Prec / F1 | Surface Recall | Modeled Maint. Tokens (Impl / Minor Struct) |
|-----------|-----------:|--------------------:|------------:|-------------------------:|---------------:|--------------------------------------------:|
| A. `raw_grep` (No `ctx`) | 11.67 | 29836.7 | 0.7498 | 0.857 / 0.826 / 0.834 | 0.9279 | 0 / 0 |
| B. `tier1_manifests` (Per-dir `CONTEXT.md`) | 4.00 | 4371.3 | 0.6344 | 0.857 / 0.826 / 0.834 | 0.2268 | 8596 / 8596 |
| C. `tier2_plus_impact` (`CONTEXT-0.md` + `ctx impact`) | 2.00 | 3517.7 | 0.8735 | 1.000 / 1.000 / 1.000 | 1.0000 | 0 / 0 (+215 Jev T1) |

## Per-Repository Results

### `context-project` (160 files, 11 subsystems, 242 internal edges, 33 public surfaces)

- **Focal High-Fan-In Target:** `src/ctx/config.py` (14 direct prod dependents, 19 transitive prod dependents, 25 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 12 | 30870 | 0.4000 | 0.9394 | 0.737 / 0.875 / 0.800 | 0.640 / 0.889 / 0.744 | **0.6791** |
| `tier1_manifests` | 4 | 6625 | 0.9000 | 0.3636 | 0.737 / 0.875 / 0.800 | 0.640 / 0.727 / 0.681 | **0.6601** |
| `tier2_plus_impact` | 2 | 3974 | 0.8000 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.9500** |

### `project-ledger` (155 files, 12 subsystems, 214 internal edges, 32 public surfaces)

- **Focal High-Fan-In Target:** `ledger/identity.py` (11 direct prod dependents, 12 transitive prod dependents, 25 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 12 | 33179 | 0.4000 | 1.0000 | 0.917 / 0.688 / 0.786 | 0.840 / 0.955 / 0.894 | **0.7892** |
| `tier1_manifests` | 4 | 3934 | 0.8000 | 0.2500 | 0.917 / 0.688 / 0.786 | 0.840 / 0.955 / 0.894 | **0.7017** |
| `tier2_plus_impact` | 2 | 3471 | 0.5000 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.8750** |

### `machina` (609 files, 13 subsystems, 138 internal edges, 45 public surfaces)

- **Focal High-Fan-In Target:** `src/machina/runtime.py` (22 direct prod dependents, 24 transitive prod dependents, 9 coupled test suites)

| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|
| `raw_grep` | 11 | 25461 | 0.3636 | 0.8444 | 0.917 / 0.917 / 0.917 | 1.000 / 1.000 / 1.000 | **0.7812** |
| `tier1_manifests` | 4 | 2555 | 0.1818 | 0.0667 | 0.917 / 0.917 / 0.917 | 1.000 / 1.000 / 1.000 | **0.5413** |
| `tier2_plus_impact` | 2 | 3108 | 0.1818 | 1.0000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | **0.7955** |

