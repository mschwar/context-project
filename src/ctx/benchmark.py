"""Phase 27.1 Reproducible Static-Oracle A/B/C Navigation & Blast-Radius Benchmark for ctx.

Evaluates three codebase-navigation retrieval strategies across real repositories against an
independent AST/filesystem static ground-truth oracle (built directly from raw source files on
disk without calling `ctx.skeleton` or `ctx.impact`):

- Condition A (`raw_grep`): Raw file-tree listing, root doc reads (`README.md`, `AGENTS.md`,
  `CLAUDE.md`), candidate entrypoint reads, and real single-pass regex grep (`\\b<stem>\\b`)
  across production and test files on disk.
- Condition B (`tier1_manifests`): On-disk depth-0/1 `CONTEXT.md` manifests (or deterministic
  directory file-summary tables when `CONTEXT.md` is absent) + primary entrypoint read +
  single-pass regex grep for reverse dependencies and tests.
- Condition C (`tier2_plus_impact`): Tier 2 `.ctx/CONTEXT-0.md` architectural/surface map +
  `ctx impact <focal_target> --output json`.

All four recall dimensions (architecture/governance orientation, public operational surface
discovery, multi-hop reverse-dependency blast radius, and coupled test selection) are computed
strictly by set intersection / token presence against the independent static oracle, with zero
hardcoded recall constants.
"""

from __future__ import annotations

import ast
import json
import math
import re
import time
from collections import deque

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ctx import __version__
from ctx.ignore import load_ignore_patterns, should_ignore
from ctx.impact import analyze_impact
from ctx.skeleton import extract_skeleton, render_context_0

_ORACLE_SKIP_DIRS = frozenset({
    ".git",
    ".ctx",
    ".ctx-cache",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tmp",
    "dist",
    "build",
    "target",
})

_ORACLE_BOUNDARY_FILENAMES = frozenset({
    "readme.md",
    "readme.rst",
    "agents.md",
    "claude.md",
    "system.md",
    "rules.md",
    "gate_closeout.md",
    "architecture.md",
    "state.md",
    "todos.md",
    "runbook.md",
    "schema.md",
    "current.md",
    "security.md",
    "contributing.md",
})

_ORACLE_ENTRYPOINT_NAMES = (
    "cli.py",
    "mcp_server.py",
    "server.py",
    "main.py",
    "app.py",
    "__main__.py",
    "index.ts",
    "server.ts",
    "index.js",
    "main.go",
    "main.rs",
)

_SOURCE_EXTS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".rb", ".java", ".kt", ".cs", ".php", ".swift", ".ex", ".exs",
})

_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "options", "head", "route", "api_route"})
_JS_REL_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+?\s+from\s+)?['"](\.[^'"]+)['"]|require\(\s*['"](\.[^'"]+)['"]\s*\))""",
    re.MULTILINE,
)
_JS_HTTP_RE = re.compile(
    r"""\b(?:app|router|server)\.(get|post|put|delete|patch)\(\s*['"](/[^'"]*)['"]""",
    re.IGNORECASE,
)
_GO_HTTP_RE = re.compile(r"""\b(?:HandleFunc|Handle|GET|POST|PUT|DELETE)\(\s*"(/[^"]*)"\s*,""")
_RUST_HTTP_RE = re.compile(r"""#\[(?:get|post|put|delete|patch)\(\s*"(/[^"]*)"\s*\)\]""")
_GO_MOD_RE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
_GO_IMPORT_QUOTED_RE = re.compile(r'"([^"]+)"')
_RUST_CRATE_USE_RE = re.compile(r"\buse\s+crate::([A-Za-z0-9_:]+)")
_RUST_MOD_DECL_RE = re.compile(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", re.MULTILINE)
_RUBY_REQ_REL_RE = re.compile(r"""^\s*require_relative\s*\(?\s*['"]([^'"]+)['"]""", re.MULTILINE)


def _approx_tokens(text_or_bytes: str | bytes) -> int:
    raw_len = len(text_or_bytes.encode("utf-8")) if isinstance(text_or_bytes, str) else len(text_or_bytes)
    return max(1, math.ceil(raw_len / 4)) if raw_len > 0 else 0


def _oracle_is_test(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    lower_parts = [p.lower() for p in parts]
    if any(p in {"tests", "test", "__tests__", "spec", "specs"} for p in lower_parts[:-1]):
        return True
    name = lower_parts[-1] if lower_parts else ""
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_test.go", "_test.rs", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js", "_spec.rb"))
        or name == "conftest.py"
    )


@dataclass
class _IndependentOracle:
    """Ground-truth repository facts extracted independently from raw files on disk."""

    files: dict[str, str]
    boundary_docs: set[str]
    public_surfaces: set[tuple[str, str, str]]  # (kind, identifier_token, file)
    outbound: dict[str, set[str]]
    inbound: dict[str, set[str]]
    internal_edge_count: int
    focal_target: str
    prod_direct: set[str]
    prod_transitive: set[str]
    coupled_tests: set[str]


def _walk_repo_texts(root: Path) -> dict[str, str]:
    spec = load_ignore_patterns(root)
    files: dict[str, str] = {}

    def _visit(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in _ORACLE_SKIP_DIRS or should_ignore(entry, spec, root):
                    continue
                _visit(entry)
            elif entry.is_file():
                if entry.name == "CONTEXT.md" or should_ignore(entry, spec, root):
                    continue
                try:
                    if entry.stat().st_size > 512_000:
                        continue
                    raw = entry.read_bytes()
                except OSError:
                    continue
                if b"\x00" in raw[:4096]:
                    continue
                rel = entry.relative_to(root).as_posix()
                files[rel] = raw.decode("utf-8", errors="replace")

    _visit(root)
    return files


def _extract_oracle_boundary_docs(files: dict[str, str]) -> set[str]:
    docs: set[str] = set()
    for rel in files:
        p = Path(rel)
        lower_name = p.name.lower()
        lower_parts = {part.lower() for part in p.parts[:-1]}
        if lower_name in _ORACLE_BOUNDARY_FILENAMES:
            docs.add(rel)
        elif p.suffix.lower() in {".md", ".rst"} and (lower_parts & {"adr", "adrs", "decisions"}):
            docs.add(rel)
    return docs


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    return None


def _extract_pyproject_script_names(toml_text: str) -> list[str]:
    """Extract `[project.scripts]` CLI entrypoint names with a Python 3.10-safe fallback."""
    if tomllib is not None:
        try:
            pyproj = tomllib.loads(toml_text)
            scripts = pyproj.get("project", {}).get("scripts", {})
            if isinstance(scripts, dict):
                return [s.strip() for s in scripts if isinstance(s, str) and s.strip()]
        except Exception:
            return []
        return []

    names: list[str] = []
    in_scripts = False
    for raw_line in toml_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_scripts = stripped[1:-1].strip() == "project.scripts"
            continue
        if in_scripts and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().strip("\"'")
            if key and re.fullmatch(r"[A-Za-z0-9_.-]+", key):
                names.append(key)
    return names


def _extract_oracle_surfaces(files: dict[str, str]) -> set[tuple[str, str, str]]:
    surfaces: set[tuple[str, str, str]] = set()

    if "pyproject.toml" in files:
        for sname in _extract_pyproject_script_names(files["pyproject.toml"]):
            surfaces.add(("cli_command", sname, "pyproject.toml"))

    if "package.json" in files:
        try:
            pkg = json.loads(files["package.json"])
            bin_field = pkg.get("bin")
            if isinstance(bin_field, str) and isinstance(pkg.get("name"), str):
                surfaces.add(("cli_command", pkg["name"].strip(), "package.json"))
            elif isinstance(bin_field, dict):
                for bname in bin_field:
                    if isinstance(bname, str) and bname.strip():
                        surfaces.add(("cli_command", bname.strip(), "package.json"))
        except Exception:
            pass

    for rel, content in files.items():
        if _oracle_is_test(rel):
            continue
        suffix = Path(rel).suffix.lower()
        if suffix == ".py":
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in node.decorator_list:
                        call = dec if isinstance(dec, ast.Call) else None
                        target = call.func if call is not None else dec
                        attr = target.attr if isinstance(target, ast.Attribute) else (target.id if isinstance(target, ast.Name) else "")
                        attr_l = attr.lower()
                        if attr_l in {"command", "group"}:
                            hidden = False
                            explicit_name: str | None = None
                            if call is not None:
                                if call.args:
                                    explicit_name = _const_str(call.args[0])
                                for kw in call.keywords:
                                    if kw.arg == "name":
                                        explicit_name = _const_str(kw.value) or explicit_name
                                    elif kw.arg == "hidden" and isinstance(kw.value, ast.Constant) and bool(kw.value.value):
                                        hidden = True
                            if not hidden:
                                cmd_token = explicit_name or node.name.replace("_", "-")
                                if not cmd_token.startswith("_"):
                                    surfaces.add(("cli_command", cmd_token, rel))
                        elif attr_l in _HTTP_METHODS and call is not None and call.args:
                            route_path = _const_str(call.args[0])
                            if route_path and route_path.startswith("/"):
                                surfaces.add(("http_route", route_path, rel))
                        elif attr_l == "tool":
                            tname = None
                            if call is not None:
                                if call.args:
                                    tname = _const_str(call.args[0])
                                for kw in call.keywords:
                                    if kw.arg == "name":
                                        tname = _const_str(kw.value) or tname
                            surfaces.add(("mcp_tool", tname or node.name, rel))
                        elif attr_l == "resource" and call is not None and call.args:
                            r_uri = _const_str(call.args[0])
                            if r_uri:
                                surfaces.add(("mcp_resource", r_uri, rel))

                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "add_parser" and node.args:
                        sub_name = _const_str(node.args[0])
                        if sub_name and not sub_name.startswith("_"):
                            surfaces.add(("cli_command", sub_name, rel))

                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    t_names: list[str] = []
                    if isinstance(node, ast.Assign):
                        t_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                        val = node.value
                    else:
                        t_names = [node.target.id] if isinstance(node.target, ast.Name) else []
                        val = node.value
                    if val is None or not isinstance(val, (ast.List, ast.Tuple)):
                        continue
                    upper_names = {n.upper() for n in t_names}
                    is_tool_tbl = any("TOOL" in u for u in upper_names)
                    is_res_tbl = any("RESOURCE" in u for u in upper_names)
                    if not (is_tool_tbl or is_res_tbl):
                        continue
                    for elt in val.elts:
                        if not isinstance(elt, ast.Dict):
                            continue
                        kv: dict[str, str] = {}
                        for k_node, v_node in zip(elt.keys, elt.values):
                            ks = _const_str(k_node)
                            vs = _const_str(v_node)
                            if ks and vs:
                                kv[ks] = vs
                        if is_tool_tbl and "name" in kv:
                            surfaces.add(("mcp_tool", kv["name"], rel))
                        elif is_res_tbl:
                            uri = kv.get("uri") or kv.get("uriTemplate")
                            if uri:
                                surfaces.add(("mcp_resource", uri, rel))

        elif suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            for m in _JS_HTTP_RE.finditer(content):
                surfaces.add(("http_route", m.group(2), rel))
        elif suffix == ".go":
            for m in _GO_HTTP_RE.finditer(content):
                surfaces.add(("http_route", m.group(1), rel))
        elif suffix == ".rs":
            for m in _RUST_HTTP_RE.finditer(content):
                surfaces.add(("http_route", m.group(1), rel))

    return surfaces


def _build_oracle_import_graph(files: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, set[str]], int]:
    all_paths = set(files.keys())
    outbound: dict[str, set[str]] = {rel: set() for rel in all_paths}
    inbound: dict[str, set[str]] = {rel: set() for rel in all_paths}

    # Map Python dotted module names -> repo-relative .py path
    py_mod_index: dict[str, str] = {}
    for rel in sorted(all_paths):
        if not rel.endswith(".py"):
            continue
        parts = list(Path(rel).parts)
        if parts[0] == "src" and len(parts) > 1:
            mod_parts = parts[1:]
        else:
            mod_parts = parts
        if mod_parts[-1] == "__init__.py":
            dotted = ".".join(mod_parts[:-1])
        else:
            dotted = ".".join([*mod_parts[:-1], mod_parts[-1][:-3]])
        if dotted:
            py_mod_index.setdefault(dotted, rel)

    go_module_prefix = ""
    if "go.mod" in files:
        m = _GO_MOD_RE.search(files["go.mod"])
        if m:
            go_module_prefix = m.group(1).strip()

    go_dir_files: dict[str, list[str]] = {}
    for rel in sorted(all_paths):
        if rel.endswith(".go") and not _oracle_is_test(rel):
            parent = Path(rel).parent.as_posix()
            go_dir_files.setdefault("" if parent == "." else parent, []).append(rel)

    def _add_edge(src: str, dst: str) -> None:
        if dst in all_paths and dst != src:
            outbound[src].add(dst)
            inbound[dst].add(src)

    for rel, content in files.items():
        suffix = Path(rel).suffix.lower()
        if suffix == ".py":
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            parts = list(Path(rel).parts)
            mod_parts = parts[1:] if (parts[0] == "src" and len(parts) > 1) else parts
            cur_pkg = mod_parts[:-1]

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        cand = alias.name
                        while cand:
                            if cand in py_mod_index:
                                _add_edge(rel, py_mod_index[cand])
                                break
                            cand = cand.rsplit(".", 1)[0] if "." in cand else ""
                elif isinstance(node, ast.ImportFrom):
                    base_parts: list[str] = []
                    if node.level and node.level > 0:
                        trim = max(0, len(cur_pkg) - (node.level - 1))
                        base_parts = list(cur_pkg[:trim])
                        if node.module:
                            base_parts.extend(node.module.split("."))
                    elif node.module:
                        base_parts = node.module.split(".")
                    base_mod = ".".join(p for p in base_parts if p)
                    matched_sub = False
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        sub_mod = f"{base_mod}.{alias.name}" if base_mod else alias.name
                        if sub_mod in py_mod_index:
                            _add_edge(rel, py_mod_index[sub_mod])
                            matched_sub = True
                    if base_mod:
                        cand = base_mod
                        while cand:
                            if cand in py_mod_index:
                                if not matched_sub or py_mod_index[cand] != rel:
                                    _add_edge(rel, py_mod_index[cand])
                                break
                            cand = cand.rsplit(".", 1)[0] if "." in cand else ""

        elif suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            base_dir = Path(rel).parent
            for m in _JS_REL_IMPORT_RE.finditer(content):
                spec = m.group(1) or m.group(2)
                if not spec:
                    continue
                norm = Path(os_normpath_posix((base_dir / spec).as_posix()))
                base_str = norm.as_posix()
                for cand in (
                    base_str,
                    f"{base_str}.ts",
                    f"{base_str}.tsx",
                    f"{base_str}.js",
                    f"{base_str}.jsx",
                    f"{base_str}/index.ts",
                    f"{base_str}/index.tsx",
                    f"{base_str}/index.js",
                ):
                    if cand in all_paths:
                        _add_edge(rel, cand)
                        break

        elif suffix == ".go" and go_module_prefix:
            for m in _GO_IMPORT_QUOTED_RE.finditer(content):
                imp = m.group(1)
                if imp == go_module_prefix:
                    sub_dir = ""
                elif imp.startswith(go_module_prefix + "/"):
                    sub_dir = imp[len(go_module_prefix) + 1 :]
                else:
                    continue
                for target_go in go_dir_files.get(sub_dir, []):
                    _add_edge(rel, target_go)

        elif suffix == ".rs":
            for m in _RUST_CRATE_USE_RE.finditer(content):
                segs = [s for s in m.group(1).split("::") if s and s != "self"]
                for depth in range(len(segs), 0, -1):
                    prefix = "/".join(segs[:depth])
                    for cand in (f"src/{prefix}.rs", f"src/{prefix}/mod.rs", f"{prefix}.rs"):
                        if cand in all_paths:
                            _add_edge(rel, cand)
                            break
            parent_dir = Path(rel).parent.as_posix()
            base_prefix = "" if parent_dir == "." else f"{parent_dir}/"
            for m in _RUST_MOD_DECL_RE.finditer(content):
                mname = m.group(1)
                for cand in (f"{base_prefix}{mname}.rs", f"{base_prefix}{mname}/mod.rs"):
                    if cand in all_paths:
                        _add_edge(rel, cand)
                        break

        elif suffix == ".rb":
            base_dir = Path(rel).parent
            for m in _RUBY_REQ_REL_RE.finditer(content):
                norm = os_normpath_posix((base_dir / m.group(1)).as_posix())
                for cand in (norm, f"{norm}.rb"):
                    if cand in all_paths:
                        _add_edge(rel, cand)
                        break

    edge_count = sum(len(targets) for targets in outbound.values())
    return outbound, inbound, edge_count


def os_normpath_posix(posix_path: str) -> str:
    parts: list[str] = []
    for seg in posix_path.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def _build_independent_oracle(root: Path) -> _IndependentOracle:
    files = _walk_repo_texts(root)
    boundary_docs = _extract_oracle_boundary_docs(files)
    public_surfaces = _extract_oracle_surfaces(files)
    outbound, inbound, edge_count = _build_oracle_import_graph(files)

    # Select focal high-fan-in production module directly from the independent oracle graph
    candidates: list[tuple[int, int, str]] = []
    for rel in sorted(files):
        if _oracle_is_test(rel) or Path(rel).suffix.lower() not in _SOURCE_EXTS:
            continue
        is_index = 1 if Path(rel).name in {"__init__.py", "index.ts", "index.js", "mod.rs"} else 0
        prod_in = sum(1 for src in inbound.get(rel, set()) if not _oracle_is_test(src))
        candidates.append((-prod_in, is_index, rel))
    if candidates:
        candidates.sort()
        focal_target = candidates[0][2]
    else:
        focal_target = next(iter(sorted(files)), ".")

    # Multi-hop reverse BFS in independent oracle graph
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(focal_target, 0)])
    prod_direct: set[str] = set()
    prod_transitive: set[str] = set()
    coupled_tests: set[str] = set()

    while queue:
        cur, dist = queue.popleft()
        for caller in sorted(inbound.get(cur, set())):
            if caller == focal_target or caller in visited:
                continue
            visited.add(caller)
            ndist = dist + 1
            if _oracle_is_test(caller):
                coupled_tests.add(caller)
            else:
                prod_transitive.add(caller)
                if ndist == 1:
                    prod_direct.add(caller)
            queue.append((caller, ndist))

    focal_stem = Path(focal_target).stem.lower()
    if focal_stem and focal_stem not in {"__init__", "index", "mod"}:
        for rel in files:
            if _oracle_is_test(rel):
                tstem = Path(rel).stem.lower()
                if tstem in {
                    f"test_{focal_stem}",
                    f"{focal_stem}_test",
                    f"{focal_stem}.test",
                    f"{focal_stem}.spec",
                    f"{focal_stem}_spec",
                }:
                    coupled_tests.add(rel)

    return _IndependentOracle(
        files=files,
        boundary_docs=boundary_docs,
        public_surfaces=public_surfaces,
        outbound=outbound,
        inbound=inbound,
        internal_edge_count=edge_count,
        focal_target=focal_target,
        prod_direct=prod_direct,
        prod_transitive=prod_transitive,
        coupled_tests=coupled_tests,
    )


def _surface_present_in_texts(token: str, texts: list[str]) -> bool:
    if not token or not texts:
        return False
    pattern = re.compile(rf"(?<![A-Za-z0-9_/-]){re.escape(token)}(?![A-Za-z0-9_-])")
    return any(pattern.search(blob) is not None for blob in texts if blob)


def _select_candidate_entrypoints(files: dict[str, str], limit: int = 4) -> list[str]:
    ranked: list[tuple[int, int, str]] = []
    for rel in files:
        if _oracle_is_test(rel):
            continue
        name = Path(rel).name
        if name in {"pyproject.toml", "package.json"}:
            ranked.append((0, len(Path(rel).parts), rel))
        elif name in _ORACLE_ENTRYPOINT_NAMES:
            idx = _ORACLE_ENTRYPOINT_NAMES.index(name)
            ranked.append((1 + idx, len(Path(rel).parts), rel))
    ranked.sort()
    return [rel for _, _, rel in ranked[:limit]]


def _execute_regex_grep(
    files: dict[str, str],
    pattern: re.Pattern[str],
    *,
    include_tests: bool,
    only_tests: bool,
    max_lines: int,
    only_source: bool = False,
    max_per_file: int | None = None,
) -> tuple[str, set[str]]:
    """Run an actual line-by-line regex grep over on-disk file contents.

    Only files with at least one line emitted within `max_lines` are added to `matched_files`,
    guaranteeing 1:1 parity between counted token payloads and scored retrieval hits.
    """
    matched_lines: list[str] = []
    matched_files: set[str] = set()
    for rel in sorted(files):
        if only_source and Path(rel).suffix.lower() not in _SOURCE_EXTS:
            continue
        is_t = _oracle_is_test(rel)
        if only_tests and not is_t:
            continue
        if not include_tests and is_t:
            continue
        content = files[rel]
        file_hits = 0
        for lineno, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                if len(matched_lines) >= max_lines:
                    return "\n".join(matched_lines), matched_files
                matched_files.add(rel)
                matched_lines.append(f"{rel}:{lineno}:{line[:160]}")
                file_hits += 1
                if max_per_file is not None and file_hits >= max_per_file:
                    break
    return "\n".join(matched_lines), matched_files


def _load_or_synthesize_tier1_depth1_manifests(root: Path, files: dict[str, str]) -> list[str]:
    """Read actual depth-0/1 CONTEXT.md manifests if present; otherwise render deterministic directory listings."""
    existing: list[str] = []
    root_manifest = root / "CONTEXT.md"
    if root_manifest.is_file():
        try:
            existing.append(root_manifest.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    try:
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.is_dir() and child.name not in _ORACLE_SKIP_DIRS and (child / "CONTEXT.md").is_file():
                try:
                    existing.append((child / "CONTEXT.md").read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    except OSError:
        pass

    if existing:
        return existing

    # Deterministic directory-level manifest equivalents from real files at depth 0 and depth 1
    by_dir: dict[str, list[str]] = {}
    for rel in sorted(files):
        parts = Path(rel).parts
        if len(parts) == 1:
            by_dir.setdefault(".", []).append(rel)
        elif len(parts) <= 3 and not _oracle_is_test(rel):
            top_key = "/".join(parts[:-1][:2])
            by_dir.setdefault(top_key, []).append(rel)

    synthesized: list[str] = []
    for dkey in sorted(by_dir)[:9]:
        entries = by_dir[dkey]
        lines = [f"# {dkey}", "", f"Directory manifest covering {len(entries)} files.", "", "## Files"]
        for rel in entries:
            first_doc = ""
            for raw_line in files[rel].splitlines()[:12]:
                stripped = raw_line.strip().lstrip("#\"'/*- ").strip()
                if stripped and not stripped.startswith(("from ", "import ", "package ", "use ")):
                    first_doc = stripped[:110]
                    break
            lines.append(f"- **{Path(rel).name}** — {first_doc or 'Source module.'}")
        synthesized.append("\n".join(lines))
    return synthesized


@dataclass(frozen=True)
class ConditionMetrics:
    """Measured metrics for one navigation condition on one repository."""

    condition: str
    tool_turns: int
    context_tokens_read: int
    recall_arch_orientation: float
    recall_surface_discovery: float
    recall_blast_radius: float
    precision_blast_radius: float
    f1_blast_radius: float
    recall_coupled_tests: float
    precision_coupled_tests: float
    f1_coupled_tests: float
    mean_recall: float
    maint_llm_tokens_impl_commit: int
    maint_llm_tokens_minor_struct_commit: int
    maint_jev_tokens_minor_struct_commit: int


@dataclass(frozen=True)
class RepoBenchmarkResult:
    """Benchmark comparison across Conditions A, B, and C for a single repository."""

    repo_name: str
    repo_path: str
    total_files: int
    subsystems_count: int
    internal_edges: int
    operational_surfaces_count: int
    focal_target: str
    focal_direct_dependents: int
    focal_transitive_dependents: int
    focal_coupled_tests: int
    elapsed_ms: int
    conditions: dict[str, ConditionMetrics] = field(default_factory=dict)


def _ratio(found: int, total: int) -> float:
    return (found / total) if total > 0 else 1.0


def _precision_and_f1(predicted: set[str], truth: set[str]) -> tuple[float, float, float]:
    """Return `(recall, precision, f1)` for *predicted* against ground-truth *truth*."""
    tp = len(predicted & truth)
    recall = _ratio(tp, len(truth))
    if not predicted:
        precision = 1.0 if not truth else 0.0
    else:
        precision = tp / len(predicted)
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return recall, precision, f1


def _extract_top_level_symbol_names(content: str, suffix: str, limit: int = 4) -> list[str]:
    """Extract exported top-level symbol identifiers from a focal module for Condition B grep."""
    names: list[str] = []
    if suffix == ".py":
        try:
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not node.name.startswith("_") and len(node.name) >= 4:
                        names.append(node.name)
        except SyntaxError:
            pass
    else:
        for m in re.finditer(
            r"^\s*(?:export\s+)?(?:pub\s+)?(?:async\s+)?(?:class|def|fn|func|interface|struct)\s+([A-Za-z][A-Za-z0-9_]{3,})",
            content,
            re.MULTILINE,
        ):
            names.append(m.group(1))
    return names[:limit]


def benchmark_repository(root: Path) -> RepoBenchmarkResult:
    """Run deterministic static-oracle A/B/C navigation benchmark on *root*."""
    started = time.perf_counter()
    resolved = root.resolve()

    oracle = _build_independent_oracle(resolved)
    focal_target = oracle.focal_target
    focal_stem = Path(focal_target).stem

    # ── Condition A: raw_grep (real file reads + real regex grep, no ctx) ────
    a_steps: list[tuple[str, str]] = []
    tree_listing = "\n".join(sorted(oracle.files.keys()))
    a_steps.append(("list_tree", tree_listing))

    root_doc_paths = [
        rel
        for rel in sorted(oracle.files)
        if "/" not in rel and rel.lower() in {"readme.md", "readme.rst", "agents.md", "claude.md"}
    ]
    # Condition A also inspects up to 2 architecture/governance docs discovered in the file-tree listing
    discovered_arch_Candidates = sorted(
        (
            rel
            for rel in oracle.files
            if rel not in root_doc_paths
            and Path(rel).name.lower() in {"architecture.md", "schema.md", "current.md", "state.md", "security.md"}
        ),
        key=lambda p: (len(Path(p).parts), p),
    )[:2]
    a_doc_paths = [*root_doc_paths, *discovered_arch_Candidates]
    a_doc_texts: list[str] = []
    for rel in a_doc_paths:
        txt = oracle.files[rel][:16384]
        a_doc_texts.append(txt)
        a_steps.append((f"read_doc:{rel}", txt))

    ep_candidates = _select_candidate_entrypoints(oracle.files, limit=4)
    ep_texts: list[str] = []
    for rel in ep_candidates:
        txt = oracle.files[rel][:24576]
        ep_texts.append(txt)
        a_steps.append((f"read_entrypoint:{rel}", txt))

    focal_raw = oracle.files.get(focal_target, "")
    focal_text = focal_raw[:16384]
    if focal_text:
        a_steps.append((f"read_focal:{focal_target}", focal_text))

    grep_re = re.compile(rf"\b{re.escape(focal_stem)}\b") if focal_stem else re.compile(r"$^")
    prod_grep_out, a_grep_prod_files = _execute_regex_grep(
        oracle.files,
        grep_re,
        include_tests=False,
        only_tests=False,
        max_lines=120,
        only_source=True,
        max_per_file=3,
    )
    a_grep_prod_files.discard(focal_target)
    a_steps.append(("grep_prod", prod_grep_out))

    test_grep_out, a_grep_test_files = _execute_regex_grep(
        oracle.files,
        grep_re,
        include_tests=True,
        only_tests=True,
        max_lines=80,
        only_source=True,
        max_per_file=3,
    )
    a_steps.append(("grep_tests", test_grep_out))
    if focal_stem:
        low_stem = focal_stem.lower()
        for rel in oracle.files:
            if _oracle_is_test(rel):
                t_stripped = (
                    Path(rel).stem.lower()
                    .removeprefix("test_")
                    .removesuffix("_test")
                    .removesuffix(".test")
                    .removesuffix(".spec")
                )
                if re.search(rf"(?:^|[_.-]){re.escape(low_stem)}(?:$|[_.-])", t_stripped):
                    a_grep_test_files.add(rel)

    cond_a_turns = len(a_steps)
    cond_a_tokens = sum(_approx_tokens(payload) for _, payload in a_steps)

    a_ingested_texts = [*a_doc_texts, *ep_texts]
    a_bdocs_found = set(a_doc_paths) & oracle.boundary_docs
    a_arch_recall = _ratio(len(a_bdocs_found), len(oracle.boundary_docs))
    a_surf_found = sum(
        1 for (_k, tok, _f) in oracle.public_surfaces if _surface_present_in_texts(tok, a_ingested_texts)
    )
    a_surf_recall = _ratio(a_surf_found, len(oracle.public_surfaces))
    a_blast_recall, a_blast_prec, a_blast_f1 = _precision_and_f1(a_grep_prod_files, oracle.prod_transitive)
    a_test_recall, a_test_prec, a_test_f1 = _precision_and_f1(a_grep_test_files, oracle.coupled_tests)
    a_mean = (a_arch_recall + a_surf_recall + a_blast_recall + a_test_recall) / 4.0

    cond_a = ConditionMetrics(
        condition="raw_grep",
        tool_turns=cond_a_turns,
        context_tokens_read=cond_a_tokens,
        recall_arch_orientation=round(a_arch_recall, 4),
        recall_surface_discovery=round(a_surf_recall, 4),
        recall_blast_radius=round(a_blast_recall, 4),
        precision_blast_radius=round(a_blast_prec, 4),
        f1_blast_radius=round(a_blast_f1, 4),
        recall_coupled_tests=round(a_test_recall, 4),
        precision_coupled_tests=round(a_test_prec, 4),
        f1_coupled_tests=round(a_test_f1, 4),
        mean_recall=round(a_mean, 4),
        maint_llm_tokens_impl_commit=0,
        maint_llm_tokens_minor_struct_commit=0,
        maint_jev_tokens_minor_struct_commit=0,
    )

    # ── Condition B: tier1_manifests (`ctx export --depth 1` + 1 entrypoint + symbol-aware grep) ──
    b_steps: list[tuple[str, str]] = []
    t1_manifest_texts = _load_or_synthesize_tier1_depth1_manifests(resolved, oracle.files)
    t1_export_blob = "\n\n".join(t1_manifest_texts)
    b_steps.append(("ctx_export_depth1", t1_export_blob))

    b_ep_texts = ep_texts[:1]
    for idx, txt in enumerate(b_ep_texts):
        b_steps.append((f"read_entrypoint:{idx}", txt))

    focal_syms = _extract_top_level_symbol_names(focal_raw, Path(focal_target).suffix.lower(), limit=4)
    b_terms = [re.escape(t) for t in ([focal_stem, *focal_syms] if focal_stem else focal_syms) if t]
    b_grep_re = re.compile(rf"\b(?:{'|'.join(b_terms)})\b") if b_terms else re.compile(r"$^")
    b_prod_grep_out, b_grep_prod_files = _execute_regex_grep(
        oracle.files,
        b_grep_re,
        include_tests=False,
        only_tests=False,
        max_lines=120,
        only_source=True,
        max_per_file=3,
    )
    b_grep_prod_files.discard(focal_target)
    b_steps.append(("grep_prod_symbols", b_prod_grep_out))

    b_test_grep_out, b_grep_test_files = _execute_regex_grep(
        oracle.files,
        b_grep_re,
        include_tests=True,
        only_tests=True,
        max_lines=80,
        only_source=True,
        max_per_file=3,
    )
    b_steps.append(("grep_tests_symbols", b_test_grep_out))

    cond_b_turns = len(b_steps)
    cond_b_tokens = sum(_approx_tokens(payload) for _, payload in b_steps)

    b_ingested_texts = [*t1_manifest_texts, *b_ep_texts]
    b_bdocs_found = {
        d
        for d in oracle.boundary_docs
        if any((d in m or f"**{Path(d).name}**" in m) for m in t1_manifest_texts)
        and (len(Path(d).parts) <= 2)
    }
    b_arch_recall = _ratio(len(b_bdocs_found), len(oracle.boundary_docs))
    b_surf_found = sum(
        1 for (_k, tok, _f) in oracle.public_surfaces if _surface_present_in_texts(tok, b_ingested_texts)
    )
    b_surf_recall = _ratio(b_surf_found, len(oracle.public_surfaces))
    b_blast_recall, b_blast_prec, b_blast_f1 = _precision_and_f1(b_grep_prod_files, oracle.prod_transitive)
    b_test_recall, b_test_prec, b_test_f1 = _precision_and_f1(b_grep_test_files, oracle.coupled_tests)
    b_mean = (b_arch_recall + b_surf_recall + b_blast_recall + b_test_recall) / 4.0

    # Modeled analytical Tier 1 incremental refresh cost for modifying `focal_target`:
    # 1 file summary call (truncated at 8,000 max_file_tokens + prompt wrapper) + directory cascade
    focal_dir = Path(focal_target).parent.as_posix()
    focal_siblings = sum(1 for rel in oracle.files if Path(rel).parent.as_posix() == focal_dir)
    focal_file_tok = min(8000, _approx_tokens(focal_raw))
    t1_maint_tokens = focal_file_tok + 360 + focal_siblings * 28

    cond_b = ConditionMetrics(
        condition="tier1_manifests",
        tool_turns=cond_b_turns,
        context_tokens_read=cond_b_tokens,
        recall_arch_orientation=round(b_arch_recall, 4),
        recall_surface_discovery=round(b_surf_recall, 4),
        recall_blast_radius=round(b_blast_recall, 4),
        precision_blast_radius=round(b_blast_prec, 4),
        f1_blast_radius=round(b_blast_f1, 4),
        recall_coupled_tests=round(b_test_recall, 4),
        precision_coupled_tests=round(b_test_prec, 4),
        f1_coupled_tests=round(b_test_f1, 4),
        mean_recall=round(b_mean, 4),
        maint_llm_tokens_impl_commit=t1_maint_tokens,
        maint_llm_tokens_minor_struct_commit=t1_maint_tokens,
        maint_jev_tokens_minor_struct_commit=0,
    )

    # ── Condition C: tier2_plus_impact (CONTEXT-0.md + `ctx impact <focal_target>`) ──
    c_steps: list[tuple[str, str]] = []
    sk = extract_skeleton(resolved)
    c0_md = render_context_0(sk, generated="2026-11-01T00:00:00Z")
    c_steps.append(("read_context_0", c0_md))

    impact = analyze_impact(resolved, focal_target, skeleton=sk)
    impact_dict = asdict(impact)
    impact_json = json.dumps(impact_dict)
    c_steps.append(("ctx_impact", impact_json))

    cond_c_turns = len(c_steps)
    cond_c_tokens = sum(_approx_tokens(payload) for _, payload in c_steps)

    # Evaluate Condition C outputs against the static reference oracle (both recall and precision/F1)
    c_gov_set = set(impact.governing_docs)
    c_bdocs_found = {d for d in oracle.boundary_docs if d in c0_md or d in c_gov_set}
    c_arch_recall = _ratio(len(c_bdocs_found), len(oracle.boundary_docs))

    c_surf_found = sum(
        1 for (_k, tok, _f) in oracle.public_surfaces if _surface_present_in_texts(tok, [c0_md, impact_json])
    )
    c_surf_recall = _ratio(c_surf_found, len(oracle.public_surfaces))

    c_impact_prod = {rec["path"] for rec in impact.transitive_inbound_dependents if not rec["is_test"]}
    c_blast_recall, c_blast_prec, c_blast_f1 = _precision_and_f1(c_impact_prod, oracle.prod_transitive)

    c_impact_tests = {rec["path"] for rec in impact.coupled_tests}
    c_test_recall, c_test_prec, c_test_f1 = _precision_and_f1(c_impact_tests, oracle.coupled_tests)
    c_mean = (c_arch_recall + c_surf_recall + c_blast_recall + c_test_recall) / 4.0

    cond_c = ConditionMetrics(
        condition="tier2_plus_impact",
        tool_turns=cond_c_turns,
        context_tokens_read=cond_c_tokens,
        recall_arch_orientation=round(c_arch_recall, 4),
        recall_surface_discovery=round(c_surf_recall, 4),
        recall_blast_radius=round(c_blast_recall, 4),
        precision_blast_radius=round(c_blast_prec, 4),
        f1_blast_radius=round(c_blast_f1, 4),
        recall_coupled_tests=round(c_test_recall, 4),
        precision_coupled_tests=round(c_test_prec, 4),
        f1_coupled_tests=round(c_test_f1, 4),
        mean_recall=round(c_mean, 4),
        maint_llm_tokens_impl_commit=0,
        maint_llm_tokens_minor_struct_commit=0,
        maint_jev_tokens_minor_struct_commit=0,
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    repo_display_name = sk.repo_name
    git_entry = resolved / ".git"
    if git_entry.is_file():
        try:
            raw_git = git_entry.read_text(encoding="utf-8").strip()
            if raw_git.startswith("gitdir:"):
                gd = Path(raw_git.split(":", 1)[1].strip())
                if not gd.is_absolute():
                    gd = (resolved / gd).resolve()
                if gd.parent.name == "worktrees" and gd.parent.parent.name == ".git":
                    repo_display_name = gd.parent.parent.parent.name or repo_display_name
        except OSError:
            pass

    return RepoBenchmarkResult(
        repo_name=repo_display_name,
        repo_path=str(resolved),
        total_files=len(oracle.files),
        subsystems_count=len(sk.subsystems),
        internal_edges=oracle.internal_edge_count,
        operational_surfaces_count=len(oracle.public_surfaces),
        focal_target=focal_target,
        focal_direct_dependents=len(oracle.prod_direct),
        focal_transitive_dependents=len(oracle.prod_transitive),
        focal_coupled_tests=len(oracle.coupled_tests),
        elapsed_ms=elapsed_ms,
        conditions={
            "raw_grep": cond_a,
            "tier1_manifests": cond_b,
            "tier2_plus_impact": cond_c,
        },
    )


def run_navigation_benchmark(paths: list[Path]) -> dict[str, Any]:
    """Run the Phase 27.1 deterministic static-oracle A/B/C navigation benchmark."""
    if not paths:
        raise ValueError("At least one repository path is required for benchmarking.")

    repo_results = [benchmark_repository(p) for p in paths]
    cond_names = ("raw_grep", "tier1_manifests", "tier2_plus_impact")

    aggregates: dict[str, dict[str, Any]] = {}
    for cname in cond_names:
        metrics_list = [r.conditions[cname] for r in repo_results]
        n = len(metrics_list)
        aggregates[cname] = {
            "mean_tool_turns": round(sum(m.tool_turns for m in metrics_list) / n, 2),
            "mean_context_tokens_read": round(sum(m.context_tokens_read for m in metrics_list) / n, 1),
            "mean_recall": round(sum(m.mean_recall for m in metrics_list) / n, 4),
            "mean_arch_orientation_recall": round(sum(m.recall_arch_orientation for m in metrics_list) / n, 4),
            "mean_blast_radius_recall": round(sum(m.recall_blast_radius for m in metrics_list) / n, 4),
            "mean_blast_radius_precision": round(sum(m.precision_blast_radius for m in metrics_list) / n, 4),
            "mean_blast_radius_f1": round(sum(m.f1_blast_radius for m in metrics_list) / n, 4),
            "mean_surface_discovery_recall": round(sum(m.recall_surface_discovery for m in metrics_list) / n, 4),
            "mean_coupled_tests_recall": round(sum(m.recall_coupled_tests for m in metrics_list) / n, 4),
            "mean_coupled_tests_precision": round(sum(m.precision_coupled_tests for m in metrics_list) / n, 4),
            "mean_coupled_tests_f1": round(sum(m.f1_coupled_tests for m in metrics_list) / n, 4),
            "maint_llm_tokens_impl_commit": round(
                sum(m.maint_llm_tokens_impl_commit for m in metrics_list) / n, 1
            ),
            "maint_llm_tokens_minor_struct_commit": round(
                sum(m.maint_llm_tokens_minor_struct_commit for m in metrics_list) / n, 1
            ),
            "maint_jev_tokens_minor_struct_commit": round(
                sum(m.maint_jev_tokens_minor_struct_commit for m in metrics_list) / n, 1
            ),
        }

    raw_tok = aggregates["raw_grep"]["mean_context_tokens_read"] or 1.0
    c_tok = aggregates["tier2_plus_impact"]["mean_context_tokens_read"]
    raw_turns = aggregates["raw_grep"]["mean_tool_turns"] or 1.0
    c_turns = aggregates["tier2_plus_impact"]["mean_tool_turns"]

    return {
        "benchmark_version": "phase-27.1-v3-static-oracle-f1",
        "methodology": "deterministic_static_oracle_retrieval",
        "maintenance_cost_basis": "modeled_analytical_estimate",
        "generator": f"ctx/{__version__}",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repos_evaluated": len(repo_results),
        "summary": {
            "token_reduction_vs_raw_grep_pct": round((1.0 - (c_tok / raw_tok)) * 100.0, 1),
            "turn_reduction_vs_raw_grep_pct": round((1.0 - (c_turns / raw_turns)) * 100.0, 1),
            "recall_gain_vs_raw_grep_pct": round(
                (aggregates["tier2_plus_impact"]["mean_recall"] - aggregates["raw_grep"]["mean_recall"]) * 100.0,
                1,
            ),
            "blast_f1_gain_vs_raw_grep_pct": round(
                (aggregates["tier2_plus_impact"]["mean_blast_radius_f1"] - aggregates["raw_grep"]["mean_blast_radius_f1"])
                * 100.0,
                1,
            ),
            "aggregates": aggregates,
        },
        "repositories": [asdict(r) for r in repo_results],
    }


def render_benchmark_markdown(report: dict[str, Any]) -> str:
    """Render a reproducible GitHub-Flavored Markdown report for Phase 27.1 A/B/C benchmark results."""
    summary = report["summary"]
    aggs = summary["aggregates"]
    blast_f1_delta = summary.get(
        "blast_f1_gain_vs_raw_grep_pct",
        round(
            (aggs["tier2_plus_impact"].get("mean_blast_radius_f1", 0.0) - aggs["raw_grep"].get("mean_blast_radius_f1", 0.0))
            * 100.0,
            1,
        ),
    )
    lines = [
        "# Phase 27.1 — Deterministic Static-Oracle Navigation & Blast-Radius Benchmark",
        "",
        f"- **Generated:** `{report['generated']}`",
        f"- **Generator:** `{report['generator']}` (`{report['benchmark_version']}`)",
        f"- **Methodology:** `{report.get('methodology', 'deterministic_static_oracle_retrieval')}`",
        f"- **Maintenance Cost Basis:** `{report.get('maintenance_cost_basis', 'modeled_analytical_estimate')}`",
        f"- **Repositories Evaluated:** {report['repos_evaluated']}",
        "- **Reproduce:** `ctx benchmark <repo1> [repo2 ...] --out-file docs/benchmarks/phase27-1-navigation-benchmark.md`",
        "",
        "## Methodology & Scope",
        "",
        "This benchmark deterministically evaluates retrieval context-token efficiency, recall, precision, and F1 across "
        "three scripted retrieval workflows (`raw_grep`, `tier1_manifests`, and `tier2_plus_impact`) against a "
        "separate static AST/filesystem reference oracle built directly from raw files on disk:",
        "",
        "- **Condition A (`raw_grep`):** Lists the file tree, reads root docs (`README.md`, `AGENTS.md`, `CLAUDE.md`) plus "
        "up to 2 architecture/governance docs discovered in the file tree, reads candidate entrypoints and the focal module, "
        "and runs line-by-line regex grep (`\\b<stem>\\b`) over production and test files.",
        "- **Condition B (`tier1_manifests`):** Reads depth-0/1 `CONTEXT.md` manifests (`ctx export --depth 1`), reads the "
        "primary entrypoint, and runs symbol-augmented regex grep (`\\b(?:<stem>|<exported_symbols>)\\b`).",
        "- **Condition C (`tier2_plus_impact`):** Reads `.ctx/CONTEXT-0.md` and `ctx impact <focal_target> --output json`.",
        "",
        "**Scope Disclosures:** Both the reference oracle and `ctx.impact` evaluate static import graphs (measuring "
        "static-graph retrieval recall/precision vs lexical grep rather than dynamic runtime dispatch), and per-commit "
        "maintenance token figures in the rightmost column are **modeled analytical estimates** rather than live billing logs.",
        "",
        "## Executive Summary",
        "",
        f"Across **{report['repos_evaluated']}** repositories and **4** static-oracle retrieval dimensions "
        "(Authority & Architecture Orientation, Public Operational Surface Discovery, Multi-Hop Blast-Radius Tracing, "
        "and Coupled Test Selection), **Condition C (`tier2_plus_impact`: `.ctx/CONTEXT-0.md` + `ctx impact`)** achieves:",
        "",
        f"- **{summary['token_reduction_vs_raw_grep_pct']:.1f}% context-token reduction** vs `raw_grep` "
        f"(`{aggs['tier2_plus_impact']['mean_context_tokens_read']}` vs `{aggs['raw_grep']['mean_context_tokens_read']}` mean tokens)",
        f"- **{summary['turn_reduction_vs_raw_grep_pct']:.1f}% retrieval-step reduction** vs `raw_grep` "
        f"(`{aggs['tier2_plus_impact']['mean_tool_turns']}` vs `{aggs['raw_grep']['mean_tool_turns']}` mean steps)",
        f"- **{summary['recall_gain_vs_raw_grep_pct']:+.1f} percentage points static-oracle mean recall delta** "
        f"(`{aggs['tier2_plus_impact']['mean_recall']:.4f}` vs `{aggs['raw_grep']['mean_recall']:.4f}`) and "
        f"**{blast_f1_delta:+.1f} percentage points blast-radius F1 delta** "
        f"(`{aggs['tier2_plus_impact'].get('mean_blast_radius_f1', 0.0):.4f}` vs `{aggs['raw_grep'].get('mean_blast_radius_f1', 0.0):.4f}`)",
        f"- **0 LLM maintenance tokens** across both implementation-only commits and structural commits "
        f"(100% deterministic local AST & import-graph extraction)",
        "",
        "## Aggregate Condition Comparison",
        "",
        "| Condition | Mean Steps | Mean Context Tokens | Mean Recall | Blast Recall / Prec / F1 | Surface Recall | Modeled Maint. Tokens (Impl / Minor Struct) |",
        "|-----------|-----------:|--------------------:|------------:|-------------------------:|---------------:|--------------------------------------------:|",
    ]

    labels = {
        "raw_grep": "A. `raw_grep` (No `ctx`)",
        "tier1_manifests": "B. `tier1_manifests` (Per-dir `CONTEXT.md`)",
        "tier2_plus_impact": "C. `tier2_plus_impact` (`CONTEXT-0.md` + `ctx impact`)",
    }
    for key in ("raw_grep", "tier1_manifests", "tier2_plus_impact"):
        a = aggs[key]
        maint = f"{a['maint_llm_tokens_impl_commit']:.0f} / {a['maint_llm_tokens_minor_struct_commit']:.0f}"
        if a["maint_jev_tokens_minor_struct_commit"] > 0:
            maint += f" (+{a['maint_jev_tokens_minor_struct_commit']:.0f} Jev T1)"
        blast_triple = (
            f"{a['mean_blast_radius_recall']:.3f} / "
            f"{a.get('mean_blast_radius_precision', 0.0):.3f} / "
            f"{a.get('mean_blast_radius_f1', 0.0):.3f}"
        )
        lines.append(
            f"| {labels[key]} | {a['mean_tool_turns']:.2f} | {a['mean_context_tokens_read']:.1f} | "
            f"{a['mean_recall']:.4f} | {blast_triple} | "
            f"{a['mean_surface_discovery_recall']:.4f} | {maint} |"
        )

    lines.extend(["", "## Per-Repository Results", ""])
    for repo in report["repositories"]:
        lines.extend([
            f"### `{repo['repo_name']}` ({repo['total_files']} files, {repo['subsystems_count']} subsystems, {repo['internal_edges']} internal edges, {repo['operational_surfaces_count']} public surfaces)",
            "",
            f"- **Focal High-Fan-In Target:** `{repo['focal_target']}` "
            f"({repo['focal_direct_dependents']} direct prod dependents, "
            f"{repo['focal_transitive_dependents']} transitive prod dependents, "
            f"{repo['focal_coupled_tests']} coupled test suites)",
            "",
            "| Condition | Steps | Context Tokens | Arch Recall | Surface Recall | Blast R / P / F1 | Test R / P / F1 | Mean Recall |",
            "|-----------|------:|---------------:|------------:|---------------:|-----------------:|----------------:|------------:|",
        ])
        for key in ("raw_grep", "tier1_manifests", "tier2_plus_impact"):
            c = repo["conditions"][key]
            b_rpf = f"{c['recall_blast_radius']:.3f} / {c.get('precision_blast_radius', 0.0):.3f} / {c.get('f1_blast_radius', 0.0):.3f}"
            t_rpf = f"{c['recall_coupled_tests']:.3f} / {c.get('precision_coupled_tests', 0.0):.3f} / {c.get('f1_coupled_tests', 0.0):.3f}"
            lines.append(
                f"| `{key}` | {c['tool_turns']} | {c['context_tokens_read']} | "
                f"{c['recall_arch_orientation']:.4f} | {c['recall_surface_discovery']:.4f} | "
                f"{b_rpf} | {t_rpf} | "
                f"**{c['mean_recall']:.4f}** |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"
