"""DuplicateBlockCheck — a paragraph or list item repeated within one doc or copied into another."""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.code_spans import is_live_doc
from irminsul.docgraph import DocGraph, DocNode

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MIN_CHARS = 80

CODE_REPEATED_BLOCK = "duplicate-block/repeated-block"
CODE_COPIED_BLOCK = "duplicate-block/copied-block"


def _blocks(body: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    start: int | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal start, lines
        if start is not None and lines:
            blocks.append((start, " ".join(" ".join(lines).split())))
        start, lines = None, []

    in_fence = False
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence or not line.strip() or line.lstrip().startswith("#"):
            flush()
            continue
        if _LIST_ITEM_RE.match(line):
            flush()
            start, lines = lineno, [_LIST_ITEM_RE.sub("", line, count=1)]
            continue
        if start is None:
            start = lineno
        lines.append(line)
    flush()
    return blocks


class DuplicateBlockCheck:
    name: ClassVar[str] = "duplicate-block"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_REPEATED_BLOCK: (
            f"A paragraph or list item of at least {_MIN_CHARS} characters appears more "
            "than once in the same doc. One copy is usually a merge or edit leftover, and "
            "the two will drift apart. Delete the repeat."
        ),
        CODE_COPIED_BLOCK: (
            f"A paragraph or list item of at least {_MIN_CHARS} characters in a live doc "
            "appears verbatim in another live doc. Each fact has one owner; keep it there "
            "and link to it from the other doc."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_REPEATED_BLOCK: FindingClass.certain,
        CODE_COPIED_BLOCK: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            out.extend(self._repeats(node))
        out.extend(self._copies(graph))
        return out

    def _copies(self, graph: DocGraph) -> list[Finding]:
        owners: dict[str, tuple[DocNode, int]] = {}
        out: list[Finding] = []
        live = [n for n in graph.nodes.values() if is_live_doc(n, graph.config)]
        for node in sorted(live, key=lambda n: n.path.as_posix()):
            seen_here: set[str] = set()
            for body_line, text in _blocks(node.body):
                if len(text) < _MIN_CHARS or text in seen_here:
                    continue
                seen_here.add(text)
                owner = owners.get(text)
                if owner is None:
                    owners[text] = (node, body_line)
                    continue
                owner_node, owner_line = owner
                where = f"{owner_node.path.as_posix()}:{owner_node.file_line(owner_line)}"
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_COPIED_BLOCK,
                        severity=self.default_severity,
                        message=f"block copies the one at {where} verbatim",
                        path=node.path,
                        doc_id=node.id,
                        line=node.file_line(body_line),
                        suggestion=f"keep the block in one doc and link to {where}",
                        data={"problem": "copied-block", "first": where},
                    )
                )
        return out

    def _repeats(self, node: DocNode) -> list[Finding]:
        first_seen: dict[str, int] = {}
        out: list[Finding] = []
        for body_line, text in _blocks(node.body):
            if len(text) < _MIN_CHARS:
                continue
            if text not in first_seen:
                first_seen[text] = body_line
                continue
            first_line = node.file_line(first_seen[text])
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_REPEATED_BLOCK,
                    severity=Severity.error,
                    message=f"block repeats the one at line {first_line} verbatim",
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(body_line),
                    suggestion="Delete the repeated block",
                    data={"problem": "repeated-block", "first_line": str(first_line)},
                )
            )
        return out
