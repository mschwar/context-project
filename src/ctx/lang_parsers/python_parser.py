import ast
from pathlib import Path
from typing import List, Dict

def parse_python_file(path: Path) -> Dict[str, List[str]]:
    """
    Parses a Python file and extracts key identifiers.

    Args:
        path: Path to the Python file.

    Returns:
        A dictionary containing lists of 'classes' and 'functions'.
    """
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        
        classes = []
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
        
        return {
            "classes": classes,
            "functions": functions
        }
    except (OSError, SyntaxError, UnicodeDecodeError):
        return {"classes": [], "functions": []}
