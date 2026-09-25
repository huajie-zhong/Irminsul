"""CommonMark fenced-code-block state, as the one reader every consumer shares.

A fence is text syntax rather than a doc-graph concern, so this module depends on nothing
but the standard library and the anchor parser, the checks, and the graph's own section
reader can all read a fence the same way. A local reading written per call site is how a
four-backtick block quoting a three-backtick example came to be read as live prose, which
raised a certain finding on a document that was correctly documenting the syntax.
"""

from __future__ import annotations

import re
from typing import Literal

_FENCE_RE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")

LineKind = Literal["outside", "marker", "content"]


class FenceTracker:
    """CommonMark fenced-code-block state, fed one body line at a time.

    A fence closes only on the same character, at least as long as the opening
    marker, and without an info string. So a ````-fenced quote may contain ```
    blocks verbatim, and a stray ``` inside a ~~~ block is content rather than
    a toggle.
    """

    __slots__ = ("_char", "_info", "_length")

    def __init__(self) -> None:
        self._char: str | None = None
        self._length = 0
        self._info = ""

    @property
    def inside(self) -> bool:
        return self._char is not None

    @property
    def info(self) -> str:
        """The open block's info string — its language label — or empty outside a block."""
        return self._info

    def consume(self, line: str) -> bool:
        """Feed one line; True when it is fence syntax or fenced content."""
        return self.classify(line) != "outside"

    def classify(self, line: str) -> LineKind:
        """Feed one line and report what it is, so no caller has to re-derive it.

        `marker` is an opening or closing fence, `content` a line the fence wraps, and
        `outside` ordinary prose. A caller that only skips code wants `consume`; the ones
        that treat the fence line differently from what it wraps need this distinction, and
        reading it off `inside` before and after the call is how a local reading of a fence
        gets written instead of shared.
        """
        match = _FENCE_RE.match(line)
        if match is None:
            return "content" if self.inside else "outside"

        marker = match.group("marker")
        info = match.group("info")
        if self._char is None:
            if marker[0] == "`" and "`" in info:
                return "outside"
            self._char = marker[0]
            self._length = len(marker)
            self._info = info.strip()
        elif marker[0] == self._char and len(marker) >= self._length and not info.strip():
            self._char = None
            self._length = 0
            self._info = ""
        else:
            # A marker that cannot close the open block — a different character, a shorter
            # run, or one carrying an info string — is content, not a toggle.
            return "content"
        return "marker"
