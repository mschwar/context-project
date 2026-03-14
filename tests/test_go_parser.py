from pathlib import Path
from ctx.lang_parsers.go_parser import parse_go_file


def test_exported_functions(tmp_path):
    src = """\
package main

func ExportedFunc(x int) int { return x }
func privateFunc() {}
func (r Receiver) ExportedMethod() string { return "" }
func (r Receiver) privateMethod() {}
"""
    f = tmp_path / "main.go"
    f.write_text(src, encoding="utf-8")
    result = parse_go_file(f)
    assert "ExportedFunc" in result["functions"]
    assert "ExportedMethod" in result["functions"]
    assert "privateFunc" not in result["functions"]
    assert "privateMethod" not in result["functions"]


def test_exported_types(tmp_path):
    src = """\
package shapes

type Circle struct { Radius float64 }
type Stringer interface { String() string }
type privateType struct{}
"""
    f = tmp_path / "shapes.go"
    f.write_text(src, encoding="utf-8")
    result = parse_go_file(f)
    assert "Circle" in result["types"]
    assert "Stringer" in result["types"]
    assert "privateType" not in result["types"]


def test_exported_constants(tmp_path):
    src = """\
package config

const MaxRetries = 3
const minDelay = 10

const (
    StatusOK      = 200
    statusError   = 500
    StatusCreated         // iota-style: no explicit assignment
)

var AVariable = 1
"""
    f = tmp_path / "config.go"
    f.write_text(src, encoding="utf-8")
    result = parse_go_file(f)
    assert set(result["constants"]) == {"MaxRetries", "StatusOK", "StatusCreated"}
    assert "minDelay" not in result["constants"]
    assert "statusError" not in result["constants"]
    assert "AVariable" not in result["constants"]


def test_exported_variables(tmp_path):
    src = """\
package log

var DefaultLogger = newLogger()
var internalBuffer []byte
"""
    f = tmp_path / "log.go"
    f.write_text(src, encoding="utf-8")
    result = parse_go_file(f)
    assert "DefaultLogger" in result["variables"]
    assert "internalBuffer" not in result["variables"]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.go"
    f.touch()
    result = parse_go_file(f)
    assert result == {
        "functions": [],
        "types": [],
        "constants": [],
        "variables": [],
    }


def test_missing_file(tmp_path):
    result = parse_go_file(tmp_path / "missing.go")
    assert result == {
        "functions": [],
        "types": [],
        "constants": [],
        "variables": [],
    }
