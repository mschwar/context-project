from pathlib import Path
from ctx.lang_parsers.ruby_parser import parse_ruby_file


def test_methods(tmp_path):
    src = """\
def greet(name)
  "Hello, #{name}"
end

def valid?
  true
end

def save!
  persist
end
"""
    f = tmp_path / "helpers.rb"
    f.write_text(src, encoding="utf-8")
    result = parse_ruby_file(f)
    assert "greet" in result["methods"]
    assert "valid?" in result["methods"]
    assert "save!" in result["methods"]


def test_classes(tmp_path):
    src = """\
class Animal
  def speak; end
end

class Dog < Animal
end

class Pets::Dog
end
"""
    f = tmp_path / "animals.rb"
    f.write_text(src, encoding="utf-8")
    result = parse_ruby_file(f)
    assert "Animal" in result["classes"]
    assert "Dog" in result["classes"]
    assert "Pets::Dog" in result["classes"]


def test_modules(tmp_path):
    src = """\
module Greetable
  def hello; end
end

module Admin::Auth
end
"""
    f = tmp_path / "concerns.rb"
    f.write_text(src, encoding="utf-8")
    result = parse_ruby_file(f)
    assert "Greetable" in result["modules"]
    assert "Admin::Auth" in result["modules"]


def test_class_method(tmp_path):
    src = """\
class User
  def self.find(id)
    nil
  end
end
"""
    f = tmp_path / "user.rb"
    f.write_text(src, encoding="utf-8")
    result = parse_ruby_file(f)
    assert "find" in result["methods"]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.rb"
    f.touch()
    assert parse_ruby_file(f) == {"methods": [], "classes": [], "modules": []}


def test_missing_file(tmp_path):
    assert parse_ruby_file(tmp_path / "missing.rb") == {
        "methods": [], "classes": [], "modules": []
    }
