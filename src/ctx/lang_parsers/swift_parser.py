import re
from pathlib import Path
from typing import Dict, List


# func name( or func name<T>(  — public/open/internal/private; capture all
# (Swift default access is internal; public/open are the explicit public modifiers,
# but for context purposes we extract all top-level declarations)
_FUNC = re.compile(
    r"^[ \t]*(?:(?:public|open|internal|private|fileprivate|static|class|override|"
    r"mutating|nonmutating|final|required|convenience|dynamic|lazy|weak|unowned)\s+)*"
    r"func\s+(\w+)\s*[(<]",
    re.MULTILINE,
)
# class / final class / open class
_CLASS = re.compile(
    r"^[ \t]*(?:(?:public|open|internal|private|fileprivate|final)\s+)*class\s+(\w+)",
    re.MULTILINE,
)
# struct
_STRUCT = re.compile(
    r"^[ \t]*(?:(?:public|internal|private|fileprivate)\s+)*struct\s+(\w+)",
    re.MULTILINE,
)
# protocol
_PROTOCOL = re.compile(
    r"^[ \t]*(?:(?:public|internal|private|fileprivate)\s+)*protocol\s+(\w+)",
    re.MULTILINE,
)
# enum
_ENUM = re.compile(
    r"^[ \t]*(?:(?:public|internal|private|fileprivate)\s+)*enum\s+(\w+)",
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
