import re
from pathlib import Path
from typing import Dict, List


# fun topLevel(  or  fun <T> topLevel(  — excludes indented (method) definitions
# We capture top-level and class-member funs; indentation is allowed.
_FUN = re.compile(r"^[ \t]*(?:(?:public|internal|protected|private|open|override|abstract|suspend|inline|operator|infix|tailrec|external|actual|expect)\s+)*fun\s+(?:<[^>]*>\s+)?(\w+)\s*[(\[]", re.MULTILINE)
# data class, class, abstract class, open class, sealed class, annotation class, inner class
_CLASS = re.compile(r"^[ \t]*(?:(?:public|internal|private|open|abstract|sealed|data|annotation|inner|value|actual|expect)\s+)*class\s+(\w+)", re.MULTILINE)
# interface
_INTERFACE = re.compile(r"^[ \t]*(?:(?:public|internal|private|fun)\s+)*interface\s+(\w+)", re.MULTILINE)
# object (singleton) and companion object
_OBJECT = re.compile(r"^[ \t]*(?:(?:public|internal|private|open|actual|expect)\s+)*object\s+(\w+)", re.MULTILINE)
# enum class
_ENUM = re.compile(r"^[ \t]*(?:(?:public|internal|private)\s+)*enum\s+class\s+(\w+)", re.MULTILINE)


def parse_kotlin_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Kotlin file and extracts top-level declarations.

    Returns a dictionary with keys: 'functions', 'classes', 'interfaces',
    'objects', and 'enums'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    return {
        "functions": _FUN.findall(content),
        "classes": _CLASS.findall(content),
        "interfaces": _INTERFACE.findall(content),
        "objects": _OBJECT.findall(content),
        "enums": _ENUM.findall(content),
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "classes": [],
        "interfaces": [],
        "objects": [],
        "enums": [],
    }
