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
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ctx import __version__
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
_RUST_USE_RE = re.compile(r"^use\s+([a-zA-Z0-9_:]+)", re.MULTILINE)
_GO_IMPORT_SINGLE_RE = re.compile(r'^import\s+"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r"^import\s*\(([^)]*)\)", re.MULTILINE)
_GO_QUOTED_PKG_RE = re.compile(r'"([^"]+)"')
_PYPROJECT_SCRIPT_SECTION_RE = re.compile(r"^\[project\.scripts\]\s*$", re.MULTILINE)


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
                        imports.add(node.module)
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

    return sorted(imports)


def _extract_markdown_headings_and_summary(path: Path) -> tuple[list[str], str, str]:
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8", errors="replace")
    except OSError:
        return [], "", ""

    content_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    headings: list[str] = []
    summary_line = ""
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
            if title and level <= 2:
                headings.append(title)
            continue
        if not summary_line and not stripped.startswith(("<!--", "|", "-", "*", ">")):
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


def _detect_config_entrypoints(root: Path) -> list[str]:
    entrypoints: list[str] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
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
                        entrypoints.append(f"cli:{k.strip()} -> {cleaned_val}")
        except (OSError, UnicodeDecodeError):
            pass

    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            if isinstance(pkg, dict):
                main_val = pkg.get("main")
                if isinstance(main_val, str) and main_val.strip():
                    entrypoints.append(f"npm:main -> {main_val.strip()}")
                bin_val = pkg.get("bin")
                if isinstance(bin_val, str) and bin_val.strip():
                    entrypoints.append(f"npm:bin -> {bin_val.strip()}")
                elif isinstance(bin_val, dict):
                    for k, v in sorted(bin_val.items()):
                        entrypoints.append(f"npm:bin:{k} -> {v}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass

    return entrypoints


def extract_skeleton(root: Path, *, max_depth: int | None = None) -> RepoSkeleton:
    """Deterministically scan a repository tree and build a RepoSkeleton with zero LLM calls."""
    root = root.resolve()
    spec = load_ignore_patterns(root)

    file_skeletons: list[FileSkeleton] = []
    boundary_docs: list[BoundaryDoc] = []
    lang_counts: Counter[str] = Counter()
    entrypoints: list[str] = _detect_config_entrypoints(root)

    # Track internal module names for dependency classification
    internal_module_roots: set[str] = set()

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

            rel_posix = entry.relative_to(root).as_posix()

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

            if entry.name in _ENTRYPOINT_FILENAMES:
                entrypoints.append(f"file:{rel_posix}")

            language = detect_language(entry)
            if language:
                lang_counts[language] += 1
                if language == "Python":
                    parts = entry.relative_to(root).parts
                    if len(parts) >= 2 and parts[0] == "src":
                        internal_module_roots.add(parts[1].removesuffix(".py"))
                    else:
                        internal_module_roots.add(parts[0].removesuffix(".py"))

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
        symbols_flat: list[str] = []
        internal_deps: set[str] = set()
        external_deps: set[str] = set()

        for f in sfiles:
            for sym in f.symbols:
                if len(symbols_flat) < 25:
                    symbols_flat.append(f"{Path(f.relative_path).name}:{sym}")
            for imp in f.imports:
                top_mod = imp.split(".")[0].split("/")[0].split("::")[0]
                if imp.startswith(".") or top_mod in internal_module_roots or top_mod in ("crate", "super", "self"):
                    internal_deps.add(imp)
                elif top_mod:
                    external_deps.add(top_mod)

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

    # Compute deterministic structural_hash (paths + symbols + imports + entrypoints)
    struct_hasher = hashlib.sha256()
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


def render_context_full(skeleton: RepoSkeleton, *, generated: str | None = None) -> str:
    """Render CONTEXT.md: Full architectural synthesis + file-level deterministic signatures."""
    ts = generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    c0 = render_context_0(skeleton, generated=ts)
    c1_body = "\n".join(render_context_1(skeleton, generated=ts).splitlines()[12:-1])

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

    base = c0.removesuffix("<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->\n")
    return (
        base
        + "\n"
        + c1_body
        + "\n"
        + "\n".join(file_lines)
        + "\n\n<!-- Generated by ctx (https://pypi.org/project/ctx-tool/) -->\n"
    )
