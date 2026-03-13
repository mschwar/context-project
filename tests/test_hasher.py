"""Tests for ctx.hasher — file and directory content hashing."""

from __future__ import annotations

import hashlib

import pathspec

from ctx.hasher import hash_directory, hash_file, is_stale


EMPTY_SPEC = pathspec.PathSpec.from_lines("gitwildmatch", [])


def _expected_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _expected_directory_hash(entries: list[str]) -> str:
    return _expected_hash("".join(entries).encode("utf-8"))


def test_hash_file_basic(tmp_path) -> None:
    file_path = tmp_path / "sample.txt"
    payload = b"hello world\n"
    file_path.write_bytes(payload)

    expected = _expected_hash(payload)

    assert hash_file(file_path) == expected
    assert hash_file(file_path) == expected


def test_hash_file_empty(tmp_path) -> None:
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")

    assert hash_file(file_path) == _expected_hash(b"")


def test_hash_file_binary(tmp_path) -> None:
    file_path = tmp_path / "image.bin"
    payload = b"\x00\x01\xff\x10"
    file_path.write_bytes(payload)

    assert hash_file(file_path) == _expected_hash(payload)


def test_hash_directory_basic(tmp_path) -> None:
    file_path = tmp_path / "alpha.txt"
    file_path.write_text("alpha", encoding="utf-8")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    nested_file = subdir / "beta.txt"
    nested_file.write_text("beta", encoding="utf-8")

    subdir_hash = _expected_directory_hash([f"beta.txt:{hash_file(nested_file)}\n"])
    expected = _expected_directory_hash(
        [
            f"alpha.txt:{hash_file(file_path)}\n",
            f"subdir:{subdir_hash}\n",
        ]
    )

    assert hash_directory(tmp_path, EMPTY_SPEC, tmp_path) == expected


def test_hash_directory_ignores_patterns(tmp_path) -> None:
    (tmp_path / "kept.txt").write_text("keep me", encoding="utf-8")
    ignored_file = tmp_path / "ignored.txt"
    ignored_file.write_text("first version", encoding="utf-8")
    spec = pathspec.PathSpec.from_lines("gitwildmatch", ["ignored.txt"])

    first_hash = hash_directory(tmp_path, spec, tmp_path)
    ignored_file.write_text("second version", encoding="utf-8")
    second_hash = hash_directory(tmp_path, spec, tmp_path)

    assert first_hash == second_hash


def test_hash_directory_order_independent(tmp_path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()

    (first_dir / "b.txt").write_text("b", encoding="utf-8")
    (first_dir / "a.txt").write_text("a", encoding="utf-8")

    (second_dir / "a.txt").write_text("a", encoding="utf-8")
    (second_dir / "b.txt").write_text("b", encoding="utf-8")

    assert hash_directory(first_dir, EMPTY_SPEC, first_dir) == hash_directory(second_dir, EMPTY_SPEC, second_dir)


def test_is_stale_different() -> None:
    assert is_stale("sha256:abc", "sha256:def") is True


def test_is_stale_same() -> None:
    assert is_stale("sha256:abc", "sha256:abc") is False
