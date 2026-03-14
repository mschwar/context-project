from pathlib import Path
from ctx.lang_parsers.kotlin_parser import parse_kotlin_file


def test_functions(tmp_path):
    src = """\
fun topLevel(x: Int): Int = x

suspend fun asyncFetch(): String = ""

private fun hidden() {}
"""
    f = tmp_path / "main.kt"
    f.write_text(src, encoding="utf-8")
    result = parse_kotlin_file(f)
    assert "topLevel" in result["functions"]
    assert "asyncFetch" in result["functions"]
    assert "hidden" in result["functions"]  # private funs still appear (Kotlin default is public)


def test_classes(tmp_path):
    src = """\
class Service
data class Point(val x: Int, val y: Int)
abstract class Base
sealed class Result
"""
    f = tmp_path / "models.kt"
    f.write_text(src, encoding="utf-8")
    result = parse_kotlin_file(f)
    assert "Service" in result["classes"]
    assert "Point" in result["classes"]
    assert "Base" in result["classes"]
    assert "Result" in result["classes"]


def test_interfaces_and_objects(tmp_path):
    src = """\
interface Repository
fun interface Predicate<T>

object Singleton
companion object {}
"""
    f = tmp_path / "types.kt"
    f.write_text(src, encoding="utf-8")
    result = parse_kotlin_file(f)
    assert "Repository" in result["interfaces"]
    assert "Singleton" in result["objects"]


def test_enum_class(tmp_path):
    src = """\
enum class Color { RED, GREEN, BLUE }
enum class Direction { NORTH, SOUTH }
"""
    f = tmp_path / "enums.kt"
    f.write_text(src, encoding="utf-8")
    result = parse_kotlin_file(f)
    assert "Color" in result["enums"]
    assert "Direction" in result["enums"]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.kt"
    f.touch()
    assert parse_kotlin_file(f) == {
        "functions": [], "classes": [], "interfaces": [], "objects": [], "enums": []
    }


def test_missing_file(tmp_path):
    assert parse_kotlin_file(tmp_path / "missing.kt") == {
        "functions": [], "classes": [], "interfaces": [], "objects": [], "enums": []
    }
