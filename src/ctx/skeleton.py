"""Deterministic structural skeleton and architectural invariant extractor for ctx.

Extracts symbols, exports, cross-directory dependencies, entrypoints, and
authority/boundary documents (AGENTS.md, SYSTEM.md, README.md, architecture.md,
ADRs) with zero LLM calls. Computes structural_hash and boundary_doc_hash so LLM
synthesis or tiered index regeneration only triggers when structural signatures
or architectural boundary documents actually change.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ctx import __version__
from ctx.config import resolve_configured_extensions
from ctx.hasher import file_matches_extensions, normalize_extensions
from ctx.ignore import load_ignore_patterns, should_ignore
from ctx.language_detector import detect_language
from ctx.lang_parsers.python_parser import parse_python_file
from ctx.lang_parsers.js_ts_parser import parse_js_ts_file
from ctx.lang_parsers.rust_parser import parse_rust_file
from ctx.lang_parsers.go_parser import parse_go_file
from ctx.lang_parsers.java_parser import parse_java_file
from ctx.lang_parsers.csharp_parser import parse_csharp_file
from ctx.lang_parsers.kotlin_parser import parse_kotlin_file
from ctx.lang_parsers.ruby_parser import parse_ruby_file
from ctx.lang_parsers.php_parser import parse_php_file
from ctx.lang_parsers.swift_parser import parse_swift_file
from ctx.lang_parsers.elixir_parser import parse_elixir_file

_ALWAYS_SKIP_DIRS = frozenset({
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

_AUTHORITY_DOC_NAMES = {
    "agents.md": "authority",
    "system.md": "authority",
    "claude.md": "authority",
    "rules.md": "authority",
    "gate_closeout.md": "authority",
    "architecture.md": "architecture",
    "readme.md": "overview",
    "readme.rst": "overview",
    "state.md": "architecture",
    "todos.md": "architecture",
    "runbook.md": "architecture",
}

_ENTRYPOINT_FILENAMES = frozenset({
    "__main__.py",
    "cli.py",
    "main.py",
    "app.py",
    "server.py",
    "mcp_server.py",
    "api.py",
    "main.rs",
    "lib.rs",
    "main.go",
    "index.ts",
    "index.js",
    "server.ts",
    "server.js",
})

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)
_RUST_USE_RE = re.compile(r"^(?:pub\s+)?use\s+([a-zA-Z0-9_:]+)", re.MULTILINE)
_GO_IMPORT_SINGLE_RE = re.compile(r'^import\s+(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r"^import\s*\(([^)]*)\)", re.MULTILINE)
_GO_QUOTED_PKG_RE = re.compile(r'"([^"]+)"')
_JAVA_IMPORT_RE = re.compile(r"^import\s+(?:static\s+)?([a-zA-Z0-9_.*]+)\s*;", re.MULTILINE)
_KOTLIN_IMPORT_RE = re.compile(r"^import\s+([a-zA-Z0-9_.*]+)", re.MULTILINE)
_CSHARP_USING_RE = re.compile(
    r"^\s*(?:global\s+)?using\s+(?!var\b)(?:static\s+)?(?:[A-Za-z_]\w*\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)\s*;",
    re.MULTILINE,
)
_RUBY_REQUIRE_RE = re.compile(
    r"""^\s*(require_relative|require)\s*\(?\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_PHP_USE_RE = re.compile(
    r"^\s*use\s+(?:(?:function|const)\s+)?\\?([A-Za-z_][A-Za-z0-9_\\]*)(?:\s*\\\{([^}]+)\})?(?:\s+as\s+[A-Za-z_]\w*)?\s*;",
    re.MULTILINE,
)
_PHP_INCLUDE_RE = re.compile(
    r"""^\s*(?:require|require_once|include|include_once)\s*\(?\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_SWIFT_IMPORT_RE = re.compile(
    r"^import\s+(?:(?:struct|class|enum|protocol|typealias|func|var|let)\s+)?([A-Za-z_][A-Za-z0-9_.]*)",
    re.MULTILINE,
)
_ELIXIR_IMPORT_RE = re.compile(
    r"^\s*(?:alias|import|use|require)\s+([A-Z][A-Za-z0-9_.]*)",
    re.MULTILINE,
)
_PYPROJECT_SCRIPT_SECTION_RE = re.compile(r"^\[project\.scripts\]\s*$", re.MULTILINE)
_GO_MOD_MODULE_RE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
_CARGO_NAME_RE = re.compile(r'^name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

_PYTHON_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) | frozenset({"__future__", "builtins"})
_NODE_STDLIB = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring", "readline",
    "repl", "stream", "string_decoder", "sys", "timers", "tls", "trace_events",
    "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
})
_RUST_STDLIB = frozenset({"std", "core", "alloc", "proc_macro", "test"})
_OTHER_STDLIB_PREFIXES = (
    "java.", "javax.", "kotlin.",
)
_OTHER_STDLIB_EXACT = frozenset({
    "System", "Foundation", "Swift", "SwiftUI", "UIKit", "Combine", "Dispatch", "Logger",
})
_NON_OPERATIONAL_DIRS = frozenset({"tests", "test", "fixtures", "fixture", "examples", "benchmarks"})
_SKIP_SUMMARY_HEADINGS = frozenset({
    "schema_version", "version", "status", "table of contents", "contents", "toc", "license",
})
_TIER2_FOOTER = "<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->"


@dataclass(frozen=True)
class FileSkeleton:
    """Deterministic structural signature for a single source file."""

    relative_path: str
    language: str | None
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SubsystemSkeleton:
    """Aggregated structural and dependency view for a directory/subsystem."""

    path: str
    file_count: int
    languages: list[str] = field(default_factory=list)
    key_symbols: list[str] = field(default_factory=list)
    internal_deps: list[str] = field(default_factory=list)
    external_deps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BoundaryDoc:
    """Authority, governance, or architecture boundary document metadata."""

    relative_path: str
    kind: str  # "authority" | "architecture" | "overview"
    headings: list[str] = field(default_factory=list)
    summary_line: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class RepoSkeleton:
    """Complete deterministic repository structural & architectural skeleton."""

    root: str
    repo_name: str
    structural_hash: str
    boundary_doc_hash: str
    total_files: int
    languages: dict[str, int]
    entrypoints: list[str]
    boundary_docs: list[BoundaryDoc]
    subsystems: list[SubsystemSkeleton]
    files: list[FileSkeleton]


def _extract_symbols_for_file(path: Path, language: str | None) -> list[str]:
    if language is None:
        return []
    metadata: dict[str, Any] = {}
    if language == "Python":
        metadata = parse_python_file(path)
    elif language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
        metadata = parse_js_ts_file(path)
    elif language == "Rust":
        metadata = parse_rust_file(path)
    elif language == "Go":
        metadata = parse_go_file(path)
    elif language == "Java":
        metadata = parse_java_file(path)
    elif language == "C#":
        metadata = parse_csharp_file(path)
    elif language == "Kotlin":
        metadata = parse_kotlin_file(path)
    elif language == "Ruby":
        metadata = parse_ruby_file(path)
    elif language == "PHP":
        metadata = parse_php_file(path)
    elif language == "Swift":
        metadata = parse_swift_file(path)
    elif language == "Elixir":
        metadata = parse_elixir_file(path)

    symbols: list[str] = []
    prefix_map = [
        ("classes", "class"),
        ("structs", "struct"),
        ("interfaces", "interface"),
        ("traits", "trait"),
        ("enums", "enum"),
        ("records", "record"),
        ("types", "type"),
        ("modules", "mod"),
        ("functions", "fn"),
        ("methods", "method"),
        ("constants", "const"),
    ]
    for key, prefix in prefix_map:
        items = metadata.get(key)
        if not isinstance(items, list):
            continue
        for name in items:
            if not isinstance(name, str):
                continue
            # Filter private helper functions/classes starting with _ unless dunder
            if name.startswith("_") and not (name.startswith("__") and name.endswith("__")):
                continue
            symbols.append(f"{prefix} {name}")
    return symbols


def _extract_imports_for_file(path: Path, language: str | None) -> list[str]:
    if language is None:
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    imports: set[str] = set()
    if language == "Python":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name:
                            imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        prefix = "." * node.level
                        imports.add(f"{prefix}{node.module}")
                    elif node.level > 0:
                        imports.add("." * node.level)
        except SyntaxError:
            pass
    elif language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
        for match in _JS_IMPORT_RE.finditer(content):
            target = match.group(1) or match.group(2)
            if target:
                imports.add(target)
    elif language == "Rust":
        for match in _RUST_USE_RE.finditer(content):
            imports.add(match.group(1))
    elif language == "Go":
        for match in _GO_IMPORT_SINGLE_RE.finditer(content):
            imports.add(match.group(1))
        for block in _GO_IMPORT_BLOCK_RE.findall(content):
            for pkg in _GO_QUOTED_PKG_RE.findall(block):
                imports.add(pkg)
    elif language == "Java":
        for match in _JAVA_IMPORT_RE.finditer(content):
            imports.add(match.group(1))
    elif language == "Kotlin":
        for match in _KOTLIN_IMPORT_RE.finditer(content):
            imports.add(match.group(1))
    elif language == "C#":
        for match in _CSHARP_USING_RE.finditer(content):
            imports.add(match.group(1))
    elif language == "Ruby":
        for match in _RUBY_REQUIRE_RE.finditer(content):
            req_kind, target = match.group(1), match.group(2)
            if not target:
                continue
            if req_kind == "require_relative" and not target.startswith("."):
                imports.add(f"./{target}")
            else:
                imports.add(target)
    elif language == "PHP":
        for match in _PHP_USE_RE.finditer(content):
            base_ns, grouped = match.group(1), match.group(2)
            if grouped:
                ns_prefix = base_ns.rstrip("\\")
                for member in grouped.split(","):
                    cleaned = re.sub(r"\s+as\s+[A-Za-z_]\w*$", "", member.strip()).strip("\\ ")
                    if cleaned:
                        imports.add(f"{ns_prefix}\\{cleaned}")
            elif base_ns:
                imports.add(base_ns)
        for match in _PHP_INCLUDE_RE.finditer(content):
            target = match.group(1)
            if target:
                imports.add(target)
    elif language == "Swift":
        for match in _SWIFT_IMPORT_RE.finditer(content):
            imports.add(match.group(1))
    elif language == "Elixir":
        for match in _ELIXIR_IMPORT_RE.finditer(content):
            imports.add(match.group(1))

    return sorted(imports)


def _is_meaningful_summary_line(stripped: str, current_heading: str) -> bool:
    if current_heading.strip().lower() in _SKIP_SUMMARY_HEADINGS:
        return False
    if stripped.startswith(("<!--", "|", "-", "*", ">", "[![", "![")):
        return False
    # Skip bare numbers / version tokens like "1" or "1.0.0"
    if re.fullmatch(r"v?\d+(?:\.\d+)*", stripped):
        return False
    return True


def _extract_markdown_headings_and_summary(path: Path) -> tuple[list[str], str, str]:
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8", errors="replace")
    except OSError:
        return [], "", ""

    content_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    headings: list[str] = []
    summary_line = ""
    current_heading = ""
    in_frontmatter = False
    in_code_block = False

    for idx, raw_line in enumerate(content.splitlines()):
        stripped = raw_line.strip()
        if idx == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped:
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            current_heading = title
            if title and level <= 2:
                headings.append(title)
            continue
        if not summary_line and _is_meaningful_summary_line(stripped, current_heading):
            summary_line = stripped[:160]

    return headings[:12], summary_line, content_hash


def _classify_boundary_doc(rel_posix: str) -> str | None:
    lower = rel_posix.lower()
    name = Path(lower).name
    if name == "context.md" or lower.startswith(".ctx/"):
        return None
    if lower in _AUTHORITY_DOC_NAMES:
        return _AUTHORITY_DOC_NAMES[lower]
    if name in _AUTHORITY_DOC_NAMES and "/" not in lower:
        return _AUTHORITY_DOC_NAMES[name]
    if (
        lower.startswith("docs/adr/")
        or lower.startswith("docs/designs/")
        or lower.startswith("adr/")
    ) and lower.endswith(".md"):
        return "architecture"
    return None


def resolve_cli_entrypoint_target(root: Path, ep_target: str) -> str | None:
    """Resolve a `[project.scripts]` `module.path:callable` target to a repo-relative file path if present."""
    module_name = ep_target.split(":", 1)[0].strip()
    if not module_name:
        return None
    mod_rel = module_name.replace(".", "/")
    resolved_root = root.resolve()
    for rel_candidate in (
        f"src/{mod_rel}.py",
        f"src/{mod_rel}/__init__.py",
        f"{mod_rel}.py",
        f"{mod_rel}/__init__.py",
    ):
        cand = (resolved_root / rel_candidate).resolve()
        if cand.is_file() and cand.is_relative_to(resolved_root):
            return cand.relative_to(resolved_root).as_posix()
    return None


def _is_valid_config_target_file(
    root: Path,
    raw_target: str,
    effective_exts: set[str] | None,
    spec: object | None,
    max_depth: int | None,
) -> bool:
    cleaned = raw_target.strip().lstrip("./")
    if not cleaned:
        return False
    resolved_root = root.resolve()
    target_path = (resolved_root / cleaned).resolve()
    if not (target_path.is_file() and target_path.is_relative_to(resolved_root)):
        return False
    rel_parts = target_path.relative_to(resolved_root).parts
    if any(
        part.lower() in _NON_OPERATIONAL_DIRS or part in _ALWAYS_SKIP_DIRS
        for part in rel_parts[:-1]
    ):
        return False
    if spec is not None and should_ignore(target_path, spec, resolved_root):
        return False
    if not file_matches_extensions(target_path, effective_exts):
        return False
    if max_depth is not None and (len(rel_parts) - 1) > max_depth:
        return False
    return True


def _detect_config_entrypoints(
    root: Path,
    effective_exts: set[str] | None = None,
    *,
    spec: object | None = None,
    max_depth: int | None = None,
) -> list[str]:
    entrypoints: list[str] = []
    resolved_root = root.resolve()

    pyproject = resolved_root / "pyproject.toml"
    if (
        pyproject.is_file()
        and file_matches_extensions(pyproject, effective_exts)
        and not (spec is not None and should_ignore(pyproject, spec, resolved_root))
    ):
        try:
            text = pyproject.read_text(encoding="utf-8")
            match = _PYPROJECT_SCRIPT_SECTION_RE.search(text)
            if match:
                rest = text[match.end() :]
                for line in rest.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("["):
                        break
                    if "=" in stripped and not stripped.startswith("#"):
                        k, v = stripped.split("=", 1)
                        cleaned_val = v.strip().strip("\"'")
                        module_name = cleaned_val.split(":", 1)[0].strip()
                        if any(
                            seg.lower() in _NON_OPERATIONAL_DIRS
                            for seg in module_name.split(".")
                            if seg
                        ):
                            continue
                        resolved_cli_rel = resolve_cli_entrypoint_target(resolved_root, cleaned_val)
                        if resolved_cli_rel is not None and not _is_valid_config_target_file(
                            resolved_root, resolved_cli_rel, effective_exts, spec, max_depth
                        ):
                            continue
                        entrypoints.append(f"cli:{k.strip()} -> {cleaned_val}")
        except (OSError, UnicodeDecodeError):
            pass

    pkg_json = resolved_root / "package.json"
    if (
        pkg_json.is_file()
        and file_matches_extensions(pkg_json, effective_exts)
        and not (spec is not None and should_ignore(pkg_json, spec, resolved_root))
    ):
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            if isinstance(pkg, dict):
                main_val = pkg.get("main")
                if isinstance(main_val, str) and main_val.strip():
                    target = main_val.strip()
                    if _is_valid_config_target_file(
                        resolved_root, target, effective_exts, spec, max_depth
                    ):
                        entrypoints.append(f"npm:main -> {target}")
                bin_val = pkg.get("bin")
                if isinstance(bin_val, str) and bin_val.strip():
                    target = bin_val.strip()
                    if _is_valid_config_target_file(
                        resolved_root, target, effective_exts, spec, max_depth
                    ):
                        entrypoints.append(f"npm:bin -> {target}")
                elif isinstance(bin_val, dict):
                    for k, v in sorted(bin_val.items()):
                        if isinstance(v, str) and v.strip():
                            target = v.strip()
                            if _is_valid_config_target_file(
                                resolved_root, target, effective_exts, spec, max_depth
                            ):
                                entrypoints.append(f"npm:bin:{k} -> {target}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass

    return entrypoints


def _strip_jsonc(raw: str) -> str:
    """Strip // line comments, /* */ block comments, and trailing commas from JSONC text."""
    # Remove comments outside quoted strings
    token_re = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/')
    without_comments = token_re.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", raw)
    return re.sub(r",\s*([}\]])", r"\1", without_comments)


def _detect_repo_module_prefixes(root: Path) -> tuple[set[str], list[str]]:
    """Detect internal module root names and multi-segment prefixes (go.mod, Cargo.toml, tsconfig/jsconfig)."""
    roots: set[str] = {"crate", "super", "self"}
    prefixes: list[str] = []

    go_mod = root / "go.mod"
    if go_mod.is_file():
        try:
            match = _GO_MOD_MODULE_RE.search(go_mod.read_text(encoding="utf-8"))
            if match:
                mod_path = match.group(1).strip()
                if mod_path:
                    prefixes.append(mod_path)
        except (OSError, UnicodeDecodeError):
            pass

    cargo_toml = root / "Cargo.toml"
    if cargo_toml.is_file():
        try:
            match = _CARGO_NAME_RE.search(cargo_toml.read_text(encoding="utf-8"))
            if match:
                crate_name = match.group(1).strip().replace("-", "_")
                if crate_name:
                    roots.add(crate_name)
        except (OSError, UnicodeDecodeError):
            pass

    for ts_cfg_name in ("tsconfig.json", "jsconfig.json"):
        ts_cfg = root / ts_cfg_name
        if not ts_cfg.is_file():
            continue
        try:
            parsed = json.loads(_strip_jsonc(ts_cfg.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        compiler_opts = parsed.get("compilerOptions")
        if not isinstance(compiler_opts, dict):
            continue
        paths_map = compiler_opts.get("paths")
        if not isinstance(paths_map, dict):
            continue
        for raw_alias in sorted(paths_map.keys()):
            if not isinstance(raw_alias, str):
                continue
            alias = raw_alias.strip()
            if not alias or alias == "*":
                continue
            if alias.endswith("/*"):
                base_alias = alias[:-2].rstrip("/")
                if base_alias:
                    prefixes.append(base_alias)
            elif "*" not in alias:
                prefixes.append(alias.rstrip("/"))

    return roots, sorted(dict.fromkeys(prefixes))


def _classify_dependency(
    imp: str,
    language: str | None,
    internal_module_roots: set[str],
    internal_prefixes: list[str],
) -> tuple[str | None, str]:
    """Classify an import string as ('internal', name), ('external', pkg), or (None, '') for stdlib."""
    if not imp:
        return None, ""

    if imp.startswith((".", "@/", "~/", "#/")):
        return "internal", imp

    for prefix in internal_prefixes:
        if imp == prefix or imp.startswith(f"{prefix}/"):
            return "internal", imp

    if language == "Go":
        first_seg = imp.split("/")[0]
        if "." not in first_seg:
            return None, ""  # Go standard library (e.g., fmt, net/http, encoding/json)
        parts = imp.split("/")
        pkg = "/".join(parts[:3]) if len(parts) >= 3 else imp
        return "external", pkg

    if language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
        if imp.startswith("node:"):
            return None, ""
        if imp.startswith("@"):
            parts = imp.split("/")
            pkg = f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else imp
            return "external", pkg
        top_mod = imp.split("/")[0]
        if top_mod in _NODE_STDLIB:
            return None, ""
        if top_mod in internal_module_roots:
            return "internal", imp
        return ("external", top_mod) if top_mod else (None, "")

    if language == "Python":
        top_mod = imp.split(".")[0]
        if top_mod in internal_module_roots:
            return "internal", imp
        if top_mod in _PYTHON_STDLIB:
            return None, ""
        return ("external", top_mod) if top_mod else (None, "")

    if language == "Rust":
        top_mod = imp.split("::")[0]
        if top_mod in internal_module_roots:
            return "internal", imp
        if top_mod in _RUST_STDLIB:
            return None, ""
        return ("external", top_mod) if top_mod else (None, "")

    if any(imp.startswith(p) for p in _OTHER_STDLIB_PREFIXES):
        return None, ""
    top_mod = imp.split(".")[0].split("/")[0].split("::")[0].split("\\")[0]
    if top_mod in _OTHER_STDLIB_EXACT:
        return None, ""
    if top_mod in internal_module_roots:
        return "internal", imp
    return ("external", top_mod) if top_mod else (None, "")


def _select_diversified_key_symbols(sfiles: list[FileSkeleton], limit: int = 25) -> list[str]:
    """Select key symbols round-robin across subsystem files, prioritizing operational entrypoints."""
    def _file_priority(f: FileSkeleton) -> tuple[int, str]:
        fname = Path(f.relative_path).name
        is_entry = 0 if fname in _ENTRYPOINT_FILENAMES else 1
        return (is_entry, f.relative_path)

    ranked_files = [f for f in sorted(sfiles, key=_file_priority) if f.symbols]
    selected: list[str] = []
    idx = 0
    while len(selected) < limit and ranked_files:
        progressed = False
        for f in ranked_files:
            if idx < len(f.symbols):
                selected.append(f"{Path(f.relative_path).name}:{f.symbols[idx]}")
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return selected


def extract_skeleton(
    root: Path,
    *,
    max_depth: int | None = None,
    extensions: list[str] | None = None,
) -> RepoSkeleton:
    """Deterministically scan a repository tree and build a RepoSkeleton with zero LLM calls."""
    root = root.resolve()
    spec = load_ignore_patterns(root)
    effective_exts = normalize_extensions(
        extensions if extensions is not None else resolve_configured_extensions(root)
    )

    file_skeletons: list[FileSkeleton] = []
    boundary_docs: list[BoundaryDoc] = []
    lang_counts: Counter[str] = Counter()
    entrypoints: list[str] = _detect_config_entrypoints(
        root, effective_exts, spec=spec, max_depth=max_depth
    )

    # Track internal module names for dependency classification
    internal_module_roots, internal_prefixes = _detect_repo_module_prefixes(root)

    def _walk(current: Path, depth: int) -> None:
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            return

        for entry in entries:
            if entry.name in _ALWAYS_SKIP_DIRS:
                continue
            if entry.name in ("CONTEXT.md", ".ctx-hook.pid", ".ctx-lock", ".ctxconfig", ".ctxignore", ".gitignore"):
                continue
            if should_ignore(entry, spec, root):
                continue

            if entry.is_dir():
                if max_depth is None or depth < max_depth:
                    _walk(entry, depth + 1)
                continue

            if not entry.is_file():
                continue

            if not file_matches_extensions(entry, effective_exts):
                continue

            rel_posix = entry.relative_to(root).as_posix()
            rel_parts = entry.relative_to(root).parts

            # Check boundary doc
            doc_kind = _classify_boundary_doc(rel_posix)
            if doc_kind is not None:
                headings, summary_line, chash = _extract_markdown_headings_and_summary(entry)
                boundary_docs.append(
                    BoundaryDoc(
                        relative_path=rel_posix,
                        kind=doc_kind,
                        headings=headings,
                        summary_line=summary_line,
                        content_hash=chash,
                    )
                )

            if (
                entry.name in _ENTRYPOINT_FILENAMES
                and not any(part.lower() in _NON_OPERATIONAL_DIRS for part in rel_parts[:-1])
            ):
                entrypoints.append(f"file:{rel_posix}")

            language = detect_language(entry)
            if language:
                lang_counts[language] += 1
                if language == "Python":
                    if len(rel_parts) >= 2 and rel_parts[0] == "src":
                        internal_module_roots.add(rel_parts[1].removesuffix(".py"))
                    elif rel_parts[0].lower() not in _NON_OPERATIONAL_DIRS:
                        internal_module_roots.add(rel_parts[0].removesuffix(".py"))

            symbols = _extract_symbols_for_file(entry, language)
            imports = _extract_imports_for_file(entry, language)
            file_skeletons.append(
                FileSkeleton(
                    relative_path=rel_posix,
                    language=language,
                    symbols=symbols,
                    imports=imports,
                )
            )

    _walk(root, 0)

    file_skeletons.sort(key=lambda f: f.relative_path)
    boundary_docs.sort(key=lambda d: d.relative_path)
    entrypoints = sorted(dict.fromkeys(entrypoints))

    # Group files into logical subsystems (top 2 directory levels for src/*, else top 1)
    subsystem_files: dict[str, list[FileSkeleton]] = defaultdict(list)
    for f in file_skeletons:
        parts = Path(f.relative_path).parts
        if len(parts) == 1:
            sub_key = "."
        elif parts[0] == "src" and len(parts) >= 3:
            sub_key = f"{parts[0]}/{parts[1]}" if len(parts) == 3 else f"{parts[0]}/{parts[1]}/{parts[2]}"
        else:
            sub_key = parts[0]
        subsystem_files[sub_key].append(f)

    subsystems: list[SubsystemSkeleton] = []
    for sub_path in sorted(subsystem_files.keys()):
        sfiles = subsystem_files[sub_path]
        sub_langs = Counter(f.language for f in sfiles if f.language)
        ordered_langs = [lang for lang, _ in sub_langs.most_common()]
        symbols_flat = _select_diversified_key_symbols(sfiles, limit=25)
        internal_deps: set[str] = set()
        external_deps: set[str] = set()

        for f in sfiles:
            for imp in f.imports:
                dep_kind, dep_name = _classify_dependency(
                    imp, f.language, internal_module_roots, internal_prefixes
                )
                if dep_kind == "internal":
                    internal_deps.add(dep_name)
                elif dep_kind == "external":
                    external_deps.add(dep_name)

        subsystems.append(
            SubsystemSkeleton(
                path=sub_path,
                file_count=len(sfiles),
                languages=ordered_langs,
                key_symbols=symbols_flat,
                internal_deps=sorted(internal_deps)[:15],
                external_deps=sorted(external_deps)[:15],
            )
        )

    # Compute deterministic structural_hash (module prefixes/roots + paths + symbols + imports + entrypoints)
    struct_hasher = hashlib.sha256()
    if internal_module_roots:
        struct_hasher.update(f"roots:{','.join(sorted(internal_module_roots))}\n".encode("utf-8"))
    if internal_prefixes:
        struct_hasher.update(f"prefixes:{','.join(sorted(internal_prefixes))}\n".encode("utf-8"))
    for ep in entrypoints:
        struct_hasher.update(f"ep:{ep}\n".encode("utf-8"))
    for f in file_skeletons:
        struct_hasher.update(
            f"file:{f.relative_path}|lang:{f.language or ''}|sym:{','.join(f.symbols)}|imp:{','.join(f.imports)}\n".encode(
                "utf-8"
            )
        )
    structural_hash = f"sha256:{struct_hasher.hexdigest()}"

    # Compute deterministic boundary_doc_hash
    bdoc_hasher = hashlib.sha256()
    for doc in boundary_docs:
        bdoc_hasher.update(f"doc:{doc.relative_path}|{doc.kind}|{doc.content_hash}\n".encode("utf-8"))
    boundary_doc_hash = f"sha256:{bdoc_hasher.hexdigest()}"

    return RepoSkeleton(
        root=str(root),
        repo_name=root.name or "repo",
        structural_hash=structural_hash,
        boundary_doc_hash=boundary_doc_hash,
        total_files=len(file_skeletons),
        languages=dict(lang_counts.most_common()),
        entrypoints=entrypoints,
        boundary_docs=boundary_docs,
        subsystems=subsystems,
        files=file_skeletons,
    )


def should_invoke_llm(prev_metadata: dict[str, Any] | None, skeleton: RepoSkeleton) -> bool:
    """Return True only when structural signatures or authority/boundary docs changed."""
    if not prev_metadata or not isinstance(prev_metadata, dict):
        return True
    prev_struct = prev_metadata.get("structural_hash")
    prev_bdoc = prev_metadata.get("boundary_doc_hash")
    if not prev_struct or not prev_bdoc:
        return True
    return (
        prev_struct != skeleton.structural_hash
        or prev_bdoc != skeleton.boundary_doc_hash
    )


def _render_frontmatter(skeleton: RepoSkeleton, tier: str, *, generated: str | None = None) -> str:
    ts = generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "\n".join([
        "---",
        f'generated: "{ts}"',
        f"generator: ctx/{__version__}",
        "mode: tier2",
        f"tier: {tier}",
        f'structural_hash: "{skeleton.structural_hash}"',
        f'boundary_doc_hash: "{skeleton.boundary_doc_hash}"',
        f"files: {skeleton.total_files}",
        f"subsystems: {len(skeleton.subsystems)}",
        "---",
    ])


def render_context_0(skeleton: RepoSkeleton, *, generated: str | None = None) -> str:
    """Render CONTEXT-0.md: 1-page repo architecture, authority boundaries, & entrypoints."""
    lines = [
        _render_frontmatter(skeleton, "CONTEXT-0", generated=generated),
        "",
        f"# {skeleton.repo_name} — Architecture & Authority Map (CONTEXT-0)",
        "",
    ]

    lang_summary = ", ".join(f"{lang} ({count})" for lang, count in skeleton.languages.items()) or "None detected"
    lines.append(f"**Files:** {skeleton.total_files} | **Subsystems:** {len(skeleton.subsystems)} | **Languages:** {lang_summary}")
    lines.append("")

    lines.append("## Authority Boundaries & Governance")
    if skeleton.boundary_docs:
        for doc in skeleton.boundary_docs:
            headings_str = f" — Sections: {', '.join(doc.headings[:6])}" if doc.headings else ""
            summary_str = f" ({doc.summary_line})" if doc.summary_line else ""
            lines.append(f"- **{doc.relative_path}** [`{doc.kind}`]{summary_str}{headings_str}")
    else:
        lines.append("- None detected")
    lines.append("")

    lines.append("## Entrypoints & Operational Surfaces")
    if skeleton.entrypoints:
        for ep in skeleton.entrypoints:
            lines.append(f"- `{ep}`")
    else:
        lines.append("- None detected")
    lines.append("")

    lines.append("## Subsystem Overview")
    lines.append("| Subsystem | Files | Languages | Key Exports |")
    lines.append("|-----------|------:|-----------|-------------|")
    for sub in skeleton.subsystems:
        langs = ", ".join(sub.languages[:3]) or "-"
        exports = ", ".join(f"`{s}`" for s in sub.key_symbols[:4]) or "-"
        lines.append(f"| `{sub.path}` | {sub.file_count} | {langs} | {exports} |")
    lines.append("")
    lines.append("<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->")
    return "\n".join(lines) + "\n"


def render_context_1(skeleton: RepoSkeleton, *, generated: str | None = None) -> str:
    """Render CONTEXT-1.md: Subsystem dependency flows, exported symbols & invariant map."""
    lines = [
        _render_frontmatter(skeleton, "CONTEXT-1", generated=generated),
        "",
        f"# {skeleton.repo_name} — Module Dependency & Invariant Map (CONTEXT-1)",
        "",
        "## Cross-Directory Dependency & Export Map",
        "",
    ]

    for sub in skeleton.subsystems:
        lines.append(f"### `{sub.path}` ({sub.file_count} files)")
        if sub.internal_deps:
            lines.append(f"- **Internal imports:** {', '.join(f'`{d}`' for d in sub.internal_deps)}")
        if sub.external_deps:
            lines.append(f"- **External packages:** {', '.join(f'`{d}`' for d in sub.external_deps)}")
        if sub.key_symbols:
            lines.append(f"- **Exported symbols:** {', '.join(f'`{s}`' for s in sub.key_symbols[:12])}")
        if not (sub.internal_deps or sub.external_deps or sub.key_symbols):
            lines.append("- Structural leaf / configuration assets")
        lines.append("")

    lines.append("## Architectural Invariants & Boundary Contracts")
    authority_docs = [d for d in skeleton.boundary_docs if d.kind in ("authority", "architecture")]
    if authority_docs:
        for doc in authority_docs:
            lines.append(f"- **{doc.relative_path}** (`{doc.content_hash[:19]}…`): {', '.join(doc.headings) or doc.summary_line or 'Contract document'}")
    else:
        lines.append("- No explicit authority/invariant contract files (`AGENTS.md`, `SYSTEM.md`, `architecture.md`) found.")
    lines.append("")
    lines.append("<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->")
    return "\n".join(lines) + "\n"


def strip_tier2_chrome(markdown_text: str, *, strip_footer: bool = True) -> str:
    """Strip YAML frontmatter (--- ... ---) and optional generated footer by delimiter matching."""
    text = markdown_text
    if text.startswith("---\n"):
        end_idx = text.find("\n---\n", 4)
        if end_idx != -1:
            text = text[end_idx + 5 :].lstrip("\n")
    if strip_footer:
        text = text.rstrip()
        if text.endswith(_TIER2_FOOTER):
            text = text[: -len(_TIER2_FOOTER)].rstrip()
    return text


def render_context_full(skeleton: RepoSkeleton, *, generated: str | None = None) -> str:
    """Render CONTEXT.md: Full architectural synthesis + file-level deterministic signatures."""
    ts = generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    c0 = render_context_0(skeleton, generated=ts)
    c1_body = strip_tier2_chrome(render_context_1(skeleton, generated=ts), strip_footer=True)

    file_lines = ["## File-Level Structural Signatures", ""]
    for f in skeleton.files:
        if not f.symbols and not f.imports:
            continue
        sym_part = f"exports: {', '.join(f'`{s}`' for s in f.symbols[:10])}" if f.symbols else ""
        imp_part = f"imports: {', '.join(f'`{i}`' for i in f.imports[:8])}" if f.imports else ""
        sep = " | " if (sym_part and imp_part) else ""
        file_lines.append(f"- **{f.relative_path}** — {sym_part}{sep}{imp_part}")
    if len(file_lines) == 2:
        file_lines.append("- None")

    base = c0.removesuffix(f"{_TIER2_FOOTER}\n")
    return (
        base
        + "\n"
        + c1_body
        + "\n\n"
        + "\n".join(file_lines)
        + f"\n\n{_TIER2_FOOTER}\n"
    )
