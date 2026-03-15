from pathlib import Path
from ctx.lang_parsers.swift_parser import parse_swift_file


def test_functions(tmp_path):
    src = """\
public func greet(name: String) -> String { return "Hi" }
func internalHelper() {}
private func secretHelper() {}
fileprivate func alsoSecret() {}
"""
    f = tmp_path / "helpers.swift"
    f.write_text(src, encoding="utf-8")
    result = parse_swift_file(f)
    assert "greet" in result["functions"]
    assert "internalHelper" in result["functions"]
    assert "secretHelper" not in result["functions"]
    assert "alsoSecret" not in result["functions"]


def test_classes_and_structs(tmp_path):
    src = """\
public class ViewController {}
final class AppDelegate {}
struct Point { var x: Int; var y: Int }
public struct Config {}
"""
    f = tmp_path / "types.swift"
    f.write_text(src, encoding="utf-8")
    result = parse_swift_file(f)
    assert "ViewController" in result["classes"]
    assert "AppDelegate" in result["classes"]
    assert "Point" in result["structs"]
    assert "Config" in result["structs"]


def test_protocols_and_enums(tmp_path):
    src = """\
protocol Identifiable { var id: Int { get } }
public protocol Drawable {}
enum Direction { case north, south, east, west }
public enum Status { case active, inactive }
"""
    f = tmp_path / "abstractions.swift"
    f.write_text(src, encoding="utf-8")
    result = parse_swift_file(f)
    assert "Identifiable" in result["protocols"]
    assert "Drawable" in result["protocols"]
    assert "Direction" in result["enums"]
    assert "Status" in result["enums"]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.swift"
    f.touch()
    assert parse_swift_file(f) == {
        "functions": [], "classes": [], "structs": [], "protocols": [], "enums": []
    }


def test_missing_file(tmp_path):
    assert parse_swift_file(tmp_path / "missing.swift") == {
        "functions": [], "classes": [], "structs": [], "protocols": [], "enums": []
    }
