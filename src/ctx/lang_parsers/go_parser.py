import re
from pathlib import Path
from typing import Dict, List


# Go exports are determined by capitalisation: any top-level identifier
# starting with an uppercase letter is part of the public API.

# Matches: func ExportedName( or func (recv) ExportedName(
_EXPORTED_FUNC = re.compile(
    r"^func\s+(?:\([^)]*\)\s+)?([A-Z]\w*)\s*[(\[]",
    re.MULTILINE,
)
# Matches: type ExportedName struct/interface/...
_EXPORTED_TYPE = re.compile(r"^type\s+([A-Z]\w*)\s+\w+", re.MULTILINE)
# Matches: const ExportedName (single-line form)
_SINGLE_CONST = re.compile(r"^const\s+([A-Z]\w*)\b", re.MULTILINE)
# Matches the body of a const (...) block; avoids re.DOTALL by excluding ')'
_CONST_BLOCK = re.compile(r"^const\s*\(([^)]*)\)", re.MULTILINE)
# Matches exported names inside a const block (first identifier on each line)
_CONST_IN_BLOCK = re.compile(r"^\s*([A-Z]\w*)", re.MULTILINE)
# Matches: var ExportedName
_EXPORTED_VAR = re.compile(r"^var\s+([A-Z]\w*)\b", re.MULTILINE)


def parse_go_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Go file and extracts exported identifiers.

    Go's export rule is capitalisation: any top-level name starting with
    an uppercase letter is exported.

    Returns a dictionary with keys: 'functions', 'types', 'constants',
    and 'variables'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    const_matches = _SINGLE_CONST.findall(content)
    for block_content in _CONST_BLOCK.findall(content):
        const_matches.extend(_CONST_IN_BLOCK.findall(block_content))

    return {
        "functions": _EXPORTED_FUNC.findall(content),
        "types": _EXPORTED_TYPE.findall(content),
        "constants": sorted(list(set(const_matches))),
        "variables": _EXPORTED_VAR.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "types": [],
        "constants": [],
        "variables": [],
    }
