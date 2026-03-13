"""Tests for ctx.ignore — merged ignore patterns and path matching."""

from __future__ import annotations

import pytest

from ctx.ignore import load_ignore_patterns, should_ignore


def test_load_ignore_patterns_uses_repo_default_file(tmp_path) -> None:
    spec = load_ignore_patterns(tmp_path)

    assert spec.match_file("CONTEXT.md")


def test_load_ignore_patterns_merges_default_and_user(tmp_path) -> None:
    default_patterns = tmp_path / ".ctxignore.default"
    default_patterns.write_text("# defaults\nnode_modules/\n*.pyc\n", encoding="utf-8")
    (tmp_path / ".ctxignore").write_text("# user\ncustom/\n*.log\n", encoding="utf-8")

    spec = load_ignore_patterns(tmp_path, default_patterns_path=default_patterns)

    assert spec.match_file("node_modules/")
    assert spec.match_file("module.pyc")
    assert spec.match_file("custom/")
    assert spec.match_file("server.log")


def test_load_ignore_patterns_finds_project_root_default_when_package_file_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    project_root = tmp_path / "repo"
    module_dir = project_root / "src" / "ctx"
    target_root = project_root / "target"
    module_dir.mkdir(parents=True)
    target_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname = 'ctx'\n", encoding="utf-8")
    (project_root / ".ctxignore.default").write_text("fallback.txt\n", encoding="utf-8")

    monkeypatch.setattr("ctx.ignore.files", lambda _package: tmp_path / "missing-package-resource")
    monkeypatch.setattr("ctx.ignore.__file__", str(module_dir / "ignore.py"))

    spec = load_ignore_patterns(target_root)

    assert spec.match_file("fallback.txt")


def test_should_ignore_directory_appends_trailing_slash(tmp_path) -> None:
    default_patterns = tmp_path / ".ctxignore.default"
    default_patterns.write_text("build/\n", encoding="utf-8")
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    spec = load_ignore_patterns(tmp_path, default_patterns_path=default_patterns)

    assert should_ignore(build_dir, spec, tmp_path) is True


def test_should_ignore_uses_relative_posix_paths(tmp_path) -> None:
    default_patterns = tmp_path / ".ctxignore.default"
    default_patterns.write_text("docs/*.md\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    markdown_file = docs_dir / "guide.md"
    markdown_file.write_text("guide", encoding="utf-8")
    text_file = docs_dir / "guide.txt"
    text_file.write_text("guide", encoding="utf-8")

    spec = load_ignore_patterns(tmp_path, default_patterns_path=default_patterns)

    assert should_ignore(markdown_file, spec, tmp_path) is True
    assert should_ignore(text_file, spec, tmp_path) is False
