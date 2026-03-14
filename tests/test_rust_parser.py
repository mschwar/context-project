import pytest
from pathlib import Path
from ctx.lang_parsers.rust_parser import parse_rust_file


def test_pub_functions(tmp_path):
    src = """\
pub fn add(a: i32, b: i32) -> i32 { a + b }
pub async fn fetch(url: &str) -> Result<String, Error> { todo!() }
fn private_helper() {}
"""
    f = tmp_path / "lib.rs"
    f.write_text(src, encoding="utf-8")
    result = parse_rust_file(f)
    assert "add" in result["functions"]
    assert "fetch" in result["functions"]
    assert "private_helper" not in result["functions"]


def test_pub_structs(tmp_path):
    src = """\
pub struct Point { x: f64, y: f64 }
pub(crate) struct Internal;
struct Private;
"""
    f = tmp_path / "geometry.rs"
    f.write_text(src, encoding="utf-8")
    result = parse_rust_file(f)
    assert "Point" in result["structs"]
    assert "Internal" in result["structs"]
    assert "Private" not in result["structs"]


def test_pub_enums(tmp_path):
    src = """\
pub enum Direction { North, South, East, West }
enum Hidden { A, B }
"""
    f = tmp_path / "direction.rs"
    f.write_text(src, encoding="utf-8")
    result = parse_rust_file(f)
    assert result["enums"] == ["Direction"]


def test_pub_traits(tmp_path):
    src = """\
pub trait Drawable { fn draw(&self); }
trait PrivateTrait {}
"""
    f = tmp_path / "traits.rs"
    f.write_text(src, encoding="utf-8")
    result = parse_rust_file(f)
    assert result["traits"] == ["Drawable"]


def test_modules(tmp_path):
    src = """\
pub mod network;
mod internal;
pub(crate) mod utils;
"""
    f = tmp_path / "main.rs"
    f.write_text(src, encoding="utf-8")
    result = parse_rust_file(f)
    assert "network" in result["modules"]
    assert "internal" in result["modules"]
    assert "utils" in result["modules"]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.rs"
    f.touch()
    result = parse_rust_file(f)
    assert result == {
        "functions": [],
        "structs": [],
        "enums": [],
        "traits": [],
        "modules": [],
    }


def test_missing_file(tmp_path):
    result = parse_rust_file(tmp_path / "missing.rs")
    assert result == {
        "functions": [],
        "structs": [],
        "enums": [],
        "traits": [],
        "modules": [],
    }
