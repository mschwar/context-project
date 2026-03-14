import pytest
from pathlib import Path
from ctx.lang_parsers.python_parser import parse_python_file

def test_parse_python_file_extracts_identifiers(tmp_path):
    code = """
class MyClass:
    def method(self):
        pass

async def async_func():
    pass

def regular_func(a, b):
    return a + b
"""
    py_file = tmp_path / "test.py"
    py_file.write_text(code, encoding="utf-8")
    
    result = parse_python_file(py_file)
    assert result["classes"] == ["MyClass"]
    assert result["functions"] == ["async_func", "regular_func"]

def test_parse_python_file_empty(tmp_path):
    py_file = tmp_path / "empty.py"
    py_file.touch()
    result = parse_python_file(py_file)
    assert result["classes"] == []
    assert result["functions"] == []

def test_parse_python_file_syntax_error(tmp_path):
    py_file = tmp_path / "error.py"
    py_file.write_text("class Unfinished:", encoding="utf-8")
    result = parse_python_file(py_file)
    assert result["classes"] == []
    assert result["functions"] == []

def test_parse_python_file_not_found(tmp_path):
    result = parse_python_file(tmp_path / "missing.py")
    assert result["classes"] == []
    assert result["functions"] == []
