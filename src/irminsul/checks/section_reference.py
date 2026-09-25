"""SectionReferenceCheck — prose that points at a part of a document that isn't there."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.fences import FenceTracker

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_TABLE_RE = re.compile(r"^\s*\|")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_APPENDIX_RE = re.compile(r"\bAppendix\s+([A-Z0-9]{1,3})\b")
_DIRECTIONAL_RE = re.compile(
    r"\b(?:see|in|under)\s+(?:the\s+)?([A-Za-z][A-Za-z`' -]{1,40}?)\s+(below|above)\b",
    re.IGNORECASE,
)
_QUOTED_RE = re.compile(r"`+[^`]*`+|\"[^\"]*\"|“[^”]*”")
_LINK_TARGET_RE = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
#: What follows `Appendix B` when the appendix is one of *this* document's sections:
#: `below`, `above`, or an explicit self-reference. Positive evidence is required before
#: reporting a missing local section, because the alternative was a keyword list of ways
#: to name somebody else's document, which can never be finished — `Appendix B of RFC
#: 9110` was caught by it and `Appendix B, see RFC 9110` was not, and both are true
#: sentences. A reference whose target cannot be established is left alone.
_LOCAL_AFTER_RE = re.compile(
    r"^[\s,;.]*(?:\(see\s+)?(?:below|above)\b"
    r"|^[\s,;.]*(?:of|in)\s+th(?:is|e\s+present)\s+"
    r"(?:document|doc|record|guide|page|file|section)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "each",
        "one",
        "its",
        "section",
        "part",
        "heading",
    }
)
_BLOCK_WORDS = {
    "table": "table",
    "tables": "table",
    "list": "list",
    "example": "fence",
    "examples": "fence",
    "snippet": "fence",
    "block": "fence",
    "code": "fence",
    "diagram": "fence",
}

CODE_MISSING_APPENDIX = "section-reference/missing-appendix"
CODE_MISSING_TARGET = "section-reference/missing-target"


def _lines(node: DocNode) -> list[tuple[int, str, bool]]:
    out: list[tuple[int, str, bool]] = []
    fence = FenceTracker()
    for lineno, line in enumerate(node.body.splitlines(), start=1):
        out.append((lineno, line, fence.consume(line)))
    return out


def _headings(node: DocNode) -> list[tuple[int, str]]:
    return [
        (lineno, match.group(1).replace("`", "").lower())
        for lineno, line, fenced in _lines(node)
        if not fenced and (match := _HEADING_RE.match(line))
    ]


def _words(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if len(w) >= 3 and w not in _STOPWORDS]


def _heading_has_words(heading: str, words: list[str]) -> bool:
    heading_words = _WORD_RE.findall(heading)
    return all(any(hw.startswith(w[:4]) for hw in heading_words) for w in words)


def _block_kind_present(lines: list[tuple[int, str, bool]], kind: str) -> bool:
    for _, line, fenced in lines:
        if kind == "fence" and fenced:
            return True
        if fenced:
            continue
        if kind == "table" and _TABLE_RE.match(line):
            return True
        if kind == "list" and _LIST_RE.match(line):
            return True
    return False


class SectionReferenceCheck:
    name: ClassVar[str] = "section-reference"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_APPENDIX: (
            "Prose cites `Appendix <label>`, but the referenced doc (the first Markdown "
            "link on the line, otherwise this doc) has no heading starting with that "
            "appendix. Link the section that holds the content, or remove the reference. "
            "Only a reference with evidence that it means *this* document is checked: a "
            "Markdown link to a document in the tree, or wording that says so — `below`, "
            "`above`, `of this document`. An appendix named with no such evidence, such "
            "as `Appendix B of RFC 9110`, belongs to a document whose headings are not "
            "ours to read, and nothing here verifies that it exists."
        ),
        CODE_MISSING_TARGET: (
            "Prose says to see something `below` or `above`, but no heading in that "
            "direction carries those words and, for a table, list, or example, no such "
            "block is there. Point at the real section, or remove the reference."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_APPENDIX: FindingClass.certain,
        CODE_MISSING_TARGET: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            out.extend(self._scan(graph, node))
        return out

    def _scan(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        lines = _lines(node)
        out: list[Finding] = []
        for index, (lineno, raw, fenced) in enumerate(lines):
            # A quoted or code-spanned phrase is being mentioned, not used as a pointer.
            line = raw if fenced else _QUOTED_RE.sub(lambda m: " " * len(m.group(0)), raw)
            for match in _APPENDIX_RE.finditer(line):
                target = self._link_target(graph, node, raw)
                if target is None:
                    if not _LOCAL_AFTER_RE.match(line[match.end() :]):
                        # Nothing establishes which document this appendix belongs to, so
                        # there is no local section to be missing. Reporting one would be
                        # a certain error resting on a guess.
                        continue
                    target = node
                label = f"appendix {match.group(1).lower()}"
                if any(text.startswith(label) for _, text in _headings(target)):
                    continue
                out.append(
                    self._finding(
                        node,
                        lineno,
                        CODE_MISSING_APPENDIX,
                        f"'Appendix {match.group(1)}' is not a section of {target.path.as_posix()}",
                    )
                )
            for match in _DIRECTIONAL_RE.finditer(line):
                phrase, direction = match.group(1), match.group(2).lower()
                words = _words(phrase)
                if not words:
                    continue
                scope = lines[index + 1 :] if direction == "below" else lines[:index]
                if self._resolves(scope, words):
                    continue
                out.append(
                    self._finding(
                        node,
                        lineno,
                        CODE_MISSING_TARGET,
                        f"'{match.group(0)}' names nothing {direction} in this doc",
                    )
                )
        return out

    @staticmethod
    def _resolves(scope: list[tuple[int, str, bool]], words: list[str]) -> bool:
        block_kinds = {_BLOCK_WORDS[w] for w in words if w in _BLOCK_WORDS}
        if block_kinds and all(_block_kind_present(scope, kind) for kind in block_kinds):
            return True
        headings = [
            match.group(1).replace("`", "").lower()
            for _, line, fenced in scope
            if not fenced and (match := _HEADING_RE.match(line))
        ]
        return any(_heading_has_words(heading, words) for heading in headings)

    @staticmethod
    def _link_target(graph: DocGraph, node: DocNode, line: str) -> DocNode | None:
        match = _LINK_TARGET_RE.search(line)
        if match is None:
            return None
        joined = posixpath.normpath(posixpath.join(node.path.parent.as_posix(), match.group(1)))
        return graph.by_path.get(Path(joined))

    def _finding(self, node: DocNode, body_line: int, code: str, message: str) -> Finding:
        return Finding(
            check=self.name,
            code=code,
            severity=Severity.error
            if self.classes[code] is FindingClass.certain
            else Severity.warning,
            message=message,
            path=node.path,
            doc_id=node.id,
            line=node.file_line(body_line),
            suggestion="Point at the section that exists, or remove the reference",
        )
