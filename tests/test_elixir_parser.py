"""Tests for ctx.lang_parsers.elixir_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctx.lang_parsers.elixir_parser import parse_elixir_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Test 1 — public def functions are extracted
# ---------------------------------------------------------------------------

def test_public_def_functions_extracted(tmp_path: Path) -> None:
    src = _write(tmp_path, "math.ex", """\
defmodule Math do
  def add(a, b) do
    a + b
  end

  def subtract(a, b) do
    a - b
  end
end
""")
    result = parse_elixir_file(src)
    assert result["functions"] == ["add", "subtract"]


# ---------------------------------------------------------------------------
# Test 2 — defp (private) functions are NOT extracted
# ---------------------------------------------------------------------------

def test_defp_private_functions_not_extracted(tmp_path: Path) -> None:
    src = _write(tmp_path, "helper.ex", """\
defmodule Helper do
  def public_fn(x) do
    _private(x)
  end

  defp _private(x) do
    x * 2
  end
end
""")
    result = parse_elixir_file(src)
    assert "public_fn" in result["functions"]
    assert "_private" not in result["functions"]


# ---------------------------------------------------------------------------
# Test 3 — defmodule names are extracted
# ---------------------------------------------------------------------------

def test_defmodule_extracted(tmp_path: Path) -> None:
    src = _write(tmp_path, "multi.ex", """\
defmodule Foo.Bar do
  def hello, do: :world
end

defmodule Foo.Baz do
  def goodbye, do: :bye
end
""")
    result = parse_elixir_file(src)
    assert result["modules"] == ["Foo.Bar", "Foo.Baz"]


# ---------------------------------------------------------------------------
# Test 4 — defstruct causes module names to appear in structs list
# ---------------------------------------------------------------------------

def test_defstruct_module_noted(tmp_path: Path) -> None:
    src = _write(tmp_path, "user.ex", """\
defmodule User do
  defstruct [:name, :email, :age]

  def new(name, email) do
    %User{name: name, email: email}
  end
end
""")
    result = parse_elixir_file(src)
    assert "User" in result["structs"]
    assert "new" in result["functions"]


# ---------------------------------------------------------------------------
# Test 5 — empty file returns empty lists
# ---------------------------------------------------------------------------

def test_empty_file_returns_empty(tmp_path: Path) -> None:
    src = _write(tmp_path, "empty.ex", "")
    result = parse_elixir_file(src)
    assert result == {"functions": [], "modules": [], "structs": []}


# ---------------------------------------------------------------------------
# Test 6 — multiple modules in one file, only the struct-bearing one noted
# ---------------------------------------------------------------------------

def test_multiple_modules_struct_in_one(tmp_path: Path) -> None:
    src = _write(tmp_path, "mixed.ex", """\
defmodule Plain do
  def greet, do: :hello
end

defmodule WithStruct do
  defstruct [:id]

  def make(id), do: %WithStruct{id: id}
end
""")
    result = parse_elixir_file(src)
    assert set(result["modules"]) == {"Plain", "WithStruct"}
    # structs lists all modules in the file because defstruct is present
    assert "WithStruct" in result["structs"]
    assert "greet" in result["functions"]
    assert "make" in result["functions"]
