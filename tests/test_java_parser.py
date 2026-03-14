from pathlib import Path
from ctx.lang_parsers.java_parser import parse_java_file


def test_public_class(tmp_path):
    src = """\
public class MyService {
    private int count;
}

class PackagePrivateClass {}
"""
    f = tmp_path / "MyService.java"
    f.write_text(src, encoding="utf-8")
    result = parse_java_file(f)
    assert "MyService" in result["classes"]
    assert "PackagePrivateClass" not in result["classes"]


def test_public_interface_enum_record(tmp_path):
    src = """\
public interface Runnable {
    void run();
}

public enum Status { OK, ERROR }

public record Point(int x, int y) {}

interface InternalIface {}
enum InternalEnum { A }
"""
    f = tmp_path / "Types.java"
    f.write_text(src, encoding="utf-8")
    result = parse_java_file(f)
    assert "Runnable" in result["interfaces"]
    assert "Status" in result["enums"]
    assert "Point" in result["records"]
    assert "InternalIface" not in result["interfaces"]
    assert "InternalEnum" not in result["enums"]


def test_public_methods(tmp_path):
    src = """\
public class Calculator {
    public int add(int a, int b) { return a + b; }
    public static void main(String[] args) {}
    private int secret() { return 0; }
    int packageMethod() { return 1; }
}
"""
    f = tmp_path / "Calculator.java"
    f.write_text(src, encoding="utf-8")
    result = parse_java_file(f)
    assert "add" in result["methods"]
    assert "main" in result["methods"]
    assert "secret" not in result["methods"]
    assert "packageMethod" not in result["methods"]


def test_abstract_and_final_modifiers(tmp_path):
    src = """\
public abstract class BaseHandler {
    public abstract void handle();
}

public final class Config {}
"""
    f = tmp_path / "Base.java"
    f.write_text(src, encoding="utf-8")
    result = parse_java_file(f)
    assert "BaseHandler" in result["classes"]
    assert "Config" in result["classes"]


def test_empty_file(tmp_path):
    f = tmp_path / "Empty.java"
    f.touch()
    result = parse_java_file(f)
    assert result == {
        "classes": [],
        "interfaces": [],
        "enums": [],
        "records": [],
        "methods": [],
    }


def test_missing_file(tmp_path):
    result = parse_java_file(tmp_path / "Missing.java")
    assert result == {
        "classes": [],
        "interfaces": [],
        "enums": [],
        "records": [],
        "methods": [],
    }


def test_generic_return_type_method(tmp_path):
    src = """\
public class Repo<T> {
    public List<T> findAll() { return null; }
    public Optional<T> findById(long id) { return null; }
}
"""
    f = tmp_path / "Repo.java"
    f.write_text(src, encoding="utf-8")
    result = parse_java_file(f)
    assert "findAll" in result["methods"]
    assert "findById" in result["methods"]
