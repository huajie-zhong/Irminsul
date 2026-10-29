"""The marker `irminsul init` writes beside each prompt it scaffolds.

A prompt is text the scaffold expects a person to replace, so the scaffold marks it rather
than anything recognising its wording: `foundation-readiness` reports a doc that still
carries a marker, and `seed` replaces only the text a marker covers.

A marker at the end of a line covers that line. A marker alone on its line covers that line
and the block after it, up to the next blank line outside a fence, which is how a prompt
that is a fenced diagram is marked without writing inside the fence. A marker inside a
fenced block or a code span is an example of the syntax and covers nothing.
"""

from __future__ import annotations

import re

from irminsul.fences import FenceTracker

PLACEHOLDER_MARKER = "<!-- irminsul:placeholder -->"

_MARKER_RE = re.compile(r"<!--\s*irminsul:placeholder\s*-->")
_CODE_SPAN_RE = re.compile(r"(`+).+?\1")


def placeholder_lines(body: str) -> list[int]:
    """The 1-based line numbers of `body` that marked placeholder text covers."""
    covered: list[int] = []
    fence = FenceTracker()
    open_block = False
    for lineno, line in enumerate(body.splitlines(), start=1):
        kind = fence.classify(line)
        if kind != "outside":
            if open_block:
                covered.append(lineno)
            continue
        if not line.strip():
            open_block = False
            continue
        marker = _MARKER_RE.search(_CODE_SPAN_RE.sub("", line))
        if marker is not None:
            covered.append(lineno)
            open_block = open_block or not _MARKER_RE.sub("", line).strip()
        elif open_block:
            covered.append(lineno)
    return covered


def without_marker(line: str) -> str:
    """`line` with its placeholder markers removed, for quoting the prompt it marks."""
    return " ".join(_MARKER_RE.sub("", line).split())
