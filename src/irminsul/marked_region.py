"""The text between a start and an end marker comment, found one way for every caller.

A marker counts only on a line outside a code fence, so a doc that quotes the markers as an
example holds no region. No marker of either kind is no region. One start before one end is
the region, found by `find_region`. Anything else — a marker without its partner, the two
reversed, two of either — raises `MalformedRegion`, because choosing a pair would decide
which of a file's lines a caller rewrites or hides. Each caller words the refusal itself.
A marker may sit mid-line, and both may share one line.
"""

from __future__ import annotations

from dataclasses import dataclass

from irminsul.fences import FenceTracker


@dataclass(frozen=True)
class Region:
    """Where a region lies. `start` and `end` are the offsets of the first character of the
    start and end markers, and `start_line` and `end_line` the 0-based indexes, in
    `text.splitlines()`, of the lines holding them."""

    start: int
    end: int
    start_line: int
    end_line: int


class MalformedRegion(Exception):
    """The markers found do not make one region: `starts` and `ends` are how many of each
    sit outside a fence, and `line` is the 0-based line of the first marker of either kind."""

    def __init__(self, starts: int, ends: int, line: int) -> None:
        super().__init__(f"{starts} start and {ends} end markers, first on line {line + 1}")
        self.starts = starts
        self.ends = ends
        self.line = line


def find_region(text: str, start_marker: str, end_marker: str) -> Region | None:
    """The region `text` marks, or None when it holds neither marker."""
    fence = FenceTracker()
    starts: list[tuple[int, int]] = []
    ends: list[tuple[int, int]] = []
    offset = 0
    for index, (line, raw) in enumerate(
        zip(text.splitlines(), text.splitlines(keepends=True), strict=True)
    ):
        if not fence.consume(line):
            for hits, marker in ((starts, start_marker), (ends, end_marker)):
                at = line.find(marker)
                while at != -1:
                    hits.append((offset + at, index))
                    at = line.find(marker, at + len(marker))
        offset += len(raw)

    if not starts and not ends:
        return None
    if len(starts) == 1 and len(ends) == 1 and starts[0][0] < ends[0][0]:
        return Region(starts[0][0], ends[0][0], starts[0][1], ends[0][1])
    first_line = min(hit[1] for hit in (*starts[:1], *ends[:1]))
    raise MalformedRegion(len(starts), len(ends), first_line)
