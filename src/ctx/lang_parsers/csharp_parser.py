import re
from pathlib import Path
from typing import Dict, List


# Matches: public [modifiers] class/interface/enum/struct/record Foo
_PUBLIC_TYPE = re.compile(
    r"^[ \t]*(?:(?:abstract|sealed|static|partial|readonly|unsafe)\s+)*public\s+"
    r"(?:(?:abstract|sealed|static|partial|readonly|unsafe)\s+)*"
    r"(class|interface|enum|struct|record)\s+(\w+)",
    re.MULTILINE,
)
# Matches: public [modifiers] ReturnType MethodName(
# Covers instance, static, async, override, virtual, abstract methods.
_PUBLIC_METHOD = re.compile(
    r"^[ \t]*(?:(?:static|virtual|override|abstract|async|sealed|extern|new|unsafe|partial)\s+)*"
    r"public\s+(?:(?:static|virtual|override|abstract|async|sealed|extern|new|unsafe|partial)\s+)*"
    r"(?:[\w\[\]<>, .?]+?\s+)"   # return type
    r"(\w+)\s*[(<]",             # method name followed by ( or < (generic)
    re.MULTILINE,
)


def parse_csharp_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a C# file and extracts public type and method declarations.

    Returns a dictionary with keys: 'classes', 'interfaces', 'enums',
    'structs', 'records', and 'methods'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    classes: List[str] = []
    interfaces: List[str] = []
    enums: List[str] = []
    structs: List[str] = []
    records: List[str] = []

    for kind, name in _PUBLIC_TYPE.findall(content):
        if kind == "class":
            classes.append(name)
        elif kind == "interface":
            interfaces.append(name)
        elif kind == "enum":
            enums.append(name)
        elif kind == "struct":
            structs.append(name)
        elif kind == "record":
            records.append(name)

    methods = _PUBLIC_METHOD.findall(content)

    return {
        "classes": classes,
        "interfaces": interfaces,
        "enums": enums,
        "structs": structs,
        "records": records,
        "methods": methods,
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "classes": [],
        "interfaces": [],
        "enums": [],
        "structs": [],
        "records": [],
        "methods": [],
    }
