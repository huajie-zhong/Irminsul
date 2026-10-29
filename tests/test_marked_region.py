"""Tests for the one reader of the text between a start and an end marker comment."""

from __future__ import annotations

import pytest

from irminsul.marked_region import MalformedRegion, Region, find_region

START = "<!-- region-start -->"
END = "<!-- region-end -->"


def _find(text: str) -> Region | None:
    return find_region(text, START, END)


def _malformed(text: str) -> MalformedRegion:
    with pytest.raises(MalformedRegion) as caught:
        _find(text)
    return caught.value


def test_text_without_either_marker_holds_no_region() -> None:
    assert _find("# Title\n\nProse.\n") is None
    assert _find("") is None


def test_one_start_before_one_end_is_the_region() -> None:
    text = f"intro\n{START}\nbody\n{END}\noutro\n"

    region = _find(text)

    assert region == Region(start=text.index(START), end=text.index(END), start_line=1, end_line=3)
    assert text[region.start + len(START) : region.end] == "\nbody\n"


def test_both_markers_on_one_line_are_a_region_on_that_line() -> None:
    text = f"a\nlead {START} inner {END} tail\nb\n"

    region = _find(text)

    assert region == Region(start=text.index(START), end=text.index(END), start_line=1, end_line=1)


def test_offsets_count_every_character_of_a_crlf_text() -> None:
    text = f"one\r\ntwo\r\n{START}\r\nbody\r\n{END}\r\n"

    region = _find(text)

    assert region is not None
    assert text[region.start :].startswith(START)
    assert text[region.end :].startswith(END)
    assert (region.start_line, region.end_line) == (2, 4)


def test_a_marker_inside_a_code_fence_is_not_a_marker() -> None:
    text = f"```markdown\n{START}\n{END}\n```\nprose\n"

    assert _find(text) is None


def test_a_fenced_example_beside_the_real_pair_leaves_the_real_pair() -> None:
    text = f"```\n{START}\n{END}\n```\n{START}\nbody\n{END}\n"

    region = _find(text)

    assert region is not None
    assert (region.start_line, region.end_line) == (4, 6)


@pytest.mark.parametrize(
    ("text", "starts", "ends", "line"),
    [
        (f"a\n{START}\nb\n", 1, 0, 1),
        (f"a\nb\n{END}\n", 0, 1, 2),
        (f"a\n{END}\n{START}\n", 1, 1, 1),
        (f"{START}\n{START}\n{END}\n", 2, 1, 0),
        (f"x\n{START}\n{END}\n{END}\n", 1, 2, 1),
        (f"{START}\n{END}\n{START}\n{END}\n", 2, 2, 0),
        (f"{START} {START}\n{END}\n", 2, 1, 0),
        (f"{END} {START}\n", 1, 1, 0),
    ],
    ids=[
        "start-only",
        "end-only",
        "reversed",
        "two-starts",
        "two-ends",
        "two-pairs",
        "two-starts-on-one-line",
        "reversed-on-one-line",
    ],
)
def test_anything_but_one_start_before_one_end_is_malformed(
    text: str, starts: int, ends: int, line: int
) -> None:
    malformed = _malformed(text)

    assert (malformed.starts, malformed.ends, malformed.line) == (starts, ends, line)


def test_a_malformed_count_leaves_out_the_markers_inside_a_fence() -> None:
    malformed = _malformed(f"```\n{START}\n{END}\n```\n{START}\n")

    assert (malformed.starts, malformed.ends, malformed.line) == (1, 0, 4)
