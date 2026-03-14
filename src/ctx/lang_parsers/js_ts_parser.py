import re
from pathlib import Path
from typing import Dict, List, Union


# Matches: export function foo, export async function foo
_EXPORTED_FUNC = re.compile(r"^export\s+(?:async\s+)?function\s+(\w+)", re.MULTILINE)
# Matches: export const foo = (...) =>  or  export const foo = function
_EXPORTED_ARROW = re.compile(
    r"^export\s+(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|function\b)",
    re.MULTILINE,
)
# Matches: export class Foo
_EXPORTED_CLASS = re.compile(r"^export\s+(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)
# Matches: export interface Foo
_EXPORTED_INTERFACE = re.compile(r"^export\s+interface\s+(\w+)", re.MULTILINE)
# Matches: export type Foo =
_EXPORTED_TYPE = re.compile(r"^export\s+type\s+(\w+)\s*[=<{]", re.MULTILINE)
# Matches any export default
_DEFAULT_EXPORT = re.compile(r"^export\s+default\b", re.MULTILINE)


def parse_js_ts_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a JS/TS file and extracts exported identifiers.

    Returns a dictionary with keys: 'functions', 'classes', 'interfaces',
    'types', and 'has_default_export'.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    functions = _EXPORTED_FUNC.findall(content) + _EXPORTED_ARROW.findall(content)
    classes = _EXPORTED_CLASS.findall(content)
    interfaces = _EXPORTED_INTERFACE.findall(content)
    types = _EXPORTED_TYPE.findall(content)
    has_default_export = bool(_DEFAULT_EXPORT.search(content))

    return {
        "functions": functions,
        "classes": classes,
        "interfaces": interfaces,
        "types": types,
        "has_default_export": has_default_export,
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "classes": [],
        "interfaces": [],
        "types": [],
        "has_default_export": False,
    }
