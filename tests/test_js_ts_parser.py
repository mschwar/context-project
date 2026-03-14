import pytest
from pathlib import Path
from ctx.lang_parsers.js_ts_parser import parse_js_ts_file


def test_exported_functions(tmp_path):
    src = """\
export function greet(name: string): string {
    return `Hello ${name}`;
}

export async function fetchData(url: string) {
    return fetch(url);
}
"""
    f = tmp_path / "mod.ts"
    f.write_text(src, encoding="utf-8")
    result = parse_js_ts_file(f)
    assert "greet" in result["functions"]
    assert "fetchData" in result["functions"]


def test_exported_arrow_functions(tmp_path):
    src = """\
export const add = (a: number, b: number) => a + b;
export const handler = async (req, res) => {};
export const helper = function() {};
"""
    f = tmp_path / "utils.ts"
    f.write_text(src, encoding="utf-8")
    result = parse_js_ts_file(f)
    assert "add" in result["functions"]
    assert "handler" in result["functions"]
    assert "helper" in result["functions"]


def test_exported_classes(tmp_path):
    src = """\
export class Animal {
    speak() {}
}

export abstract class Shape {
    abstract area(): number;
}
"""
    f = tmp_path / "shapes.ts"
    f.write_text(src, encoding="utf-8")
    result = parse_js_ts_file(f)
    assert result["classes"] == ["Animal", "Shape"]


def test_exported_interfaces_and_types(tmp_path):
    src = """\
export interface User {
    id: number;
    name: string;
}

export type ID = string | number;
export type Callback<T> = (val: T) => void;
"""
    f = tmp_path / "types.ts"
    f.write_text(src, encoding="utf-8")
    result = parse_js_ts_file(f)
    assert result["interfaces"] == ["User"]
    assert "ID" in result["types"]
    assert "Callback" in result["types"]


def test_default_export_detected(tmp_path):
    src = "export default function App() { return null; }\n"
    f = tmp_path / "App.tsx"
    f.write_text(src, encoding="utf-8")
    result = parse_js_ts_file(f)
    assert result["has_default_export"] is True


def test_no_default_export(tmp_path):
    src = "export function helper() {}\n"
    f = tmp_path / "helper.js"
    f.write_text(src, encoding="utf-8")
    result = parse_js_ts_file(f)
    assert result["has_default_export"] is False


def test_empty_file(tmp_path):
    f = tmp_path / "empty.ts"
    f.touch()
    result = parse_js_ts_file(f)
    assert result["functions"] == []
    assert result["classes"] == []
    assert result["interfaces"] == []
    assert result["types"] == []
    assert result["has_default_export"] is False


def test_missing_file(tmp_path):
    result = parse_js_ts_file(tmp_path / "missing.ts")
    assert result["functions"] == []
    assert result["has_default_export"] is False
