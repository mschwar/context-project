import re
from pathlib import Path
from typing import Dict, List


# public [static|abstract|final] function name(
# Matches public/global functions, excluding private/protected methods.
_PUBLIC_FUNCTION = re.compile(
    r"^[ \t]*(?:(?:abstract|final|static)\s+)*(?!private|protected)\s*function\s+(\w+)\s*\(",
    re.MULTILINE,
)
# class Foo [extends|implements ...]
_CLASS = re.compile(r"^[ \t]*(?:(?:abstract|final|readonly)\s+)*class\s+(\w+)", re.MULTILINE)
# interface Foo
_INTERFACE = re.compile(r"^[ \t]*interface\s+(\w+)", re.MULTILINE)
# trait Foo
_TRAIT = re.compile(r"^[ \t]*trait\s+(\w+)", re.MULTILINE)
# enum Foo  (PHP 8.1+)
_ENUM = re.compile(r"^[ \t]*enum\s+(\w+)", re.MULTILINE)


def parse_php_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a PHP file and extracts public declarations.

    Returns a dictionary with keys: 'functions', 'classes', 'interfaces',
    'traits', and 'enums'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    return {
        "functions": _PUBLIC_FUNCTION.findall(content),
        "classes": _CLASS.findall(content),
        "interfaces": _INTERFACE.findall(content),
        "traits": _TRAIT.findall(content),
        "enums": _ENUM.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "classes": [],
        "interfaces": [],
        "traits": [],
        "enums": [],
    }
