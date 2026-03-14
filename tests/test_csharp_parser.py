from pathlib import Path
from ctx.lang_parsers.csharp_parser import parse_csharp_file


def test_public_class(tmp_path):
    src = """\
public class OrderService
{
    private int _count;
}

class InternalClass {}
"""
    f = tmp_path / "OrderService.cs"
    f.write_text(src, encoding="utf-8")
    result = parse_csharp_file(f)
    assert "OrderService" in result["classes"]
    assert "InternalClass" not in result["classes"]


def test_public_interface_enum_struct_record(tmp_path):
    src = """\
public interface IRepository { }

public enum Color { Red, Green, Blue }

public struct Point { public int X; public int Y; }

public record Person(string Name, int Age);

interface IInternal {}
enum InternalEnum { A }
"""
    f = tmp_path / "Types.cs"
    f.write_text(src, encoding="utf-8")
    result = parse_csharp_file(f)
    assert "IRepository" in result["interfaces"]
    assert "Color" in result["enums"]
    assert "Point" in result["structs"]
    assert "Person" in result["records"]
    assert "IInternal" not in result["interfaces"]
    assert "InternalEnum" not in result["enums"]


def test_public_methods(tmp_path):
    src = """\
public class Calculator
{
    public int Add(int a, int b) { return a + b; }
    public static void Main(string[] args) { }
    private int Secret() { return 0; }
    internal int InternalMethod() { return 1; }
}
"""
    f = tmp_path / "Calculator.cs"
    f.write_text(src, encoding="utf-8")
    result = parse_csharp_file(f)
    assert "Add" in result["methods"]
    assert "Main" in result["methods"]
    assert "Secret" not in result["methods"]
    assert "InternalMethod" not in result["methods"]


def test_abstract_sealed_static_modifiers(tmp_path):
    src = """\
public abstract class BaseHandler
{
    public abstract void Handle();
}

public sealed class Config {}

public static class Extensions {}
"""
    f = tmp_path / "Base.cs"
    f.write_text(src, encoding="utf-8")
    result = parse_csharp_file(f)
    assert "BaseHandler" in result["classes"]
    assert "Config" in result["classes"]
    assert "Extensions" in result["classes"]


def test_async_and_override_methods(tmp_path):
    src = """\
public class Worker
{
    public async Task RunAsync() { }
    public override string ToString() { return ""; }
}
"""
    f = tmp_path / "Worker.cs"
    f.write_text(src, encoding="utf-8")
    result = parse_csharp_file(f)
    assert "RunAsync" in result["methods"]
    assert "ToString" in result["methods"]


def test_public_properties(tmp_path):
    src = """\
public class Person
{
    public string Name { get; set; }
    public int Age { get; private set; }
    public string FullName => $"{Name}";
    private int _secret { get; set; }
}
"""
    f = tmp_path / "Person.cs"
    f.write_text(src, encoding="utf-8")
    result = parse_csharp_file(f)
    assert "Name" in result["properties"]
    assert "Age" in result["properties"]
    assert "FullName" in result["properties"]
    assert "_secret" not in result["properties"]
    # Properties should not appear in methods
    assert "Name" not in result["methods"]


def test_empty_file(tmp_path):
    f = tmp_path / "Empty.cs"
    f.touch()
    result = parse_csharp_file(f)
    assert result == {
        "classes": [],
        "interfaces": [],
        "enums": [],
        "structs": [],
        "records": [],
        "methods": [],
        "properties": [],
    }


def test_missing_file(tmp_path):
    result = parse_csharp_file(tmp_path / "Missing.cs")
    assert result == {
        "classes": [],
        "interfaces": [],
        "enums": [],
        "structs": [],
        "records": [],
        "methods": [],
        "properties": [],
    }
