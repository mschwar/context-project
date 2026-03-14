import re
from pathlib import Path
from typing import Dict, List


# Matches: public class/interface/enum/record Foo
_PUBLIC_TYPE = re.compile(
    r"^[ \t]*(?:(?:abstract|final|sealed|non-sealed|static)\s+)*public\s+(?:(?:abstract|final|sealed|non-sealed|static)\s+)*"
    r"(class|interface|enum|record)\s+(\w+)",
    re.MULTILINE,
)
# Matches: public [modifiers] ReturnType methodName(
_PUBLIC_METHOD = re.compile(
    r"^[ \t]*(?:(?:static|final|abstract|synchronized|native|default|override)\s+)*"
    r"public\s+(?:(?:static|final|abstract|synchronized|native|default|override)\s+)*"
    r"(?:<[^>]*>\s+)?"           # optional generic return type
    r"(?:[\w\[\]<>, .]+?\s+)"    # return type (non-greedy)
    r"(\w+)\s*\(",
    re.MULTILINE,
)
# Annotation lines: @Foo or @Foo(...) — stripped before method matching so that
# @Override\npublic void foo() is correctly detected.
_ANNOTATION_LINE = re.compile(r"^[ \t]*@\w+[^\n]*\n", re.MULTILINE)


def parse_java_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Java file and extracts public type and method declarations.

    Returns a dictionary with keys: 'classes', 'interfaces', 'enums',
    'records', and 'methods'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    classes: List[str] = []
    interfaces: List[str] = []
    enums: List[str] = []
    records: List[str] = []

    for kind, name in _PUBLIC_TYPE.findall(content):
        if kind == "class":
            classes.append(name)
        elif kind == "interface":
            interfaces.append(name)
        elif kind == "enum":
            enums.append(name)
        elif kind == "record":
            records.append(name)

    # Strip annotation lines so @Override\npublic void foo() is matched correctly.
    stripped = _ANNOTATION_LINE.sub("", content)
    methods = _PUBLIC_METHOD.findall(stripped)

    return {
        "classes": classes,
        "interfaces": interfaces,
        "enums": enums,
        "records": records,
        "methods": methods,
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "classes": [],
        "interfaces": [],
        "enums": [],
        "records": [],
        "methods": [],
    }
