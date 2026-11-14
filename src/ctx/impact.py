"""Directed file & subsystem dependency graph and blast-radius analyzer for ctx.

Resolves multi-language internal imports into a directed dependency graph with:
- File-to-file and subsystem-to-subsystem inbound/outbound adjacency
- Tarjan strongly-connected component cycle detection
- Condensed DAG topological layer ordering (Layer 0 foundational leaves -> top orchestrators)
- Blast-radius impact queries (`analyze_impact`) for file, directory/subsystem, or symbol targets,
  returning direct/transitive dependents, coupled tests, affected entrypoints & operational surfaces,
  and governing authority/architecture documents with zero LLM calls.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from ctx.skeleton import (
    RepoSkeleton,
    _GO_MOD_MODULE_RE,
    _IDENT_TOKEN_RE,
    _NON_OPERATIONAL_DIRS,
    _strip_jsonc,
    _subsystem_key_for_rel_path,
    extract_skeleton,
    resolve_cli_entrypoint_target,
    resolve_config_target_path,
)

_RUST_MOD_DECL_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", re.MULTILINE)
_JS_PROBE_SUFFIXES = (
    "",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    "/index.ts",
    "/index.tsx",
    "/index.js",
    "/index.jsx",
)


@dataclass(frozen=True)
class DependencyGraph:
    """Directed internal dependency graph for a repository."""

    root: str
    outbound_files: dict[str, list[str]]
    inbound_files: dict[str, list[str]]
    outbound_subsystems: dict[str, list[str]]
    inbound_subsystems: dict[str, list[str]]
    cycles: list[list[str]]
    subsystem_cycles: list[list[str]]
    topological_layers: list[list[str]]
    file_layers: dict[str, int]
    internal_edge_count: int


@dataclass(frozen=True)
class ImpactResult:
    """Blast-radius impact report for a file, subsystem, or symbol target."""

    target: str
    target_kind: str  # "file" | "subsystem" | "symbol"
    matched_files: list[str]
    matched_symbols: list[str]
    direct_outbound_deps: list[str]
    direct_inbound_dependents: list[str]
    transitive_inbound_dependents: list[dict[str, Any]]
    coupled_tests: list[dict[str, Any]]
    affected_subsystems: list[str]
    affected_entrypoints: list[str]
    governing_docs: list[str]
    cycles_involving_target: list[list[str]]
    layer_index: int | None
    total_layers: int
    internal_edge_count: int
    repo_cycles_count: int = field(default=0)


@dataclass(frozen=True)
class DiffImpactResult:
    """Proportional-verification blast-radius report across a git diff or working tree."""

    diff_spec: str
    changed_files: list[str]
    matched_code_files: list[str]
    changed_test_files: list[str]
    changed_boundary_docs: list[str]
    changed_configs: list[str]
    direct_outbound_deps: list[str]
    direct_inbound_dependents: list[str]
    transitive_inbound_dependents: list[dict[str, Any]]
    coupled_tests: list[dict[str, Any]]
    affected_subsystems: list[str]
    affected_entrypoints: list[str]
    governing_docs: list[str]
    cycles_involving_changes: list[list[str]]
    verification_scope: str
    recommended_checks: list[str]
    escalation_reasons: list[str] = field(default_factory=list)


def is_test_file_path(rel_posix: str) -> bool:
    """Return True if *rel_posix* belongs to a test suite or test file naming convention."""
    p = Path(rel_posix)
    lower_parts = [seg.lower() for seg in p.parts[:-1]]
    if any(seg in {"tests", "test", "__tests__", "spec", "specs"} for seg in lower_parts):
        return True
    name = p.name.lower()
    return name.startswith("test_") or name.endswith(
        ("_test.py", "_test.go", "_test.rs", ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.js")
    )


def _load_tsconfig_aliases(root: Path) -> tuple[str, list[tuple[str, list[str]]]]:
    """Parse optional tsconfig.json / jsconfig.json baseUrl and paths aliases."""
    for name in ("tsconfig.json", "jsconfig.json"):
        cfg = root / name
        if not cfg.is_file():
            continue
        try:
            parsed = json.loads(_strip_jsonc(cfg.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        opts = parsed.get("compilerOptions")
        if not isinstance(opts, dict):
            continue
        base_url = str(opts.get("baseUrl") or ".").strip() or "."
        raw_paths = opts.get("paths")
        aliases: list[tuple[str, list[str]]] = []
        if isinstance(raw_paths, dict):
            for k, v in raw_paths.items():
                if not isinstance(k, str) or not isinstance(v, list):
                    continue
                targets = [str(item).strip() for item in v if isinstance(item, str) and str(item).strip()]
                if targets:
                    aliases.append((k.strip(), targets))
        return base_url, aliases
    return ".", []


def _load_go_module_name(root: Path) -> str:
    go_mod = root / "go.mod"
    if not go_mod.is_file():
        return ""
    try:
        m = _GO_MOD_MODULE_RE.search(go_mod.read_text(encoding="utf-8"))
        return m.group(1).strip() if m else ""
    except (OSError, UnicodeDecodeError):
        return ""


def _build_python_module_map(all_files: set[str]) -> dict[str, str]:
    """Map dotted Python module names to repo-relative file paths (including src/ and monorepo workspaces)."""
    mod_map: dict[str, str] = {}
    pkg_init_dirs: set[tuple[str, ...]] = set()
    for rel in sorted(all_files):
        if rel.endswith("/__init__.py"):
            pkg_init_dirs.add(tuple(rel.split("/")[:-1]))

    for rel in sorted(all_files):
        if not rel.endswith(".py"):
            continue
        no_ext = rel[:-3]
        parts = no_ext.split("/")
        is_init = parts[-1] == "__init__"
        target_parts = parts[:-1] if is_init else parts
        if not target_parts:
            continue
        mod_map.setdefault(".".join(target_parts), rel)
        if "src" in target_parts:
            src_idx = target_parts.index("src")
            if src_idx + 1 < len(target_parts):
                mod_map.setdefault(".".join(target_parts[src_idx + 1 :]), rel)
        # Support flat monorepo packages like packages/core/core_pkg/__init__.py -> core_pkg
        for idx in range(1, len(target_parts) if not is_init else len(target_parts)):
            if tuple(target_parts[: idx + 1]) in pkg_init_dirs and tuple(target_parts[:idx]) not in pkg_init_dirs:
                mod_map.setdefault(".".join(target_parts[idx:]), rel)
    return mod_map


def _load_js_workspace_packages(root: Path, all_files: set[str]) -> dict[str, str]:
    """Map monorepo JS/TS workspace package names (e.g. '@acme/core') to their package directory."""
    pkg_dirs: dict[str, str] = {}
    for rel in sorted(all_files):
        if Path(rel).name != "package.json" or "/" not in rel:
            continue
        pkg_path = root / rel
        try:
            parsed = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            name = str(parsed.get("name") or "").strip()
            if name:
                pkg_dirs.setdefault(name, Path(rel).parent.as_posix())
    return pkg_dirs


def _load_cargo_crate_roots(root: Path, all_files: set[str]) -> dict[str, str]:
    """Map Rust crate names (normalized '-' -> '_') across root and workspace Cargo.toml files to src dirs."""
    crates: dict[str, str] = {}
    candidates = {"Cargo.toml"} | {rel for rel in all_files if Path(rel).name == "Cargo.toml"}
    for rel in sorted(candidates):
        cargo_path = root / rel
        if not cargo_path.is_file():
            continue
        try:
            m = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', cargo_path.read_text(encoding="utf-8"), re.MULTILINE)
        except (OSError, UnicodeDecodeError):
            continue
        if not m:
            continue
        crate_name = m.group(1).strip().replace("-", "_")
        if not crate_name:
            continue
        parent = Path(rel).parent.as_posix()
        src_dir = "src" if parent == "." else f"{parent}/src"
        crates.setdefault(crate_name, src_dir)
    return crates


def _resolve_python_file_edges(
    root: Path,
    rel_posix: str,
    fallback_imports: list[str],
    py_mod_map: dict[str, str],
) -> set[str]:
    """Resolve Python AST `import` and `from ... import ...` statements to exact internal `.py` files."""
    targets: set[str] = set()
    rel_parts = list(Path(rel_posix).parts)
    is_pkg_init = rel_parts[-1] == "__init__.py"
    cur_dir_parts = rel_parts[:-1]
    if cur_dir_parts and cur_dir_parts[0] == "src":
        cur_pkg_parts = cur_dir_parts[1:]
    else:
        cur_pkg_parts = cur_dir_parts

    def _add_dotted(dotted: str) -> bool:
        cleaned = dotted.strip(".")
        if not cleaned:
            return False
        hit = py_mod_map.get(cleaned)
        if hit and hit != rel_posix:
            targets.add(hit)
            return True
        # Walk parent packages if importing a symbol from a module path
        segs = cleaned.split(".")
        for cut in range(len(segs) - 1, 0, -1):
            sub_hit = py_mod_map.get(".".join(segs[:cut]))
            if sub_hit and sub_hit != rel_posix:
                targets.add(sub_hit)
                return True
        return False

    abs_path = root / rel_posix
    parsed_ast = False
    try:
        tree = ast.parse(abs_path.read_text(encoding="utf-8"))
        parsed_ast = True
    except (OSError, UnicodeDecodeError, SyntaxError):
        tree = None

    if parsed_ast and tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name:
                        _add_dotted(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base_parts: list[str] = []
                if node.level > 0:
                    up = node.level - 1
                    anchor = cur_pkg_parts
                    if up <= len(anchor):
                        base_parts = anchor[: len(anchor) - up]
                    else:
                        continue
                    if node.module:
                        base_parts = [*base_parts, *node.module.split(".")]
                elif node.module:
                    base_parts = node.module.split(".")

                matched_any_member = False
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        cand_mod = ".".join([*base_parts, alias.name])
                        if cand_mod in py_mod_map and py_mod_map[cand_mod] != rel_posix:
                            targets.add(py_mod_map[cand_mod])
                            matched_any_member = True
                if base_parts:
                    base_mod = ".".join(base_parts)
                    # Always link the base module if no submodule matched, or if `__init__.py` exists alongside
                    if not matched_any_member or base_mod in py_mod_map:
                        _add_dotted(base_mod)
        return targets

    for imp in fallback_imports:
        if not imp.startswith("."):
            _add_dotted(imp)
    return targets


def _probe_js_ts_candidate(candidate_rel: str, all_files: set[str]) -> str | None:
    norm = Path(candidate_rel).as_posix()
    while norm.startswith("./"):
        norm = norm[2:]
    norm = norm.lstrip("/")
    bases = [norm]
    for ext in (".js", ".jsx", ".mjs", ".cjs"):
        if norm.endswith(ext):
            bases.append(norm[: -len(ext)])
    for b in bases:
        for suffix in _JS_PROBE_SUFFIXES:
            probed = f"{b}{suffix}" if suffix else b
            if probed in all_files:
                return probed
    return None


def _resolve_js_ts_edges(
    root: Path,
    rel_posix: str,
    imports: list[str],
    all_files: set[str],
    ts_base_url: str,
    ts_aliases: list[tuple[str, list[str]]],
    js_workspaces: dict[str, str] | None = None,
) -> set[str]:
    targets: set[str] = set()
    cur_dir = (root / rel_posix).parent
    resolved_root = root.resolve()
    ws_map = js_workspaces or {}

    for imp in imports:
        if not imp:
            continue
        if imp.startswith("."):
            try:
                cand_abs = (cur_dir / imp).resolve()
                if cand_abs.is_relative_to(resolved_root):
                    rel_cand = cand_abs.relative_to(resolved_root).as_posix()
                    hit = _probe_js_ts_candidate(rel_cand, all_files)
                    if hit and hit != rel_posix:
                        targets.add(hit)
                        continue
            except OSError:
                pass

        matched_alias = False
        for pattern, replacements in ts_aliases:
            if pattern.endswith("/*"):
                prefix = pattern[:-1]  # keeps trailing '/'
                if imp.startswith(prefix):
                    tail = imp[len(prefix) :]
                    for rep in replacements:
                        rep_base = rep[:-1] if rep.endswith("/*") else rep.rstrip("/") + "/"
                        cand_abs = (resolved_root / ts_base_url / f"{rep_base}{tail}").resolve()
                        if cand_abs.is_relative_to(resolved_root):
                            hit = _probe_js_ts_candidate(cand_abs.relative_to(resolved_root).as_posix(), all_files)
                            if hit and hit != rel_posix:
                                targets.add(hit)
                                matched_alias = True
            elif imp == pattern:
                for rep in replacements:
                    cand_abs = (resolved_root / ts_base_url / rep).resolve()
                    if cand_abs.is_relative_to(resolved_root):
                        hit = _probe_js_ts_candidate(cand_abs.relative_to(resolved_root).as_posix(), all_files)
                        if hit and hit != rel_posix:
                            targets.add(hit)
                            matched_alias = True
        if matched_alias:
            continue

        if imp.startswith(("@/", "~/")):
            tail = imp[2:]
            for base_prefix in ("src/", ""):
                hit = _probe_js_ts_candidate(f"{base_prefix}{tail}", all_files)
                if hit and hit != rel_posix:
                    targets.add(hit)
                    break
            continue

        for pkg_name, pkg_dir in ws_map.items():
            if imp == pkg_name:
                for entry_cand in (f"{pkg_dir}/src/index", f"{pkg_dir}/index"):
                    hit = _probe_js_ts_candidate(entry_cand, all_files)
                    if hit and hit != rel_posix:
                        targets.add(hit)
                        break
            elif imp.startswith(f"{pkg_name}/"):
                sub = imp[len(pkg_name) + 1 :]
                for cand_prefix in (f"{pkg_dir}/src/{sub}", f"{pkg_dir}/{sub}"):
                    hit = _probe_js_ts_candidate(cand_prefix, all_files)
                    if hit and hit != rel_posix:
                        targets.add(hit)
                        break

    return targets


def _resolve_go_edges(
    rel_posix: str,
    imports: list[str],
    go_module: str,
    go_pkg_files: dict[str, list[str]],
) -> set[str]:
    if not go_module:
        return set()
    targets: set[str] = set()
    for imp in imports:
        if imp == go_module:
            pkg_dir = "."
        elif imp.startswith(f"{go_module}/"):
            pkg_dir = imp[len(go_module) + 1 :]
        else:
            continue
        for fpath in go_pkg_files.get(pkg_dir, []):
            if fpath != rel_posix and not is_test_file_path(fpath):
                targets.add(fpath)
    return targets


def _resolve_rust_edges(
    root: Path,
    rel_posix: str,
    imports: list[str],
    all_files: set[str],
    crate_name: str,
    cargo_crates: dict[str, str] | None = None,
) -> set[str]:
    targets: set[str] = set()
    crate_map = cargo_crates or {}
    p = Path(rel_posix)
    cur_dir = p.parent.as_posix()
    if cur_dir == ".":
        cur_dir = ""
    parts = p.parts
    if "src" in parts[:-1]:
        src_idx = len(parts) - 2 - list(reversed(parts[:-1])).index("src")
        crate_src_dir = "/".join(parts[: src_idx + 1])
    else:
        crate_src_dir = "src"

    def _probe_rs(mod_segs: list[str], base_dir: str = "src") -> bool:
        for cut in range(len(mod_segs), 0, -1):
            joined = "/".join(mod_segs[:cut])
            prefix = f"{base_dir}/{joined}" if base_dir else joined
            for cand in (f"{prefix}.rs", f"{prefix}/mod.rs"):
                if cand in all_files and cand != rel_posix:
                    targets.add(cand)
                    return True
        return False

    for imp in imports:
        segs = [s for s in imp.split("::") if s and s != "*"]
        if not segs:
            continue
        head = segs[0]
        if head in ("crate", crate_name) and len(segs) >= 2:
            if not _probe_rs(segs[1:], crate_src_dir) and crate_src_dir != "src":
                _probe_rs(segs[1:], "src")
        elif head in crate_map:
            ws_src = crate_map[head]
            if len(segs) >= 2 and _probe_rs(segs[1:], ws_src):
                pass
            else:
                lib_cand = f"{ws_src}/lib.rs"
                if lib_cand in all_files and lib_cand != rel_posix:
                    targets.add(lib_cand)
        elif head == "self" and len(segs) >= 2:
            base = cur_dir if p.name in ("lib.rs", "main.rs", "mod.rs") else f"{cur_dir}/{p.stem}".strip("/")
            _probe_rs(segs[1:], base)
        elif head == "super" and len(segs) >= 2:
            own_mod_dir = (
                cur_dir
                if p.name in ("lib.rs", "main.rs", "mod.rs")
                else f"{cur_dir}/{p.stem}".strip("/")
            )
            super_count = 0
            while super_count < len(segs) and segs[super_count] == "super":
                super_count += 1
            rem = segs[super_count:]
            if rem:
                mod_parts = [part for part in own_mod_dir.split("/") if part]
                if super_count <= len(mod_parts):
                    parent_dir = "/".join(mod_parts[: len(mod_parts) - super_count])
                    _probe_rs(rem, parent_dir)

    try:
        content = (root / rel_posix).read_text(encoding="utf-8")
        base = cur_dir if p.name in ("lib.rs", "main.rs", "mod.rs") else f"{cur_dir}/{p.stem}".strip("/")
        for m in _RUST_MOD_DECL_RE.finditer(content):
            _probe_rs([m.group(1)], base)
    except (OSError, UnicodeDecodeError):
        pass

    return targets


def _resolve_other_lang_edges(
    root: Path,
    rel_posix: str,
    language: str | None,
    imports: list[str],
    all_files: set[str],
    lower_file_lookup: dict[str, str],
) -> set[str]:
    targets: set[str] = set()
    resolved_root = root.resolve()
    cur_dir = (resolved_root / rel_posix).parent

    for imp in imports:
        if not imp:
            continue
        if language == "Ruby":
            if imp.startswith("."):
                try:
                    cand = (cur_dir / imp).resolve()
                    if cand.is_relative_to(resolved_root):
                        rel = cand.relative_to(resolved_root).as_posix()
                        for probe in (rel, f"{rel}.rb"):
                            if probe in all_files and probe != rel_posix:
                                targets.add(probe)
                except OSError:
                    pass
            else:
                for probe in (f"lib/{imp}.rb", f"{imp}.rb"):
                    if probe in all_files and probe != rel_posix:
                        targets.add(probe)
        elif language in ("Java", "Kotlin"):
            mod_path = imp.rstrip(".*").replace(".", "/")
            exts = (".java",) if language == "Java" else (".kt", ".kts")
            for f in all_files:
                if f != rel_posix and any(f.endswith(f"{mod_path}{ext}") for ext in exts):
                    targets.add(f)
        elif language == "PHP":
            norm_ns = imp.replace("\\", "/").lower().lstrip("/") + ".php"
            for lower_rel, orig_rel in lower_file_lookup.items():
                if orig_rel != rel_posix and (lower_rel == norm_ns or lower_rel.endswith(f"/{norm_ns.split('/', 1)[-1]}")):
                    if lower_rel.endswith(norm_ns) or (len(norm_ns.split("/")) >= 2 and lower_rel.endswith("/".join(norm_ns.split("/")[1:]))):
                        targets.add(orig_rel)
        elif language == "Elixir":
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", imp.replace(".", "/")).lower().replace("/_", "/")
            for lower_rel, orig_rel in lower_file_lookup.items():
                if orig_rel != rel_posix and lower_rel.endswith(f"{snake}.ex"):
                    targets.add(orig_rel)
        elif language in ("C", "C++", "C/C++ Header", "C++ Header"):
            clean_hdr = imp.replace("\\", "/")
            if clean_hdr.startswith("."):
                try:
                    cand = (cur_dir / clean_hdr).resolve()
                    if cand.is_relative_to(resolved_root):
                        rel_cand = cand.relative_to(resolved_root).as_posix()
                        if rel_cand in all_files and rel_cand != rel_posix:
                            targets.add(rel_cand)
                            continue
                except OSError:
                    pass
                clean_hdr = clean_hdr.lstrip("./")
            for prefix in ("", "include/", "src/"):
                probed = f"{prefix}{clean_hdr}"
                if probed in all_files and probed != rel_posix:
                    targets.add(probed)
                    break
            else:
                suffix = f"/{clean_hdr}"
                matches = [f for f in all_files if f != rel_posix and f.endswith(suffix)]
                if len(matches) == 1:
                    targets.add(matches[0])

    return targets


def _tarjan_cycles(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Return canonicalized strongly-connected cycles (size >= 2) using an iterative DFS stack."""
    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    scc_stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []

    for root_node in sorted(adjacency.keys()):
        if root_node in indices:
            continue
        indices[root_node] = index_counter
        lowlink[root_node] = index_counter
        index_counter += 1
        scc_stack.append(root_node)
        on_stack.add(root_node)
        call_stack: list[tuple[str, list[str], int]] = [
            (root_node, list(adjacency.get(root_node, [])), 0)
        ]

        while call_stack:
            node, succs, idx = call_stack[-1]
            if idx < len(succs):
                succ = succs[idx]
                call_stack[-1] = (node, succs, idx + 1)
                if succ not in indices:
                    indices[succ] = index_counter
                    lowlink[succ] = index_counter
                    index_counter += 1
                    scc_stack.append(succ)
                    on_stack.add(succ)
                    call_stack.append((succ, list(adjacency.get(succ, [])), 0))
                elif succ in on_stack:
                    if indices[succ] < lowlink[node]:
                        lowlink[node] = indices[succ]
            else:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    if lowlink[node] < lowlink[parent]:
                        lowlink[parent] = lowlink[node]
                if lowlink[node] == indices[node]:
                    scc: list[str] = []
                    while True:
                        w = scc_stack.pop()
                        on_stack.remove(w)
                        scc.append(w)
                        if w == node:
                            break
                    if len(scc) > 1:
                        cycles.append(sorted(scc))

    cycles.sort()
    return cycles


def _compute_topological_layers(adjacency: dict[str, list[str]]) -> tuple[list[list[str]], dict[str, int]]:
    """Compute condensed DAG topological layers iteratively where Layer 0 has 0 internal outbound deps."""
    nodes = sorted(adjacency.keys())
    if not nodes:
        return [], {}

    # Map nodes in multi-node SCCs to shared component IDs so cycles don't block layering
    cycles = _tarjan_cycles(adjacency)
    node_to_comp: dict[str, int] = {}
    comp_members: dict[int, list[str]] = {}
    next_comp = 0
    for cyc in cycles:
        cid = next_comp
        next_comp += 1
        comp_members[cid] = cyc
        for n in cyc:
            node_to_comp[n] = cid
    for n in nodes:
        if n not in node_to_comp:
            cid = next_comp
            next_comp += 1
            node_to_comp[n] = cid
            comp_members[cid] = [n]

    comp_out: dict[int, set[int]] = {cid: set() for cid in comp_members}
    comp_rev: dict[int, list[int]] = {cid: [] for cid in comp_members}
    for n, deps in adjacency.items():
        cn = node_to_comp[n]
        for d in deps:
            if d in node_to_comp:
                cd = node_to_comp[d]
                if cd != cn and cd not in comp_out[cn]:
                    comp_out[cn].add(cd)
                    comp_rev[cd].append(cn)

    rem_out: dict[int, int] = {cid: len(deps) for cid, deps in comp_out.items()}
    comp_layer: dict[int, int] = {}
    ready: deque[int] = deque()
    for cid, count in rem_out.items():
        if count == 0:
            comp_layer[cid] = 0
            ready.append(cid)

    while ready:
        cd = ready.popleft()
        base_lvl = comp_layer[cd]
        for cn in comp_rev[cd]:
            cand_lvl = base_lvl + 1
            if cand_lvl > comp_layer.get(cn, 0):
                comp_layer[cn] = cand_lvl
            rem_out[cn] -= 1
            if rem_out[cn] == 0:
                ready.append(cn)

    max_lvl = 0
    file_layers: dict[str, int] = {}
    for cid, members in comp_members.items():
        lvl = comp_layer.get(cid, 0)
        if lvl > max_lvl:
            max_lvl = lvl
        for m in members:
            file_layers[m] = lvl

    layers: list[list[str]] = [[] for _ in range(max_lvl + 1)]
    for n in nodes:
        layers[file_layers[n]].append(n)
    for bucket in layers:
        bucket.sort()
    return layers, file_layers


def build_dependency_graph(root: Path, skeleton: RepoSkeleton | None = None) -> DependencyGraph:
    """Build a directed internal file-to-file and subsystem-to-subsystem dependency graph."""
    resolved_root = root.resolve()
    sk = skeleton if skeleton is not None else extract_skeleton(resolved_root)

    all_files = {f.relative_path for f in sk.files}
    lower_lookup = {rel.lower(): rel for rel in all_files}
    py_mod_map = _build_python_module_map(all_files)
    ts_base_url, ts_aliases = _load_tsconfig_aliases(resolved_root)
    js_workspaces = _load_js_workspace_packages(resolved_root, all_files)
    go_module = _load_go_module_name(resolved_root)
    cargo_crates = _load_cargo_crate_roots(resolved_root, all_files)

    go_pkg_files: dict[str, list[str]] = {}
    for f in sk.files:
        if f.language == "Go":
            parent = Path(f.relative_path).parent.as_posix()
            go_pkg_files.setdefault(parent, []).append(f.relative_path)

    crate_name = ""
    cargo_toml = resolved_root / "Cargo.toml"
    if cargo_toml.is_file():
        try:
            m = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', cargo_toml.read_text(encoding="utf-8"), re.MULTILINE)
            if m:
                crate_name = m.group(1).strip().replace("-", "_")
        except (OSError, UnicodeDecodeError):
            pass

    outbound_files: dict[str, list[str]] = {f.relative_path: [] for f in sk.files}
    inbound_sets: dict[str, set[str]] = {f.relative_path: set() for f in sk.files}
    edge_count = 0

    for f in sk.files:
        lang = f.language
        if lang is None:
            continue
        if lang == "Python":
            resolved = _resolve_python_file_edges(resolved_root, f.relative_path, f.imports, py_mod_map)
        elif lang in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
            resolved = _resolve_js_ts_edges(
                resolved_root, f.relative_path, f.imports, all_files, ts_base_url, ts_aliases, js_workspaces
            )
        elif lang == "Go":
            resolved = _resolve_go_edges(f.relative_path, f.imports, go_module, go_pkg_files)
        elif lang == "Rust":
            resolved = _resolve_rust_edges(
                resolved_root, f.relative_path, f.imports, all_files, crate_name, cargo_crates
            )
        else:
            resolved = _resolve_other_lang_edges(
                resolved_root, f.relative_path, lang, f.imports, all_files, lower_lookup
            )

        ordered = sorted(t for t in resolved if t in all_files and t != f.relative_path)
        outbound_files[f.relative_path] = ordered
        edge_count += len(ordered)
        for target_rel in ordered:
            inbound_sets[target_rel].add(f.relative_path)

    inbound_files = {rel: sorted(srcs) for rel, srcs in inbound_sets.items()}

    # Subsystem-level graph
    sub_out_sets: dict[str, set[str]] = {s.path: set() for s in sk.subsystems}
    sub_in_sets: dict[str, set[str]] = {s.path: set() for s in sk.subsystems}
    for src_file, dst_files in outbound_files.items():
        src_sub = _subsystem_key_for_rel_path(src_file)
        sub_out_sets.setdefault(src_sub, set())
        sub_in_sets.setdefault(src_sub, set())
        for dst_file in dst_files:
            dst_sub = _subsystem_key_for_rel_path(dst_file)
            sub_out_sets.setdefault(dst_sub, set())
            sub_in_sets.setdefault(dst_sub, set())
            if src_sub != dst_sub:
                sub_out_sets[src_sub].add(dst_sub)
                sub_in_sets[dst_sub].add(src_sub)

    outbound_subsystems = {k: sorted(v) for k, v in sorted(sub_out_sets.items())}
    inbound_subsystems = {k: sorted(v) for k, v in sorted(sub_in_sets.items())}

    prod_outbound = {
        k: [d for d in v if not is_test_file_path(d)]
        for k, v in outbound_files.items()
        if not is_test_file_path(k) and sk.files
    }
    cycles = _tarjan_cycles(prod_outbound)
    prod_sub_outbound = {
        k: [d for d in v if k.lower() not in _NON_OPERATIONAL_DIRS and d.lower() not in _NON_OPERATIONAL_DIRS]
        for k, v in outbound_subsystems.items()
        if k.lower() not in _NON_OPERATIONAL_DIRS
    }
    subsystem_cycles = _tarjan_cycles(prod_sub_outbound)
    code_outbound = {
        f.relative_path: [d for d in outbound_files[f.relative_path] if not is_test_file_path(d)]
        for f in sk.files
        if f.language and f.language != "Markdown" and not is_test_file_path(f.relative_path)
    }
    topological_layers, file_layers = _compute_topological_layers(code_outbound)

    return DependencyGraph(
        root=str(resolved_root),
        outbound_files=outbound_files,
        inbound_files=inbound_files,
        outbound_subsystems=outbound_subsystems,
        inbound_subsystems=inbound_subsystems,
        cycles=cycles,
        subsystem_cycles=subsystem_cycles,
        topological_layers=topological_layers,
        file_layers=file_layers,
        internal_edge_count=edge_count,
    )


def _match_target(
    resolved_root: Path,
    target: str,
    sk: RepoSkeleton,
) -> tuple[str, list[str], list[str]]:
    """Resolve *target* as ('file' | 'subsystem' | 'symbol', matched_files, matched_symbols)."""
    raw = target.strip()
    if not raw:
        raise ValueError("Impact target must be a non-empty file path, directory, or symbol name.")

    all_files = {f.relative_path: f for f in sk.files}

    # Normalize potential filesystem path inside root
    norm_rel = raw.replace("\\", "/").strip("/")
    cand_path = Path(raw)
    if cand_path.is_absolute():
        try:
            resolved_cand = cand_path.resolve()
            if resolved_cand.is_relative_to(resolved_root):
                norm_rel = resolved_cand.relative_to(resolved_root).as_posix()
        except OSError:
            pass
    elif (resolved_root / raw).exists():
        try:
            resolved_cand = (resolved_root / raw).resolve()
            if resolved_cand.is_relative_to(resolved_root):
                norm_rel = resolved_cand.relative_to(resolved_root).as_posix()
        except OSError:
            pass

    if norm_rel in all_files:
        f = all_files[norm_rel]
        return "file", [norm_rel], [f"{norm_rel}:{s}" for s in f.symbols]

    # Subsystem or directory prefix match
    if norm_rel in ("", "."):
        return "subsystem", sorted(all_files.keys()), []
    dir_matches = sorted(
        rel for rel in all_files if rel.startswith(f"{norm_rel}/")
    )
    if dir_matches:
        return "subsystem", dir_matches, []

    # File suffix match (e.g. `lock.py` -> `src/ctx/lock.py`)
    suffix_matches = sorted(
        rel for rel in all_files if rel.endswith(f"/{norm_rel}") or Path(rel).name == norm_rel
    )
    if suffix_matches:
        non_test = [r for r in suffix_matches if not is_test_file_path(r)]
        chosen = non_test or suffix_matches
        syms = [f"{r}:{s}" for r in chosen for s in all_files[r].symbols]
        return "file", chosen, syms

    # Symbol match (`CtxLock`, `fn extract_skeleton`, `lock.py:class CtxLock`, `lock:CtxLock`)
    file_hint = ""
    sym_query = raw
    if ":" in raw and not raw.endswith(":"):
        left, right = raw.split(":", 1)
        if "." in left or "/" in left:
            file_hint = left.strip().replace("\\", "/")
            sym_query = right.strip()

    matched_files_set: set[str] = set()
    matched_symbols: list[str] = []
    for f in sk.files:
        if file_hint and not (f.relative_path == file_hint or f.relative_path.endswith(f"/{file_hint}") or Path(f.relative_path).name == file_hint):
            continue
        for sym in f.symbols:
            ident = sym.split(" ", 1)[1].strip() if " " in sym else sym.strip()
            if sym_query in (sym, ident):
                matched_files_set.add(f.relative_path)
                matched_symbols.append(f"{f.relative_path}:{sym}")

    if matched_files_set:
        non_test = sorted(r for r in matched_files_set if not is_test_file_path(r))
        chosen = non_test if (non_test and not file_hint) else sorted(matched_files_set)
        chosen_set = set(chosen)
        filtered_syms = [ms for ms in matched_symbols if ms.split(":", 1)[0] in chosen_set]
        return "symbol", chosen, filtered_syms

    raise ValueError(f"Target not found in repository skeleton: {target}")


def _resolve_entrypoint_files(resolved_root: Path, sk: RepoSkeleton) -> dict[str, set[str]]:
    """Map repo-relative file paths to `skeleton.entrypoints` entries anchored on that file."""
    file_to_eps: dict[str, set[str]] = {}
    for ep in sk.entrypoints:
        if ep.startswith("file:"):
            rel = ep[len("file:") :].strip()
            file_to_eps.setdefault(rel, set()).add(ep)
        elif ep.startswith("cli:") and "->" in ep:
            target = ep.split("->", 1)[1].strip()
            rel_cli = resolve_cli_entrypoint_target(resolved_root, target)
            if rel_cli:
                file_to_eps.setdefault(rel_cli, set()).add(ep)
        elif ep.startswith("npm:") and "->" in ep:
            target = ep.split("->", 1)[1].strip()
            p = resolve_config_target_path(resolved_root, target)
            if p is not None:
                rel_npm = p.relative_to(resolved_root).as_posix()
                file_to_eps.setdefault(rel_npm, set()).add(ep)
    return file_to_eps


def analyze_impact(
    root: Path,
    target: str,
    *,
    max_depth: int | None = None,
    skeleton: RepoSkeleton | None = None,
    graph: DependencyGraph | None = None,
) -> ImpactResult:
    """Compute reverse dependency blast radius, coupled tests, affected surfaces, and governing docs."""
    if max_depth is not None and max_depth < 1:
        raise ValueError("max_depth must be >= 1 when specified")

    resolved_root = root.resolve()
    sk = skeleton if skeleton is not None else extract_skeleton(resolved_root)
    dep_graph = graph if graph is not None else build_dependency_graph(resolved_root, skeleton=sk)

    target_kind, matched_files, matched_symbols = _match_target(resolved_root, target, sk)
    seed_set = set(matched_files)

    # Direct outbound dependencies
    direct_outbound = sorted({
        dep
        for src in matched_files
        for dep in dep_graph.outbound_files.get(src, [])
        if dep not in seed_set
    })

    # Reverse BFS over inbound_files
    visited_dist: dict[str, int] = {f: 0 for f in matched_files}
    visited_via: dict[str, str] = {}
    queue: deque[str] = deque(matched_files)

    while queue:
        curr = queue.popleft()
        curr_dist = visited_dist[curr]
        if max_depth is not None and curr_dist >= max_depth:
            continue
        for caller in dep_graph.inbound_files.get(curr, []):
            if caller not in visited_dist:
                visited_dist[caller] = curr_dist + 1
                visited_via[caller] = curr
                queue.append(caller)

    direct_inbound = sorted(
        f for f, d in visited_dist.items() if d == 1 and not is_test_file_path(f)
    )
    transitive_records: list[dict[str, Any]] = [
        {
            "path": f,
            "distance": d,
            "via": visited_via[f],
            "is_test": is_test_file_path(f),
        }
        for f, d in sorted(visited_dist.items(), key=lambda kv: (kv[1], kv[0]))
        if d >= 1
    ]

    # Coupled tests: import-coupled tests first, then naming-convention & symbol-mention tests
    coupled_map: dict[str, dict[str, Any]] = {}
    for rec in transitive_records:
        if rec["is_test"]:
            coupled_map[rec["path"]] = {
                "path": rec["path"],
                "distance": rec["distance"],
                "reason": "direct_import" if rec["distance"] == 1 else "transitive_import",
            }

    seed_stems = {
        Path(f).stem.lower()
        for f in matched_files
        if Path(f).stem.lower() not in {"__init__", "index", "mod", "main", "lib"}
    }
    queried_symbol_idents = {
        ms.split(":", 1)[1].split(" ", 1)[-1].strip()
        for ms in matched_symbols
        if ":" in ms
    }

    for f in sk.files:
        if not is_test_file_path(f.relative_path) or f.relative_path in coupled_map:
            continue
        tname = Path(f.relative_path).stem.lower()
        stripped_tname = (
            tname.removeprefix("test_")
            .removesuffix("_test")
            .removesuffix(".test")
            .removesuffix(".spec")
        )
        if stripped_tname in seed_stems or any(
            re.search(rf"(?:^|[_.-]){re.escape(st)}(?:$|[_.-])", stripped_tname) is not None
            for st in seed_stems
            if len(st) >= 3
        ):
            coupled_map[f.relative_path] = {
                "path": f.relative_path,
                "distance": None,
                "reason": "naming_convention",
            }
            continue
        if target_kind == "symbol" and queried_symbol_idents:
            try:
                idents = set(_IDENT_TOKEN_RE.findall((resolved_root / f.relative_path).read_text(encoding="utf-8")))
                if idents & queried_symbol_idents:
                    coupled_map[f.relative_path] = {
                        "path": f.relative_path,
                        "distance": None,
                        "reason": "symbol_reference",
                    }
            except (OSError, UnicodeDecodeError):
                pass

    reason_rank = {"direct_import": 0, "transitive_import": 1, "symbol_reference": 2, "naming_convention": 3}
    coupled_tests = sorted(
        coupled_map.values(),
        key=lambda item: (
            reason_rank.get(str(item["reason"]), 9),
            item["distance"] if isinstance(item["distance"], int) else 999,
            str(item["path"]),
        ),
    )

    affected_prod_files = {
        f for f in visited_dist if not is_test_file_path(f)
    }
    affected_subsystems = sorted({
        _subsystem_key_for_rel_path(f)
        for f in affected_prod_files
    })

    # Affected entrypoints & operational surfaces
    ep_by_file = _resolve_entrypoint_files(resolved_root, sk)
    affected_eps: set[str] = set()
    for fpath in affected_prod_files:
        affected_eps.update(ep_by_file.get(fpath, set()))
    for surf in sk.operational_surfaces:
        if surf.file in affected_prod_files and surf.kind in (
            "cli_command",
            "http_route",
            "mcp_tool",
            "mcp_resource",
        ):
            affected_eps.add(f"{surf.kind}:{surf.name} ({surf.file})")

    # Governing authority & architecture boundary documents
    governing_docs: list[str] = []
    seed_parents = {
        parent.as_posix()
        for f in matched_files
        for parent in [Path(f).parent, *Path(f).parents]
    }
    for doc in sk.boundary_docs:
        if doc.kind not in ("authority", "architecture"):
            continue
        doc_parent = Path(doc.relative_path).parent.as_posix()
        if (
            doc_parent == "."
            or doc.relative_path.lower().startswith(("docs/adr/", "adr/", "docs/designs/"))
            or doc_parent in seed_parents
        ):
            governing_docs.append(doc.relative_path)

    cycles_involving_target = [
        cyc for cyc in dep_graph.cycles if any(f in seed_set for f in cyc)
    ]

    seed_layers = [
        dep_graph.file_layers[f] for f in matched_files if f in dep_graph.file_layers
    ]
    layer_index = min(seed_layers) if seed_layers else None

    return ImpactResult(
        target=target,
        target_kind=target_kind,
        matched_files=matched_files,
        matched_symbols=matched_symbols,
        direct_outbound_deps=direct_outbound,
        direct_inbound_dependents=direct_inbound,
        transitive_inbound_dependents=transitive_records,
        coupled_tests=coupled_tests,
        affected_subsystems=affected_subsystems,
        affected_entrypoints=sorted(affected_eps),
        governing_docs=sorted(dict.fromkeys(governing_docs)),
        cycles_involving_target=cycles_involving_target,
        layer_index=layer_index,
        total_layers=len(dep_graph.topological_layers),
        internal_edge_count=dep_graph.internal_edge_count,
        repo_cycles_count=len(dep_graph.cycles),
    )


_SHARED_CONFIG_NAMES = frozenset({
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "tsconfig.json",
    "jsconfig.json",
    "cargo.toml",
    "go.mod",
    "conftest.py",
    ".ctxconfig",
    ".ctxignore",
})


def _is_shared_config_path(rel_posix: str) -> bool:
    lower = rel_posix.lower()
    name = Path(lower).name
    if name in _SHARED_CONFIG_NAMES:
        return True
    if lower.startswith((".github/workflows/", "ops/")):
        return True
    return False


def _collect_git_diff_files(
    resolved_root: Path,
    *,
    git_diff: str | None = None,
    staged: bool = False,
) -> tuple[str, list[str]]:
    """Collect changed repo-relative paths from git diff / staged index / working tree."""
    check_git = subprocess.run(
        ["git", "-C", str(resolved_root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if check_git.returncode != 0:
        raise ValueError(f"Not a git repository: {resolved_root}")
    git_top = Path(check_git.stdout.strip()).resolve()

    raw_paths: set[str] = set()
    if staged:
        spec_label = "--staged"
        proc = subprocess.run(
            ["git", "-C", str(git_top), "diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            raise ValueError(f"Git staged diff failed: {proc.stderr.strip()}")
        raw_paths.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    else:
        rev_spec = (git_diff or "WORKTREE").strip()
        if rev_spec.startswith("-"):
            raise ValueError(f"Invalid git diff revision spec: {rev_spec}")
        spec_label = rev_spec
        if rev_spec.upper() == "WORKTREE":
            head_diff = subprocess.run(
                ["git", "-C", str(git_top), "diff", "--name-only", "--diff-filter=ACMRD", "HEAD", "--"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if head_diff.returncode == 0:
                raw_paths.update(line.strip() for line in head_diff.stdout.splitlines() if line.strip())
            else:
                for extra_args in (["diff", "--name-only"], ["diff", "--cached", "--name-only"]):
                    p = subprocess.run(
                        ["git", "-C", str(git_top), *extra_args],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if p.returncode == 0:
                        raw_paths.update(line.strip() for line in p.stdout.splitlines() if line.strip())
            untracked = subprocess.run(
                ["git", "-C", str(git_top), "ls-files", "--others", "--exclude-standard"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if untracked.returncode == 0:
                raw_paths.update(line.strip() for line in untracked.stdout.splitlines() if line.strip())
        else:
            proc = subprocess.run(
                ["git", "-C", str(git_top), "diff", "--name-only", "--diff-filter=ACMRD", rev_spec, "--"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode != 0:
                raise ValueError(f"Git diff failed for '{rev_spec}': {proc.stderr.strip()}")
            raw_paths.update(line.strip() for line in proc.stdout.splitlines() if line.strip())

    scoped: list[str] = []
    for rel_from_top in sorted(raw_paths):
        abs_cand = (git_top / rel_from_top).resolve()
        if abs_cand.is_relative_to(resolved_root):
            rel = abs_cand.relative_to(resolved_root).as_posix()
            if rel and not rel.startswith((".ctx/", ".ctx-cache/")):
                scoped.append(rel)
    return spec_label, sorted(dict.fromkeys(scoped))


def analyze_diff_impact(
    root: Path,
    *,
    git_diff: str | None = None,
    staged: bool = False,
    max_depth: int | None = None,
    skeleton: RepoSkeleton | None = None,
    graph: DependencyGraph | None = None,
) -> DiffImpactResult:
    """Compile a git diff into unioned blast radius, coupled tests, and proportional verification checks."""
    if max_depth is not None and max_depth < 1:
        raise ValueError("max_depth must be >= 1 when specified")

    resolved_root = root.resolve()
    spec_label, changed_files = _collect_git_diff_files(
        resolved_root,
        git_diff=git_diff,
        staged=staged,
    )
    sk = skeleton if skeleton is not None else extract_skeleton(resolved_root)
    dep_graph = graph if graph is not None else build_dependency_graph(resolved_root, skeleton=sk)

    all_files = {f.relative_path: f for f in sk.files}
    changed_configs: list[str] = []
    changed_test_files: list[str] = []
    changed_boundary_docs: list[str] = []
    matched_code_files: list[str] = []

    for rel in changed_files:
        lower = rel.lower()
        if _is_shared_config_path(rel):
            changed_configs.append(rel)
        elif is_test_file_path(rel):
            changed_test_files.append(rel)
        elif lower.endswith((".md", ".rst", ".txt")):
            changed_boundary_docs.append(rel)
        else:
            matched_code_files.append(rel)

    seed_graph_files = [
        rel
        for rel in [*matched_code_files, *changed_test_files]
        if rel in all_files
    ]
    seed_set = set(seed_graph_files)

    direct_outbound = sorted({
        dep
        for src in seed_graph_files
        for dep in dep_graph.outbound_files.get(src, [])
        if dep not in seed_set
    })

    visited_dist: dict[str, int] = {f: 0 for f in seed_graph_files}
    visited_via: dict[str, str] = {}
    queue: deque[str] = deque(seed_graph_files)
    while queue:
        curr = queue.popleft()
        curr_dist = visited_dist[curr]
        if max_depth is not None and curr_dist >= max_depth:
            continue
        for caller in dep_graph.inbound_files.get(curr, []):
            if caller not in visited_dist:
                visited_dist[caller] = curr_dist + 1
                visited_via[caller] = curr
                queue.append(caller)

    direct_inbound = sorted(
        f for f, d in visited_dist.items() if d == 1 and not is_test_file_path(f)
    )
    transitive_records: list[dict[str, Any]] = [
        {
            "path": f,
            "distance": d,
            "via": visited_via[f],
            "is_test": is_test_file_path(f),
        }
        for f, d in sorted(visited_dist.items(), key=lambda kv: (kv[1], kv[0]))
        if d >= 1
    ]

    coupled_map: dict[str, dict[str, Any]] = {}
    for t_rel in changed_test_files:
        if t_rel in all_files:
            coupled_map[t_rel] = {"path": t_rel, "distance": 0, "reason": "changed_test"}
    for rec in transitive_records:
        if rec["is_test"] and rec["path"] not in coupled_map:
            coupled_map[rec["path"]] = {
                "path": rec["path"],
                "distance": rec["distance"],
                "reason": "direct_import" if rec["distance"] == 1 else "transitive_import",
            }

    seed_stems = {
        Path(f).stem.lower()
        for f in matched_code_files
        if Path(f).stem.lower() not in {"__init__", "index", "mod", "main", "lib"}
    }
    for f in sk.files:
        if not is_test_file_path(f.relative_path) or f.relative_path in coupled_map:
            continue
        tname = Path(f.relative_path).stem.lower()
        stripped_tname = (
            tname.removeprefix("test_")
            .removesuffix("_test")
            .removesuffix(".test")
            .removesuffix(".spec")
        )
        if stripped_tname in seed_stems or any(
            re.search(rf"(?:^|[_.-]){re.escape(st)}(?:$|[_.-])", stripped_tname) is not None
            for st in seed_stems
            if len(st) >= 3
        ):
            coupled_map[f.relative_path] = {
                "path": f.relative_path,
                "distance": None,
                "reason": "naming_convention",
            }

    reason_rank = {
        "changed_test": 0,
        "direct_import": 1,
        "transitive_import": 2,
        "naming_convention": 3,
    }
    coupled_tests = sorted(
        coupled_map.values(),
        key=lambda item: (
            reason_rank.get(str(item["reason"]), 9),
            item["distance"] if isinstance(item["distance"], int) else 999,
            str(item["path"]),
        ),
    )

    affected_prod_files = {f for f in visited_dist if not is_test_file_path(f)} | {
        f for f in matched_code_files if f in all_files
    }
    affected_subsystems = sorted({
        _subsystem_key_for_rel_path(f)
        for f in affected_prod_files
    })

    ep_by_file = _resolve_entrypoint_files(resolved_root, sk)
    affected_eps: set[str] = set()
    for fpath in affected_prod_files:
        affected_eps.update(ep_by_file.get(fpath, set()))
    for surf in sk.operational_surfaces:
        if surf.file in affected_prod_files and surf.kind in (
            "cli_command",
            "http_route",
            "mcp_tool",
            "mcp_resource",
        ):
            affected_eps.add(f"{surf.kind}:{surf.name} ({surf.file})")

    governing_docs: list[str] = []
    seed_parents = {
        parent.as_posix()
        for f in changed_files
        for parent in [Path(f).parent, *Path(f).parents]
    }
    for doc in sk.boundary_docs:
        if doc.kind not in ("authority", "architecture"):
            continue
        doc_parent = Path(doc.relative_path).parent.as_posix()
        if (
            doc_parent == "."
            or doc.relative_path.lower().startswith(("docs/adr/", "adr/", "docs/designs/"))
            or doc_parent in seed_parents
        ):
            governing_docs.append(doc.relative_path)

    cycles_involving_changes = [
        cyc for cyc in dep_graph.cycles if any(f in seed_set for f in cyc)
    ]

    repo_has_tests = any(is_test_file_path(f.relative_path) for f in sk.files)
    escalation_reasons: list[str] = []
    recommended_checks: list[str] = []

    def _default_broad_runner() -> str:
        if (resolved_root / "pyproject.toml").is_file() or sk.languages.get("Python"):
            return "pytest"
        if (resolved_root / "Cargo.toml").is_file():
            return "cargo test"
        if (resolved_root / "go.mod").is_file():
            return "go test ./..."
        if (resolved_root / "package.json").is_file():
            return "npm test"
        return "pytest"

    doc_hygiene_test = "tests/test_doc_hygiene.py"
    has_doc_hygiene = (resolved_root / doc_hygiene_test).is_file()
    has_test_docs = (resolved_root / "tests" / "test_docs.py").is_file()

    if not changed_files:
        verification_scope = "none"
    elif not matched_code_files and not changed_test_files and not changed_configs:
        verification_scope = "docs_only"
        if has_doc_hygiene:
            recommended_checks.append(f"python -m unittest {doc_hygiene_test}")
        if has_test_docs:
            recommended_checks.append("pytest tests/test_docs.py")
    else:
        if changed_configs:
            escalation_reasons.append(
                f"Shared configuration/fixture modified: {', '.join(changed_configs[:5])}"
            )
        if len(coupled_tests) > 12:
            escalation_reasons.append(
                f"High blast-radius fan-out ({len(coupled_tests)} coupled test files > 12)"
            )
        if matched_code_files and not coupled_tests and repo_has_tests:
            escalation_reasons.append(
                "Modified code has zero statically coupled tests; escalating to suite"
            )

        if escalation_reasons:
            verification_scope = "broad_suite"
            recommended_checks.append(_default_broad_runner())
        else:
            verification_scope = "targeted_tests"
            py_tests = [str(t["path"]) for t in coupled_tests if str(t["path"]).endswith(".py")]
            other_tests = [str(t["path"]) for t in coupled_tests if not str(t["path"]).endswith(".py")]
            if py_tests:
                recommended_checks.append(f"pytest {' '.join(py_tests)}")
            if other_tests:
                recommended_checks.append(_default_broad_runner())

        if changed_boundary_docs and has_doc_hygiene:
            doc_cmd = f"python -m unittest {doc_hygiene_test}"
            if doc_cmd not in recommended_checks:
                recommended_checks.append(doc_cmd)

    return DiffImpactResult(
        diff_spec=spec_label,
        changed_files=changed_files,
        matched_code_files=matched_code_files,
        changed_test_files=changed_test_files,
        changed_boundary_docs=changed_boundary_docs,
        changed_configs=changed_configs,
        direct_outbound_deps=direct_outbound,
        direct_inbound_dependents=direct_inbound,
        transitive_inbound_dependents=transitive_records,
        coupled_tests=coupled_tests,
        affected_subsystems=affected_subsystems,
        affected_entrypoints=sorted(affected_eps),
        governing_docs=sorted(dict.fromkeys(governing_docs)),
        cycles_involving_changes=cycles_involving_changes,
        verification_scope=verification_scope,
        recommended_checks=recommended_checks,
        escalation_reasons=escalation_reasons,
    )
