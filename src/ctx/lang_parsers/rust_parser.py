import re
from pathlib import Path
from typing import Dict, List


_PUB_FN = re.compile(r"^pub(?:\([^)]*\))?\s+(?:async\s+)?fn\s+(\w+)", re.MULTILINE)
_PUB_STRUCT = re.compile(r"^pub(?:\([^)]*\))?\s+struct\s+(\w+)", re.MULTILINE)
_PUB_ENUM = re.compile(r"^pub(?:\([^)]*\))?\s+enum\s+(\w+)", re.MULTILINE)
_PUB_TRAIT = re.compile(r"^pub(?:\([^)]*\))?\s+trait\s+(\w+)", re.MULTILINE)
_MOD = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)", re.MULTILINE)


def parse_rust_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Rust file and extracts public declarations and modules.

    Returns a dictionary with keys: 'functions', 'structs', 'enums',
    'traits', and 'modules'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    return {
        "functions": _PUB_FN.findall(content),
        "structs": _PUB_STRUCT.findall(content),
        "enums": _PUB_ENUM.findall(content),
        "traits": _PUB_TRAIT.findall(content),
        "modules": _MOD.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "structs": [],
        "enums": [],
        "traits": [],
        "modules": [],
    }
