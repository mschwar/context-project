"""Deterministic lexical/regex symbol parser for C and C++ source & header files."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List

_CONTROL_KEYWORDS = frozenset({
    "if",
    "else",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "sizeof",
    "alignof",
    "decltype",
    "static_assert",
    "operator",
    "delete",
    "new",
})

_COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE_RE = re.compile(r"//[^\n]*")
_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\{", re.MULTILINE)
_CLASS_RE = re.compile(
    r"^\s*(?:template\s*<[^>]*>\s*)?class\s+(?:[A-Z_][A-Z0-9_]*\s+)*([A-Za-z_]\w*)\b[^;]*\{",
    re.MULTILINE,
)
_STRUCT_RE = re.compile(
    r"^\s*(?:template\s*<[^>]*>\s*)?(?:typedef\s+)?struct\s+(?:[A-Z_][A-Z0-9_]*\s+)*([A-Za-z_]\w*)\b[^;]*\{",
    re.MULTILINE,
)
_TYPEDEF_STRUCT_RE = re.compile(
    r"^\s*typedef\s+struct(?:\s+[A-Za-z_]\w*)?\s*\{[^{}]*\}\s*([A-Za-z_]\w*)\s*;",
    re.MULTILINE | re.DOTALL,
)
_ENUM_RE = re.compile(
    r"^\s*enum\s+(?:class\s+|struct\s+)?([A-Za-z_]\w*)\b[^;]*\{",
    re.MULTILINE,
)
_USING_TYPE_RE = re.compile(
    r"^\s*(?:template\s*<[^>]*>\s*)?using\s+([A-Za-z_]\w*)\s*=",
    re.MULTILINE,
)
_TYPEDEF_ALIAS_RE = re.compile(
    r"^\s*typedef\s+[^;{]+\b([A-Za-z_]\w*)\s*;",
    re.MULTILINE,
)
_TOP_FUNC_RE = re.compile(
    r"^(?:template\s*<[^>]*>\s*)?"
    r"(?:(?:inline|static|constexpr|consteval|extern|virtual|explicit|friend)\s+)*"
    r"[A-Za-z_][\w:<>,\s*&~]*?\s+\**([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept(?:\([^)]*\))?\s*)?(?:\{|;)",
    re.MULTILINE,
)


def _dedupe(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item and item not in _CONTROL_KEYWORDS and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_c_cpp_file(path: Path) -> Dict[str, List[str]]:
    """Extract top-level classes, structs, enums, namespaces, type aliases, and functions from C/C++ files."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    stripped = _COMMENT_LINE_RE.sub("", _COMMENT_BLOCK_RE.sub("", raw))

    structs = _STRUCT_RE.findall(stripped) + _TYPEDEF_STRUCT_RE.findall(stripped)
    types = _USING_TYPE_RE.findall(stripped) + _TYPEDEF_ALIAS_RE.findall(stripped)

    return {
        "classes": _dedupe(_CLASS_RE.findall(stripped)),
        "structs": _dedupe(structs),
        "enums": _dedupe(_ENUM_RE.findall(stripped)),
        "modules": _dedupe([ns.split("::")[-1] for ns in _NAMESPACE_RE.findall(stripped)]),
        "types": _dedupe(types),
        "functions": _dedupe(_TOP_FUNC_RE.findall(stripped)),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "classes": [],
        "structs": [],
        "enums": [],
        "modules": [],
        "types": [],
        "functions": [],
    }
