import re
from pathlib import Path
from typing import Dict, List


# Public function definitions only (def, not defp).
# Matches: def name(  OR  def name,  OR  def name\n  (zero-arg shorthand)
_DEF = re.compile(r"^[ \t]*def\s+(\w+)\s*[\(,\n]", re.MULTILINE)
# Module definitions
_DEFMODULE = re.compile(r"^[ \t]*defmodule\s+([\w.]+)", re.MULTILINE)
# Struct definitions (marks the module as defining a struct)
_DEFSTRUCT = re.compile(r"^[ \t]*defstruct\b", re.MULTILINE)


def parse_elixir_file(path: Path) -> Dict[str, List[str]]:
    """Parse an Elixir source file and extract public functions, modules, and structs.

    Only public ``def`` functions are captured; private ``defp`` functions are
    excluded to match the project convention of surfacing public API only.

    Returns a dictionary with keys:
        ``functions`` — list of public function names (deduplicated, order preserved)
        ``modules``   — list of module names from ``defmodule``
        ``structs``   — list of module names that contain a ``defstruct``
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty()

    modules = _DEFMODULE.findall(content)
    # If the file contains a defstruct, associate it with every module declared
    # in that file (typically there is only one per file in idiomatic Elixir).
    structs = list(modules) if _DEFSTRUCT.search(content) else []

    return {
        "functions": list(dict.fromkeys(_DEF.findall(content))),
        "modules": modules,
        "structs": structs,
    }


def _empty() -> Dict[str, List[str]]:
    return {
        "functions": [],
        "modules": [],
        "structs": [],
    }
