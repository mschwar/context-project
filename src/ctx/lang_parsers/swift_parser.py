import re
from pathlib import Path
from typing import Dict, List


# Matches public, open, internal (default), and unqualified declarations.
# Excludes private and fileprivate to match the project convention of
# capturing the public/internal API surface only.
_FUNC = re.compile(
    r"^[ \t]*(?:(?:public|open|internal|static|class|override|"
    r"mutating|nonmutating|final|required|convenience|dynamic)\s+)*"
    r"func\s+(\w+)\s*[(<]",
    re.MULTILINE,
)
_CLASS = re.compile(
    r"^[ \t]*(?:(?:public|open|internal|final)\s+)*class\s+(\w+)",
    re.MULTILINE,
)
_STRUCT = re.compile(
    r"^[ \t]*(?:(?:public|open|internal)\s+)*struct\s+(\w+)",
    re.MULTILINE,
)
_PROTOCOL = re.compile(
    r"^[ \t]*(?:(?:public|open|internal)\s+)*protocol\s+(\w+)",
    re.MULTILINE,
)
_ENUM = re.compile(
    r"^[ \t]*(?:(?:public|open|internal)\s+)*enum\s+(\w+)",
    re.MULTILINE,
)


def parse_swift_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Swift file and extracts top-level declarations.

    Returns a dictionary with keys: 'functions', 'classes', 'structs',
    'protocols', and 'enums'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    return {
        "functions": _FUNC.findall(content),
        "classes": _CLASS.findall(content),
        "structs": _STRUCT.findall(content),
        "protocols": _PROTOCOL.findall(content),
        "enums": _ENUM.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "classes": [],
        "structs": [],
        "protocols": [],
        "enums": [],
    }
