# Phase 27.1 — Empirical A/B/C Agent Navigation & Blast-Radius Benchmark

- **Generated:** `2026-11-01T03:20:18Z`
- **Generator:** `ctx/1.1.0` (`phase-27.1-v1`)
- **Repositories Evaluated:** 3
- **Reproduce:** `ctx benchmark <repo1> [repo2 ...] --out-file docs/benchmarks/phase27-1-navigation-benchmark.md`

## Executive Summary

Across **3** repositories and **4** ground-truth codebase tasks (Authority & Architecture Orientation, Operational Surface Discovery, Transitive Blast-Radius Tracing, and Coupled Test Selection), **Condition C (`tier2_plus_impact`: `.ctx/CONTEXT-0.md` + `ctx impact`)** achieves:

- **86.1% fewer context tokens ingested** vs `raw_grep` (`3443.0` vs `24762.7` mean tokens)
- **77.8% fewer tool turns** vs `raw_grep` (`2.0` vs `9.0` mean turns)
- **+24.7 percentage points higher ground-truth recall** (`0.9519` vs `0.7049`), driven by multi-hop transitive reverse-dependency & operational surface extraction
- **0 Type-II LLM maintenance tokens** on implementation-only commits (`should_invoke_llm() == False`) and non-material structural tweaks gated by Type 1 Jev (`invariant_drift_material`, ~180 System-One input tokens @ `$0.042/1M` = `$0.000008`)

## Aggregate Condition Comparison

| Condition | Mean Tool Turns | Mean Context Tokens | Mean Overall Recall | Blast-Radius Recall | Surface Recall | Maint. Type-II LLM Tokens (Impl / Minor Struct) |
|-----------|----------------:|--------------------:|--------------------:|--------------------:|---------------:|------------------------------------------------:|
| A. `raw_grep` (No `ctx`) | 9.00 | 24762.7 | 0.7049 | 0.8542 | 0.7252 | 0 / 0 |
| B. `tier1_manifests` (Per-dir `CONTEXT.md`) | 7.00 | 5500.0 | 0.6811 | 0.8542 | 0.2302 | 1800 / 1800 |
| C. `tier2_plus_impact` (`CONTEXT-0.md` + `ctx impact`) | 2.00 | 3443.0 | 0.9519 | 1.0000 | 0.8079 | 0 / 0 (+180 Jev T1) |

## Per-Repository Results

### `context-project` (159 files, 11 subsystems, 239 internal edges, 70 surfaces)

- **Focal High-Fan-In Target:** `src/ctx/config.py` (14 direct prod dependents, 19 transitive prod dependents, 25 coupled test suites)

| Condition | Turns | Context Tokens | Arch Recall | Surface Recall | Blast-Radius Recall | Coupled-Test Recall | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|--------------------:|--------------------:|------------:|
| `raw_grep` | 10 | 29386 | 0.2000 | 0.9211 | 0.7368 | 0.5200 | **0.5945** |
| `tier1_manifests` | 7 | 5093 | 0.8000 | 0.0000 | 0.7368 | 0.5200 | **0.5142** |
| `tier2_plus_impact` | 2 | 3962 | 1.0000 | 0.9474 | 1.0000 | 1.0000 | **0.9868** |

### `project-ledger` (152 files, 12 subsystems, 214 internal edges, 36 surfaces)

- **Focal High-Fan-In Target:** `ledger/identity.py` (11 direct prod dependents, 12 transitive prod dependents, 25 coupled test suites)

| Condition | Turns | Context Tokens | Arch Recall | Surface Recall | Blast-Radius Recall | Coupled-Test Recall | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|--------------------:|--------------------:|------------:|
| `raw_grep` | 9 | 24200 | 0.4000 | 0.9688 | 0.9167 | 0.6000 | **0.7214** |
| `tier1_manifests` | 7 | 5032 | 1.0000 | 0.5000 | 0.9167 | 0.6000 | **0.7542** |
| `tier2_plus_impact` | 2 | 3473 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **1.0000** |

### `machina` (592 files, 13 subsystems, 118 internal edges, 58 surfaces)

- **Focal High-Fan-In Target:** `src/machina/runtime.py` (20 direct prod dependents, 22 transitive prod dependents, 7 coupled test suites)

| Condition | Turns | Context Tokens | Arch Recall | Surface Recall | Blast-Radius Recall | Coupled-Test Recall | Mean Recall |
|-----------|------:|---------------:|------------:|---------------:|--------------------:|--------------------:|------------:|
| `raw_grep` | 8 | 20702 | 1.0000 | 0.2857 | 0.9091 | 1.0000 | **0.7987** |
| `tier1_manifests` | 7 | 6375 | 1.0000 | 0.1905 | 0.9091 | 1.0000 | **0.7749** |
| `tier2_plus_impact` | 2 | 2894 | 1.0000 | 0.4762 | 1.0000 | 1.0000 | **0.8690** |

