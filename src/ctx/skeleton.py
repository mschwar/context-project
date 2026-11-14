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
from ctx.config import load_config
from ctx.hasher import file_matches_extensions, normalize_extensions
from ctx.ignore import load_ignore_patterns, should_ignore
from ctx.language_detector import detect_language
from ctx.lang_parsers.c_cpp_parser import parse_c_cpp_file
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
_C_CPP_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*([<"])([^>"]+)[>"]',
    re.MULTILINE,
)
_C_CPP_STDLIB = frozenset({
    "assert.h", "complex.h", "ctype.h", "errno.h", "fenv.h", "float.h", "inttypes.h",
    "iso646.h", "limits.h", "locale.h", "math.h", "setjmp.h", "signal.h", "stdalign.h",
    "stdarg.h", "stdatomic.h", "stdbool.h", "stddef.h", "stdint.h", "stdio.h", "stdlib.h",
    "stdnoreturn.h", "string.h", "tgmath.h", "threads.h", "time.h", "uchar.h", "wchar.h",
    "wctype.h", "unistd.h", "fcntl.h", "pthread.h", "dlfcn.h", "dirent.h", "netdb.h",
    "poll.h", "sched.h", "semaphore.h", "strings.h", "syslog.h", "termios.h", "sys",
    "arpa", "netinet", "windows.h", "winsock2.h",
    "algorithm", "any", "array", "atomic", "barrier", "bit", "bitset", "cassert", "cctype",
    "cerrno", "cfenv", "cfloat", "charconv", "chrono", "cinttypes", "climits", "clocale",
    "cmath", "codecvt", "compare", "complex", "concepts", "condition_variable", "coroutine",
    "csetjmp", "csignal", "cstdarg", "cstddef", "cstdint", "cstdio", "cstdlib", "cstring",
    "ctime", "cuchar", "cwchar", "cwctype", "deque", "exception", "execution", "expected",
    "filesystem", "format", "forward_list", "fstream", "functional", "future",
    "initializer_list", "iomanip", "ios", "iosfwd", "iostream", "istream", "iterator",
    "latch", "limits", "list", "locale", "map", "memory", "memory_resource", "mutex", "new",
    "numbers", "numeric", "optional", "ostream", "print", "queue", "random", "ranges",
    "ratio", "regex", "scoped_allocator", "semaphore", "set", "shared_mutex", "source_location",
    "span", "spanstream", "sstream", "stack", "stacktrace", "stdexcept", "stdfloat",
    "stop_token", "streambuf", "string", "string_view", "strstream", "syncstream",
    "system_error", "thread", "tuple", "type_traits", "typeindex", "typeinfo",
    "unordered_map", "unordered_set", "utility", "valarray", "variant", "vector", "version",
})
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
_OS_ENV_NOISE = frozenset({
    "PATH", "HOME", "USER", "USERNAME", "LOGNAME", "SHELL", "TERM", "PWD", "OLDPWD",
    "TMPDIR", "TEMP", "TMP", "PATHEXT", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
    "SYSTEMROOT", "COMSPEC", "WINDIR", "LANG", "LC_ALL", "COLUMNS", "LINES", "CI",
})
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
_JS_HTTP_ROUTE_RE = re.compile(
    r"""\b(?:app|router|server|fastify|hono)\.(get|post|put|delete|patch)\(\s*['"](/[^'"]*)['"]""",
    re.MULTILINE,
)
_JS_MCP_TOOL_RE = re.compile(
    r"""\b(?:server|mcp)\.tool\(\s*['"]([a-zA-Z0-9_.-]+)['"]""",
    re.MULTILINE,
)
_JS_ENV_RE = re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]{2,})\b")
_GO_HTTP_ROUTE_ANY_RE = re.compile(
    r"""\b(?:(http|mux)\.HandleFunc|(?:r|router|group|e)\.(Get|Post|Put|Delete|Patch|GET|POST|PUT|DELETE|PATCH))\(\s*"(?:(GET|POST|PUT|DELETE|PATCH)\s+)?(/[^"]*)"\s*,""",
)
_GO_ENV_RE = re.compile(r"""\bos\.(?:Getenv|LookupEnv)\(\s*"([A-Z][A-Z0-9_]{2,})"\s*\)""")
_RUST_ATTR_ROUTE_RE = re.compile(r"""#\[(get|post|put|delete|patch)\(\s*"(/[^"]*)"\s*\)\]""")
_RUST_AXUM_ROUTE_RE = re.compile(r"""\.route\(\s*"(/[^"]*)"\s*,\s*(get|post|put|delete|patch)\b""")
_RUST_ENV_RE = re.compile(r"""\benv::var\(\s*"([A-Z][A-Z0-9_]{2,})"\s*\)""")
_IDENT_TOKEN_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_SKIP_SUMMARY_HEADINGS = frozenset({
    "schema_version", "version", "status", "table of contents", "contents", "toc", "license",
})
_TIER2_FOOTER = "<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->"


@dataclass(frozen=True)
class OperationalSurface:
    """Deterministic operational surface extracted from source code."""

    kind: str  # "cli_command" | "http_route" | "mcp_tool" | "mcp_resource" | "env_var"
    name: str
    file: str
    detail: str = ""


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
    arch_role: str = ""


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
    operational_surfaces: list[OperationalSurface] = field(default_factory=list)


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
    elif language in ("C", "C++", "C/C++ Header", "C++ Header"):
        metadata = parse_c_cpp_file(path)

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
    elif language in ("C", "C++", "C/C++ Header", "C++ Header"):
        for match in _C_CPP_INCLUDE_RE.finditer(content):
            delim, header = match.group(1), match.group(2).strip()
            if not header:
                continue
            if delim == '"':
                imports.add(header if header.startswith(".") else f"./{header}")
            else:
                imports.add(header)

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
    parts = Path(lower).parts
    name = Path(lower).name
    if name == "context.md" or lower.startswith(".ctx/"):
        return None
    if any(seg in {"archive", "tests", "test", "fixtures", "fixture", "benchmarks"} for seg in parts[:-1]):
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
    segments = module_name.split(".")
    if not all(seg and seg.isidentifier() for seg in segments):
        return None
    mod_rel = "/".join(segments)
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


def resolve_config_target_path(root: Path, raw_target: str) -> Path | None:
    """Resolve a relative package/config entrypoint target safely inside *root* without stripping '../' or '.bin/'."""
    cleaned = raw_target.strip()
    if not cleaned:
        return None
    raw_path = Path(cleaned)
    if raw_path.is_absolute():
        return None
    resolved_root = root.resolve()
    try:
        target_path = (resolved_root / raw_path).resolve()
    except OSError:
        return None
    if not (target_path.is_file() and target_path.is_relative_to(resolved_root)):
        return None
    return target_path


def _is_valid_config_target_file(
    root: Path,
    raw_target: str,
    effective_exts: set[str] | None,
    spec: object | None,
    max_depth: int | None,
) -> bool:
    target_path = resolve_config_target_path(root, raw_target)
    if target_path is None:
        return False
    resolved_root = root.resolve()
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
                        mod_segments = module_name.split(".")
                        if not module_name or not all(seg and seg.isidentifier() for seg in mod_segments):
                            continue
                        if any(
                            seg.lower() in _NON_OPERATIONAL_DIRS
                            for seg in mod_segments
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

    if language in ("C", "C++", "C/C++ Header", "C++ Header"):
        norm_hdr = imp.replace("\\", "/").strip("/")
        top_hdr = norm_hdr.split("/")[0]
        if norm_hdr in _C_CPP_STDLIB or top_hdr in _C_CPP_STDLIB:
            return None, ""
        if top_hdr in internal_module_roots:
            return "internal", imp
        pkg = top_hdr.removesuffix(".h").removesuffix(".hpp")
        return ("external", pkg) if pkg else (None, "")

    if any(imp.startswith(p) for p in _OTHER_STDLIB_PREFIXES):
        return None, ""
    top_mod = imp.split(".")[0].split("/")[0].split("::")[0].split("\\")[0]
    if top_mod in _OTHER_STDLIB_EXACT:
        return None, ""
    if top_mod in internal_module_roots:
        return "internal", imp
    return ("external", top_mod) if top_mod else (None, "")


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_receiver_and_method(func: ast.AST) -> tuple[str, str]:
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return func.value.id, func.attr
        if isinstance(func.value, ast.Attribute):
            return func.value.attr, func.attr
        return "", func.attr
    if isinstance(func, ast.Name):
        return "", func.id
    return "", ""


def _dict_literal_entries(node: ast.Dict) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for k_node, v_node in zip(node.keys, node.values):
        k_str = _const_str(k_node)
        if k_str is not None and v_node is not None:
            out[k_str] = v_node
    return out


def _is_test_or_non_operational_file(rel_posix: str) -> bool:
    rel_path = Path(rel_posix)
    if any(part.lower() in _NON_OPERATIONAL_DIRS for part in rel_path.parts[:-1]):
        return True
    lower_name = rel_path.name.lower()
    if lower_name.startswith("test_") or lower_name.endswith(
        ("_test.py", "_test.go", "_test.rs", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js")
    ):
        return True
    return False


def _record_env_key(
    key: str | None,
    rel_posix: str,
    seen: set[tuple[str, str, str]],
    surfaces: list[OperationalSurface],
) -> None:
    if not key or not _ENV_KEY_RE.match(key) or key in _OS_ENV_NOISE:
        return
    sig = ("env_var", key, rel_posix)
    if sig not in seen:
        seen.add(sig)
        surfaces.append(OperationalSurface(kind="env_var", name=key, file=rel_posix))


def _extract_python_operational_surfaces(content: str, rel_posix: str) -> list[OperationalSurface]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    surfaces: list[OperationalSurface] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(kind: str, name: str, detail: str = "") -> None:
        cleaned = name.strip()
        if not cleaned:
            return
        sig = (kind, cleaned, rel_posix)
        if sig not in seen:
            seen.add(sig)
            surfaces.append(
                OperationalSurface(kind=kind, name=cleaned, file=rel_posix, detail=detail.strip())
            )

    # 1. Click / Typer CLI groups & commands + FastAPI/Flask HTTP routes + FastMCP decorators
    fn_nodes = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    group_prefixes: dict[str, str] = {}
    for fn in fn_nodes:
        for dec in fn.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            target = call.func if call is not None else dec
            recv, method = _call_receiver_and_method(target)
            if method == "group":
                explicit = _const_str(call.args[0]) if (call and call.args) else None
                if explicit is None and call:
                    for kw in call.keywords:
                        if kw.arg == "name":
                            explicit = _const_str(kw.value)
                if recv in ("click", "typer", "") and fn.name in ("cli", "main", "app"):
                    group_prefixes[fn.name] = ""
                else:
                    parent = group_prefixes.get(recv, "" if recv in ("click", "typer", "cli", "main", "app") else recv)
                    seg = explicit if explicit is not None else fn.name.replace("_", "-")
                    group_prefixes[fn.name] = f"{parent} {seg}".strip()

    http_methods = frozenset({"get", "post", "put", "delete", "patch", "options", "head"})
    for fn in fn_nodes:
        cli_flags: list[str] = []
        for dec in fn.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            recv, method = _call_receiver_and_method(dec.func)
            if method in ("option", "Option"):
                str_args = [s for a in dec.args if (s := _const_str(a)) and s.startswith("-")]
                long_opts = [s for s in str_args if s.startswith("--")]
                chosen = (long_opts[0] if long_opts else (str_args[0] if str_args else "")).split("/")[0]
                if chosen and chosen not in cli_flags:
                    cli_flags.append(chosen)
            elif method in ("argument", "Argument") and dec.args:
                arg_name = _const_str(dec.args[0])
                if arg_name:
                    tok = f"<{arg_name}>"
                    if tok not in cli_flags:
                        cli_flags.append(tok)

        for dec in fn.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            target = call.func if call is not None else dec
            recv, method = _call_receiver_and_method(target)

            if method == "command" and (
                recv in group_prefixes or recv in ("click", "typer", "cli", "app", "main") or recv.endswith("_group")
            ):
                explicit = _const_str(call.args[0]) if (call and call.args) else None
                is_hidden = False
                if call:
                    for kw in call.keywords:
                        if kw.arg == "name" and explicit is None:
                            explicit = _const_str(kw.value)
                        elif kw.arg == "hidden" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            is_hidden = True
                parent = group_prefixes.get(
                    recv,
                    "" if recv in ("click", "typer", "cli", "app", "main") else recv.removesuffix("_group").replace("_", "-"),
                )
                leaf = explicit if explicit is not None else fn.name.replace("_", "-")
                full_cmd = f"{parent} {leaf}".strip()
                details: list[str] = []
                if is_hidden:
                    details.append("hidden=true")
                if cli_flags:
                    details.append(f"flags: {', '.join(cli_flags[:8])}")
                _add("cli_command", full_cmd, "; ".join(details))

            elif method in http_methods and call and call.args:
                route_path = _const_str(call.args[0])
                if route_path and route_path.startswith("/"):
                    _add("http_route", f"{method.upper()} {route_path}", fn.name)

            elif method in ("route", "api_route") and call and call.args:
                route_path = _const_str(call.args[0])
                if route_path and route_path.startswith("/"):
                    methods_list: list[str] = []
                    for kw in call.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            methods_list = [
                                s.upper() for elt in kw.value.elts if (s := _const_str(elt))
                            ]
                    for m_upper in (methods_list or ["GET"]):
                        _add("http_route", f"{m_upper} {route_path}", fn.name)

            elif method == "tool" and recv not in ("", "itertools", "functools"):
                explicit = _const_str(call.args[0]) if (call and call.args) else None
                if explicit is None and call:
                    for kw in call.keywords:
                        if kw.arg == "name":
                            explicit = _const_str(kw.value)
                doc_first = ((ast.get_docstring(fn) or "").splitlines() or [""])[0][:100]
                _add("mcp_tool", explicit or fn.name, doc_first)

            elif method == "resource" and call and call.args:
                uri = _const_str(call.args[0])
                if uri and "://" in uri:
                    doc_first = ((ast.get_docstring(fn) or "").splitlines() or [""])[0][:100]
                    _add("mcp_resource", uri, doc_first)

    # 2. Declarative MCP tool & resource definition tables (Assign / AnnAssign at module scope)
    for stmt in tree.body:
        var_name = ""
        val_node: ast.AST | None = None
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            var_name = stmt.targets[0].id
            val_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            var_name = stmt.target.id
            val_node = stmt.value
        if not var_name or not isinstance(val_node, (ast.List, ast.Tuple)):
            continue
        upper_var = var_name.upper()
        if "TOOL" in upper_var:
            for elt in val_node.elts:
                if not isinstance(elt, ast.Dict):
                    continue
                entries = _dict_literal_entries(elt)
                t_name = _const_str(entries.get("name"))
                if t_name and ("inputSchema" in entries or "description" in entries):
                    t_desc = (_const_str(entries.get("description")) or "")[:100]
                    _add("mcp_tool", t_name, t_desc)
        if "RESOURCE" in upper_var or "TEMPLATE" in upper_var:
            for elt in val_node.elts:
                if isinstance(elt, ast.Dict):
                    entries = _dict_literal_entries(elt)
                    uri = _const_str(entries.get("uri")) or _const_str(entries.get("uriTemplate"))
                    if uri and "://" in uri:
                        desc = (_const_str(entries.get("description")) or _const_str(entries.get("mimeType")) or "")[:100]
                        _add("mcp_resource", uri, desc)
                elif isinstance(elt, ast.Tuple) and elt.elts:
                    uri = _const_str(elt.elts[0])
                    if uri and "://" in uri:
                        desc = (_const_str(elt.elts[1]) if len(elt.elts) >= 2 else "") or ""
                        _add("mcp_resource", uri, desc[:100])

    # 3. argparse subparsers / commands (in module body and top-level parser builder functions)
    def _scan_argparse_scope(stmts: list[ast.stmt]) -> None:
        has_parser = False
        prog_name = ""
        subparsers_vars: dict[str, str] = {}
        parser_vars: dict[str, str] = {}
        discovered_cmds: list[str] = []
        cmd_flags: dict[str, list[str]] = defaultdict(list)
        root_flags: list[str] = []

        def _walk_stmts(block: list[ast.stmt]) -> None:
            nonlocal has_parser, prog_name
            for st in block:
                call_node: ast.Call | None = None
                assigned_var = ""
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and isinstance(st.value, ast.Call):
                    assigned_var = st.targets[0].id
                    call_node = st.value
                elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and isinstance(st.value, ast.Call):
                    assigned_var = st.target.id
                    call_node = st.value
                elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
                    call_node = st.value

                if call_node is not None:
                    recv, method = _call_receiver_and_method(call_node.func)
                    if method == "ArgumentParser":
                        has_parser = True
                        for kw in call_node.keywords:
                            if kw.arg == "prog":
                                prog_name = _const_str(kw.value) or prog_name
                        if assigned_var:
                            parser_vars[assigned_var] = ""
                    elif method == "add_subparsers" and assigned_var:
                        subparsers_vars[assigned_var] = parser_vars.get(recv, "")
                    elif method == "add_parser" and call_node.args:
                        sub_name = _const_str(call_node.args[0])
                        if sub_name:
                            parent = subparsers_vars.get(recv, "")
                            full = f"{parent} {sub_name}".strip()
                            if full not in discovered_cmds:
                                discovered_cmds.append(full)
                            if assigned_var:
                                parser_vars[assigned_var] = full
                    elif method == "add_argument" and call_node.args:
                        str_args = [s for a in call_node.args if (s := _const_str(a))]
                        long_opts = [s for s in str_args if s.startswith("--")]
                        flag = long_opts[0] if long_opts else (str_args[0] if str_args else "")
                        if flag:
                            if not flag.startswith("-"):
                                flag = f"<{flag}>"
                            target_cmd = parser_vars.get(recv, "")
                            bucket = cmd_flags[target_cmd] if target_cmd else root_flags
                            if flag not in bucket:
                                bucket.append(flag)

                for child_attr in ("body", "orelse", "finalbody"):
                    child = getattr(st, child_attr, None)
                    if isinstance(child, list):
                        _walk_stmts(child)

        _walk_stmts(stmts)
        if discovered_cmds:
            for cmd in discovered_cmds:
                fl = cmd_flags.get(cmd, [])
                detail = f"flags: {', '.join(fl[:8])}" if fl else "argparse"
                _add("cli_command", cmd, detail)
        elif has_parser and root_flags:
            _add("cli_command", prog_name or Path(rel_posix).stem, f"flags: {', '.join(root_flags[:8])}")

    _scan_argparse_scope(tree.body)
    for fn in fn_nodes:
        _scan_argparse_scope(fn.body)

    # 4. Starlette Route("/path", ...) + environment variable lookups
    env_helpers = frozenset({"_env_text", "_env_int", "_env_float", "_env_bool", "getenv"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            recv, method = _call_receiver_and_method(node.func)
            if method == "Route" and node.args:
                route_path = _const_str(node.args[0])
                if route_path and route_path.startswith("/"):
                    _add("http_route", f"GET {route_path}", "Route")
            elif (recv == "os" and method == "getenv" and node.args) or (
                recv == "environ" and method == "get" and node.args
            ) or (recv == "" and method in env_helpers and node.args):
                _record_env_key(_const_str(node.args[0]), rel_posix, seen, surfaces)
        elif isinstance(node, ast.Subscript):
            is_environ = (
                (isinstance(node.value, ast.Attribute) and node.value.attr == "environ")
                or (isinstance(node.value, ast.Name) and node.value.id == "environ")
            )
            if is_environ:
                _record_env_key(_const_str(node.slice), rel_posix, seen, surfaces)

    return surfaces


def _extract_operational_surfaces_for_file(
    path: Path,
    rel_posix: str,
    language: str | None,
) -> list[OperationalSurface]:
    if language is None or _is_test_or_non_operational_file(rel_posix):
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if language == "Python":
        return _extract_python_operational_surfaces(content, rel_posix)

    surfaces: list[OperationalSurface] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(kind: str, name: str, detail: str = "") -> None:
        sig = (kind, name, rel_posix)
        if sig not in seen:
            seen.add(sig)
            surfaces.append(OperationalSurface(kind=kind, name=name, file=rel_posix, detail=detail))

    if language in ("JavaScript", "TypeScript", "JavaScript (React)", "TypeScript (React)"):
        for m in _JS_HTTP_ROUTE_RE.finditer(content):
            _add("http_route", f"{m.group(1).upper()} {m.group(2)}")
        for m in _JS_MCP_TOOL_RE.finditer(content):
            _add("mcp_tool", m.group(1))
        for m in _JS_ENV_RE.finditer(content):
            _record_env_key(m.group(1), rel_posix, seen, surfaces)
    elif language == "Go":
        for m in _GO_HTTP_ROUTE_ANY_RE.finditer(content):
            method = (m.group(2) or m.group(3) or "ANY").upper()
            _add("http_route", f"{method} {m.group(4)}")
        for m in _GO_ENV_RE.finditer(content):
            _record_env_key(m.group(1), rel_posix, seen, surfaces)
    elif language == "Rust":
        for m in _RUST_ATTR_ROUTE_RE.finditer(content):
            _add("http_route", f"{m.group(1).upper()} {m.group(2)}")
        for m in _RUST_AXUM_ROUTE_RE.finditer(content):
            _add("http_route", f"{m.group(2).upper()} {m.group(1)}")
        for m in _RUST_ENV_RE.finditer(content):
            _record_env_key(m.group(1), rel_posix, seen, surfaces)

    return surfaces


def _symbol_ident(symbol_entry: str) -> str:
    parts = symbol_entry.split(" ", 1)
    return parts[1].strip() if len(parts) == 2 else symbol_entry.strip()


def _extract_python_code_idents(raw_text: str) -> set[str] | None:
    """Extract referenced Python identifiers via AST, excluding keyword-argument labels like check=False."""
    try:
        tree = ast.parse(raw_text)
    except SyntaxError:
        return None
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name and alias.name != "*":
                    idents.add(alias.name.split(".")[-1])
    return idents


def _compute_module_inbound_scores(file_skeletons: list[FileSkeleton]) -> dict[str, int]:
    """Count non-test inbound module import references for each source file."""
    stem_to_files: dict[str, list[str]] = defaultdict(list)
    dotted_to_file: dict[str, str] = {}
    for f in file_skeletons:
        if _is_test_or_non_operational_file(f.relative_path):
            continue
        p = Path(f.relative_path)
        stem = p.parent.name if p.stem in ("__init__", "index", "mod") else p.stem
        if stem:
            stem_to_files[stem].append(f.relative_path)
        no_ext_parts = list(p.with_suffix("").parts)
        if no_ext_parts and no_ext_parts[-1] in ("__init__", "index", "mod"):
            no_ext_parts = no_ext_parts[:-1]
        if no_ext_parts:
            dotted_to_file[".".join(no_ext_parts)] = f.relative_path
            if "src" in no_ext_parts:
                src_idx = no_ext_parts.index("src")
                if src_idx + 1 < len(no_ext_parts):
                    dotted_to_file[".".join(no_ext_parts[src_idx + 1 :])] = f.relative_path

    inbound: Counter[str] = Counter()
    for caller in file_skeletons:
        weight = 1 if _is_test_or_non_operational_file(caller.relative_path) else 3
        matched_targets: set[str] = set()
        for imp in caller.imports:
            norm = imp.lstrip("./").replace("/", ".").replace("::", ".").replace("\\", ".")
            if norm in dotted_to_file and dotted_to_file[norm] != caller.relative_path:
                matched_targets.add(dotted_to_file[norm])
                continue
            segs = [s for s in norm.split(".") if s]
            for cut in range(len(segs), 0, -1):
                cand = ".".join(segs[:cut])
                if cand in dotted_to_file and dotted_to_file[cand] != caller.relative_path:
                    matched_targets.add(dotted_to_file[cand])
                    break
            else:
                tail = segs[-1] if segs else ""
                for cand_rel in stem_to_files.get(tail, ()):
                    if cand_rel != caller.relative_path:
                        matched_targets.add(cand_rel)
        for tgt in matched_targets:
            inbound[tgt] += weight
    return dict(inbound)


def _compute_cross_file_symbol_refs(
    file_skeletons: list[FileSkeleton],
    file_ident_sets: dict[str, set[str]],
) -> dict[tuple[str, str], int]:
    """Score cross-file symbol centrality, weighting production callers higher than tests."""
    candidate_idents: set[str] = set()
    for f in file_skeletons:
        for sym in f.symbols:
            ident = _symbol_ident(sym)
            if len(ident) >= 3:
                candidate_idents.add(ident)
    if not candidate_idents:
        return {}

    global_doc_score: Counter[str] = Counter()
    own_weight_by_file: dict[str, int] = {}
    for rel_path, idents in file_ident_sets.items():
        weight = 1 if _is_test_or_non_operational_file(rel_path) else 3
        own_weight_by_file[rel_path] = weight
        for tok in idents & candidate_idents:
            global_doc_score[tok] += weight

    ref_counts: dict[tuple[str, str], int] = {}
    for f in file_skeletons:
        own_idents = file_ident_sets.get(f.relative_path, set())
        own_w = own_weight_by_file.get(f.relative_path, 3)
        for sym in f.symbols:
            ident = _symbol_ident(sym)
            if len(ident) < 3:
                ref_counts[(f.relative_path, sym)] = 0
                continue
            other_refs = global_doc_score.get(ident, 0) - (own_w if ident in own_idents else 0)
            ref_counts[(f.relative_path, sym)] = max(0, other_refs)
    return ref_counts


def _select_diversified_key_symbols(
    sfiles: list[FileSkeleton],
    limit: int = 25,
    *,
    ref_counts: dict[tuple[str, str], int] | None = None,
    module_inbound_scores: dict[str, int] | None = None,
) -> list[str]:
    """Select key symbols round-robin across subsystem files, balancing primary entrypoint and core hubs."""
    rc = ref_counts or {}
    mod_in = module_inbound_scores or {}

    entry_candidates = [
        f
        for f in sfiles
        if f.symbols and Path(f.relative_path).name in _ENTRYPOINT_FILENAMES
    ]
    primary_entry_path: str | None = None
    if entry_candidates:
        primary_entry_path = min(
            entry_candidates,
            key=lambda f: (
                -mod_in.get(f.relative_path, 0),
                -sum(rc.get((f.relative_path, s), 0) for s in f.symbols),
                f.relative_path,
            ),
        ).relative_path

    def _file_priority(f: FileSkeleton) -> tuple[int, int, int, str]:
        entry_tier = 0 if f.relative_path == primary_entry_path else 1
        in_score = mod_in.get(f.relative_path, 0)
        total_refs = sum(rc.get((f.relative_path, s), 0) for s in f.symbols)
        return (entry_tier, -in_score, -total_refs, f.relative_path)

    ranked_file_symbols: list[tuple[str, list[str]]] = []
    for f in sorted(sfiles, key=_file_priority):
        if not f.symbols:
            continue
        ordered_syms = [
            sym
            for _, sym in sorted(
                enumerate(f.symbols),
                key=lambda pair: (-rc.get((f.relative_path, pair[1]), 0), pair[0]),
            )
        ]
        ranked_file_symbols.append((Path(f.relative_path).name, ordered_syms))

    selected: list[str] = []
    idx = 0
    while len(selected) < limit and ranked_file_symbols:
        progressed = False
        for fname, syms in ranked_file_symbols:
            if idx < len(syms):
                selected.append(f"{fname}:{syms[idx]}")
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return selected


def _pre_subsystem_arch_role(state: dict[str, object]) -> str | None:
    raw_path = str(state.get("path") or "").strip().lower().strip("/")
    tokens = {tok for tok in re.split(r"[/_\-.]+", raw_path) if tok}
    if tokens & {"tests", "test", "benchmarks", "benchmark", "qa", "e2e", "specs", "fixtures"}:
        return "verification_tooling"
    if tokens & {"docs", "doc", "adr", "adrs", "documents", "archive", "designs", "rfcs"}:
        return "docs_governance"
    return None


def _rule_subsystem_arch_role(state: dict[str, object]) -> str:
    """Deterministic subsystem architectural role classifier."""
    pre = _pre_subsystem_arch_role(state)
    if pre is not None:
        return pre
    raw_path = str(state.get("path") or "").strip().lower().strip("/")
    path_tokens = {tok for tok in re.split(r"[/_\-.]+", raw_path) if tok}
    symbols = " ".join(str(s).lower() for s in (state.get("key_symbols") or []))  # type: ignore[union-attr]
    ext_deps = {str(d).lower() for d in (state.get("external_deps") or [])}  # type: ignore[union-attr]
    surfaces = {str(k).lower() for k in (state.get("operational_surface_kinds") or [])}  # type: ignore[union-attr]
    langs = {str(lang).lower() for lang in (state.get("languages") or [])}  # type: ignore[union-attr]

    if not langs or langs <= {"markdown"}:
        if raw_path in {".", ""} and not symbols:
            return "docs_governance"
    if ext_deps & {"anthropic", "openai", "httpx", "requests", "boto3", "psycopg", "redis", "sqlalchemy"} or (
        path_tokens
        & {
            "adapter",
            "adapters",
            "provider",
            "providers",
            "client",
            "clients",
            "git",
            "hook",
            "hooks",
            "storage",
            "db",
            "connector",
            "connectors",
        }
    ):
        if not (path_tokens & {"core", "domain"}):
            return "adapter_integration"
    file_count_val = int(state.get("file_count") or 0)  # type: ignore[arg-type]
    explicit_iface_path = bool(path_tokens & {"cli", "cmd", "server", "routes", "web", "ui", "mcp", "frontend"})
    if explicit_iface_path and not (path_tokens & {"core", "engine"}):
        return "entrypoint_interface"
    if (
        surfaces & {"cli_command", "http_route", "mcp_tool", "mcp_resource"}
        and not (path_tokens & {"core", "engine"})
        and file_count_val < 6
    ):
        return "entrypoint_interface"
    if path_tokens & {"util", "utils", "common", "shared", "helper", "helpers", "config", "types"}:
        return "shared_utility"
    if symbols or langs:
        return "core_domain"
    return "shared_utility"


def _classify_subsystem_arch_role(
    sub_path: str,
    file_count: int,
    languages: list[str],
    key_symbols: list[str],
    internal_deps: list[str],
    external_deps: list[str],
    surface_kinds: list[str],
) -> str:
    return _rule_subsystem_arch_role(
        {
            "path": sub_path,
            "file_count": file_count,
            "languages": languages,
            "key_symbols": key_symbols,
            "internal_deps": internal_deps,
            "external_deps": external_deps,
            "operational_surface_kinds": surface_kinds,
        }
    )


def _subsystem_key_for_rel_path(rel_posix: str) -> str:
    parts = Path(rel_posix).parts
    if len(parts) == 1:
        return "."
    if parts[0] == "src" and len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}" if len(parts) == 3 else f"{parts[0]}/{parts[1]}/{parts[2]}"
    return parts[0]


def extract_skeleton(
    root: Path,
    *,
    max_depth: int | None = None,
    extensions: list[str] | None = None,
) -> RepoSkeleton:
    """Deterministically scan a repository tree and build a RepoSkeleton with zero LLM calls."""
    root = root.resolve()
    cfg = load_config(root, max_depth=max_depth, extensions=extensions)
    effective_max_depth = cfg.max_depth
    spec = load_ignore_patterns(root)
    effective_exts = normalize_extensions(cfg.extensions)

    file_skeletons: list[FileSkeleton] = []
    boundary_docs: list[BoundaryDoc] = []
    operational_surfaces: list[OperationalSurface] = []
    file_ident_sets: dict[str, set[str]] = {}
    lang_counts: Counter[str] = Counter()
    entrypoints: list[str] = _detect_config_entrypoints(
        root, effective_exts, spec=spec, max_depth=effective_max_depth
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
                if effective_max_depth is None or depth < effective_max_depth:
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
                    if "src" in rel_parts[:-1]:
                        src_idx = rel_parts[:-1].index("src")
                        if src_idx + 1 < len(rel_parts):
                            internal_module_roots.add(rel_parts[src_idx + 1].removesuffix(".py"))
                    elif entry.name == "__init__.py" and len(rel_parts) >= 2:
                        internal_module_roots.add(entry.parent.name)
                    elif rel_parts[0].lower() not in _NON_OPERATIONAL_DIRS:
                        internal_module_roots.add(rel_parts[0].removesuffix(".py"))
                try:
                    raw_text = entry.read_text(encoding="utf-8")
                    py_idents = _extract_python_code_idents(raw_text) if language == "Python" else None
                    file_ident_sets[rel_posix] = (
                        py_idents if py_idents is not None else set(_IDENT_TOKEN_RE.findall(raw_text))
                    )
                except (OSError, UnicodeDecodeError):
                    pass

            symbols = _extract_symbols_for_file(entry, language)
            imports = _extract_imports_for_file(entry, language)
            operational_surfaces.extend(_extract_operational_surfaces_for_file(entry, rel_posix, language))
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
    kind_order = {"cli_command": 0, "http_route": 1, "mcp_tool": 2, "mcp_resource": 3, "env_var": 4}
    dedup_surfaces: dict[tuple[str, str, str], OperationalSurface] = {}
    for surf in operational_surfaces:
        key = (surf.kind, surf.name, surf.file)
        if key not in dedup_surfaces:
            dedup_surfaces[key] = surf
    operational_surfaces = sorted(
        dedup_surfaces.values(),
        key=lambda s: (kind_order.get(s.kind, 9), s.name, s.file),
    )

    ref_counts = _compute_cross_file_symbol_refs(file_skeletons, file_ident_sets)
    module_inbound_scores = _compute_module_inbound_scores(file_skeletons)

    # Group files and operational surfaces into logical subsystems
    subsystem_files: dict[str, list[FileSkeleton]] = defaultdict(list)
    subsystem_surface_kinds: dict[str, set[str]] = defaultdict(set)
    for f in file_skeletons:
        subsystem_files[_subsystem_key_for_rel_path(f.relative_path)].append(f)
    for surf in operational_surfaces:
        subsystem_surface_kinds[_subsystem_key_for_rel_path(surf.file)].add(surf.kind)

    subsystems: list[SubsystemSkeleton] = []
    for sub_path in sorted(subsystem_files.keys()):
        sfiles = subsystem_files[sub_path]
        sub_langs = Counter(f.language for f in sfiles if f.language)
        ordered_langs = [lang for lang, _ in sub_langs.most_common()]
        symbols_flat = _select_diversified_key_symbols(
            sfiles,
            limit=25,
            ref_counts=ref_counts,
            module_inbound_scores=module_inbound_scores,
        )
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

        int_list = sorted(internal_deps)[:15]
        ext_list = sorted(external_deps)[:15]
        arch_role = _classify_subsystem_arch_role(
            sub_path,
            len(sfiles),
            ordered_langs,
            symbols_flat,
            int_list,
            ext_list,
            sorted(subsystem_surface_kinds.get(sub_path, set())),
        )
        subsystems.append(
            SubsystemSkeleton(
                path=sub_path,
                file_count=len(sfiles),
                languages=ordered_langs,
                key_symbols=symbols_flat,
                internal_deps=int_list,
                external_deps=ext_list,
                arch_role=arch_role,
            )
        )

    # Compute deterministic structural_hash (module prefixes/roots + paths + symbols + imports + entrypoints + public surfaces)
    struct_hasher = hashlib.sha256()
    if internal_module_roots:
        struct_hasher.update(f"roots:{','.join(sorted(internal_module_roots))}\n".encode("utf-8"))
    if internal_prefixes:
        struct_hasher.update(f"prefixes:{','.join(sorted(internal_prefixes))}\n".encode("utf-8"))
    for ep in entrypoints:
        struct_hasher.update(f"ep:{ep}\n".encode("utf-8"))
    for surf in operational_surfaces:
        struct_hasher.update(
            f"surf:{surf.kind}|{surf.name}|{surf.file}|{surf.detail}\n".encode("utf-8")
        )
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
        operational_surfaces=operational_surfaces,
    )


def is_skeleton_stale(prev_metadata: dict[str, Any] | None, skeleton: RepoSkeleton) -> bool:
    """Return True when structural signatures or authority/boundary docs changed."""
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


should_invoke_llm = is_skeleton_stale


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


def _render_operational_surfaces_block(surfaces: list[OperationalSurface]) -> list[str]:
    if not surfaces:
        return []
    by_kind: dict[str, list[OperationalSurface]] = defaultdict(list)
    for s in surfaces:
        by_kind[s.kind].append(s)

    out: list[str] = []
    if by_kind["cli_command"]:
        items = [
            f"`{s.name}` ({s.detail})" if s.detail and s.detail != "argparse" else f"`{s.name}`"
            for s in by_kind["cli_command"][:20]
        ]
        out.append(f"- **CLI Commands ({len(by_kind['cli_command'])}):** {', '.join(items)}")
    if by_kind["http_route"]:
        items = [f"`{s.name}` (`{s.file}`)" for s in by_kind["http_route"][:15]]
        out.append(f"- **HTTP Routes ({len(by_kind['http_route'])}):** {', '.join(items)}")
    if by_kind["mcp_tool"]:
        items = [f"`{s.name}`" for s in by_kind["mcp_tool"][:20]]
        out.append(f"- **MCP Tools ({len(by_kind['mcp_tool'])}):** {', '.join(items)}")
    if by_kind["mcp_resource"]:
        items = [f"`{s.name}`" for s in by_kind["mcp_resource"][:15]]
        out.append(f"- **MCP Resources ({len(by_kind['mcp_resource'])}):** {', '.join(items)}")
    if by_kind["env_var"]:
        env_names = sorted({s.name for s in by_kind["env_var"]})
        items = [f"`{name}`" for name in env_names[:25]]
        out.append(f"- **Configuration Env Vars ({len(env_names)}):** {', '.join(items)}")
    return out


def render_context_0(
    skeleton: RepoSkeleton,
    *,
    generated: str | None = None,
    synthesized_invariants: list[dict[str, str]] | None = None,
) -> str:
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
    surface_lines = _render_operational_surfaces_block(skeleton.operational_surfaces)
    if skeleton.entrypoints or surface_lines:
        for ep in skeleton.entrypoints:
            lines.append(f"- `{ep}`")
        lines.extend(surface_lines)
    else:
        lines.append("- None detected")
    lines.append("")

    lines.append("## Subsystem Overview")
    lines.append("| Subsystem | Role | Files | Languages | Key Exports |")
    lines.append("|-----------|------|------:|-----------|-------------|")
    for sub in skeleton.subsystems:
        role = sub.arch_role or "-"
        langs = ", ".join(sub.languages[:3]) or "-"
        exports = ", ".join(f"`{s}`" for s in sub.key_symbols[:4]) or "-"
        lines.append(f"| `{sub.path}` | `{role}` | {sub.file_count} | {langs} | {exports} |")
    lines.append("")

    if synthesized_invariants:
        lines.append("## Synthesized Cross-Module Invariants & Footguns")
        for inv in synthesized_invariants[:10]:
            cat = inv.get("category", "invariant")
            scope = inv.get("scope", ".")
            stmt = inv.get("statement", "")
            if stmt:
                lines.append(f"- **[{cat}]** (`{scope}`): {stmt}")
        lines.append("")

    lines.append("<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->")
    return "\n".join(lines) + "\n"


def render_context_1(
    skeleton: RepoSkeleton,
    *,
    generated: str | None = None,
    synthesized_invariants: list[dict[str, str]] | None = None,
) -> str:
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
        role_tag = f" [`{sub.arch_role}`]" if sub.arch_role else ""
        lines.append(f"### `{sub.path}` ({sub.file_count} files){role_tag}")
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

    if synthesized_invariants:
        lines.append("## Synthesized Cross-Module Invariants & Footguns")
        for inv in synthesized_invariants:
            cat = inv.get("category", "invariant")
            scope = inv.get("scope", ".")
            stmt = inv.get("statement", "")
            if stmt:
                lines.append(f"- **[{cat}]** (`{scope}`): {stmt}")
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


def render_context_full(
    skeleton: RepoSkeleton,
    *,
    generated: str | None = None,
    synthesized_invariants: list[dict[str, str]] | None = None,
) -> str:
    """Render CONTEXT.md: Full architectural synthesis + file-level deterministic signatures."""
    ts = generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Pass synthesized_invariants to CONTEXT-1 body only so CONTEXT.md includes them once without duplication
    c0 = render_context_0(skeleton, generated=ts, synthesized_invariants=None)
    c1_body = strip_tier2_chrome(
        render_context_1(skeleton, generated=ts, synthesized_invariants=synthesized_invariants),
        strip_footer=True,
    )

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
