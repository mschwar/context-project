import re
from pathlib import Path
from typing import Dict, List


# Ruby: all top-level definitions are public by default.
# Top-level def: starts at column 0 or minimal indent (we allow any indent to
# catch module-level methods), but we exclude deeply indented defs by requiring
# the line to begin without leading spaces OR with exactly two spaces (inside a
# class/module body).
# Simpler approach: capture all def/class/module names at any indent — the LLM
# benefits from seeing all names regardless of nesting depth.
_DEF = re.compile(r"^[ \t]*def\s+(?:self\.)?(\w+[?!]?)", re.MULTILINE)
_CLASS = re.compile(r"^[ \t]*class\s+([A-Z]\w*(?:::[A-Z]\w*)*)", re.MULTILINE)
_MODULE = re.compile(r"^[ \t]*module\s+([A-Z]\w*(?:::[A-Z]\w*)*)", re.MULTILINE)


def parse_ruby_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Ruby file and extracts method, class, and module definitions.

    Ruby has no explicit visibility modifier for public definitions; all
    top-level and class-body definitions are public by default.

    Returns a dictionary with keys: 'methods', 'classes', and 'modules'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    return {
        "methods": _DEF.findall(content),
        "classes": _CLASS.findall(content),
        "modules": _MODULE.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "methods": [],
        "classes": [],
        "modules": [],
    }
