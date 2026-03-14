import pytest
from pathlib import Path
from ctx.language_detector import detect_language

def test_detect_language_file_extensions(tmp_path):
    py_file = tmp_path / "main.py"
    py_file.touch()
    assert detect_language(py_file) == "Python"

    rs_file = tmp_path / "lib.rs"
    rs_file.touch()
    assert detect_language(rs_file) == "Rust"

    js_file = tmp_path / "app.js"
    js_file.touch()
    assert detect_language(js_file) == "JavaScript"

def test_detect_language_project_files(tmp_path):
    python_dir = tmp_path / "py_project"
    python_dir.mkdir()
    (python_dir / "pyproject.toml").touch()
    assert detect_language(python_dir) == "Python"

    rust_dir = tmp_path / "rs_project"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").touch()
    assert detect_language(rust_dir) == "Rust"

def test_detect_language_most_common_extension(tmp_path):
    mixed_dir = tmp_path / "mixed"
    mixed_dir.mkdir()
    (mixed_dir / "a.py").touch()
    (mixed_dir / "b.py").touch()
    (mixed_dir / "c.js").touch()
    assert detect_language(mixed_dir) == "Python"

def test_detect_language_unknown(tmp_path):
    unknown_file = tmp_path / "data.dat"
    unknown_file.touch()
    assert detect_language(unknown_file) is None

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert detect_language(empty_dir) is None
