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
# Matches: const ExportedName or const ( ExportedName on its own line
_EXPORTED_CONST = re.compile(r"^\s*([A-Z]\w*)\s+.*=|^const\s+([A-Z]\w*)\b", re.MULTILINE)
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

    # _EXPORTED_CONST has two capture groups; flatten and drop empty strings
    const_matches = [
        name
        for match in _EXPORTED_CONST.finditer(content)
        for name in match.groups()
        if name
    ]

    return {
        "functions": _EXPORTED_FUNC.findall(content),
        "types": _EXPORTED_TYPE.findall(content),
        "constants": const_matches,
        "variables": _EXPORTED_VAR.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "types": [],
        "constants": [],
        "variables": [],
    }
