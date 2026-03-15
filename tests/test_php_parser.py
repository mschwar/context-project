from pathlib import Path
from ctx.lang_parsers.php_parser import parse_php_file


def test_public_functions(tmp_path):
    src = """\
<?php
class Service {
    public function doWork(): void {}
    public static function create(): self { return new self(); }
    private function hidden(): void {}
    protected function alsoHidden(): void {}
}
"""
    f = tmp_path / "Service.php"
    f.write_text(src, encoding="utf-8")
    result = parse_php_file(f)
    assert "doWork" in result["functions"]
    assert "create" in result["functions"]
    assert "hidden" not in result["functions"]
    assert "alsoHidden" not in result["functions"]


def test_classes(tmp_path):
    src = """\
<?php
class User {}
abstract class BaseModel {}
final class Config {}
"""
    f = tmp_path / "models.php"
    f.write_text(src, encoding="utf-8")
    result = parse_php_file(f)
    assert "User" in result["classes"]
    assert "BaseModel" in result["classes"]
    assert "Config" in result["classes"]


def test_interface_trait_enum(tmp_path):
    src = """\
<?php
interface Countable {}
trait Timestampable {}
enum Status { case Active; case Inactive; }
"""
    f = tmp_path / "types.php"
    f.write_text(src, encoding="utf-8")
    result = parse_php_file(f)
    assert "Countable" in result["interfaces"]
    assert "Timestampable" in result["traits"]
    assert "Status" in result["enums"]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.php"
    f.touch()
    assert parse_php_file(f) == {
        "functions": [], "classes": [], "interfaces": [], "traits": [], "enums": []
    }


def test_missing_file(tmp_path):
    assert parse_php_file(tmp_path / "missing.php") == {
        "functions": [], "classes": [], "interfaces": [], "traits": [], "enums": []
    }
