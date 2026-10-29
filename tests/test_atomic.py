"""`write_atomic`: a file is replaced whole or not at all, in the line endings it had."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from irminsul.atomic import write_atomic


def test_the_endings_a_file_had_are_kept_unless_the_caller_pins_them(tmp_path: Path) -> None:
    crlf, fresh = tmp_path / "crlf.md", tmp_path / "nested" / "fresh.md"
    crlf.write_bytes(b"one\r\ntwo\r\n")

    write_atomic(crlf, "one\ntwo\nthree\n")
    write_atomic(fresh, "one\ntwo\n")

    assert crlf.read_bytes() == b"one\r\ntwo\r\nthree\r\n"
    assert fresh.read_bytes() == b"one\ntwo\n"
    write_atomic(crlf, "one\n", newline="\n")
    assert crlf.read_bytes() == b"one\n"


def test_a_mixed_file_takes_the_ending_most_of_its_lines_had(tmp_path: Path) -> None:
    mostly_crlf, mostly_lf = tmp_path / "a.md", tmp_path / "b.md"
    mostly_crlf.write_bytes(b"one\r\ntwo\r\nthree\n")
    mostly_lf.write_bytes(b"one\r\ntwo\nthree\nfour\n")

    write_atomic(mostly_crlf, "x\ny\n")
    write_atomic(mostly_lf, "x\ny\n")

    assert mostly_crlf.read_bytes() == b"x\r\ny\r\n"
    assert mostly_lf.read_bytes() == b"x\ny\n"


def test_a_file_named_like_the_temporary_one_is_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_text("before\n", encoding="utf-8")
    neighbour = tmp_path / "doc.md.tmp"
    neighbour.write_text("somebody's file\n", encoding="utf-8")

    write_atomic(target, "after\n")

    assert target.read_text(encoding="utf-8") == "after\n"
    assert neighbour.read_text(encoding="utf-8") == "somebody's file\n"


def test_a_failed_replace_leaves_the_file_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "doc.md"
    target.write_text("before\n", encoding="utf-8")

    def refuse(src: object, dst: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(PermissionError):
        write_atomic(target, "after\n")

    assert sorted(path.name for path in tmp_path.iterdir()) == ["doc.md"]
    assert target.read_text(encoding="utf-8") == "before\n"
