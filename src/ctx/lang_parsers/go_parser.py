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

    # For constants, use a more robust multi-step parsing.
    const_block_re = re.compile(r"^const\s*\((.*?)\)", re.DOTALL | re.MULTILINE)
    const_in_block_re = re.compile(r"^\s*([A-Z]\w*)", re.MULTILINE)
    single_const_re = re.compile(r"^const\s+([A-Z]\w*)\b", re.MULTILINE)

    const_matches = single_const_re.findall(content)
    for block_content in const_block_re.findall(content):
        const_matches.extend(const_in_block_re.findall(block_content))

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
