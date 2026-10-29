"""ProseFileReferenceCheck — a local Markdown file named in plain text must be a link."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import ClassVar

from markdown_it.token import Token

from irminsul.checks.base import Finding, FindingClass, Severity, certain_audit_nodes
from irminsul.docgraph import DocGraph, is_rfc

_LOCAL_MD_RE = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.md)(?![\w.-])")

CODE_UNLINKED_REFERENCE = "prose-file-reference/unlinked-reference"


class ProseFileReferenceCheck:
    """Local Markdown files named in plain text must be real links, not bare mentions."""

    name: ClassVar[str] = "prose-file-reference"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNLINKED_REFERENCE: (
            "A local `.md` filename is named in plain text without a Markdown link. Convert "
            "it to a link, or put the name in a code span if it is meant as a literal "
            "mention: a code span or a fenced block is not judged here."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNLINKED_REFERENCE: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in certain_audit_nodes(graph):
            if is_rfc(node, graph.config):
                continue
            reported: set[int] = set()
            for line, text in _plain_text(node.tokens):
                match = _LOCAL_MD_RE.search(text)
                if match is None or line in reported:
                    continue
                reported.add(line)
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNLINKED_REFERENCE,
                        severity=Severity.error,
                        message=f"local markdown reference '{match.group(1)}' is not a Markdown link",
                        path=node.path,
                        doc_id=node.id,
                        line=node.file_line(line),
                        suggestion=(
                            "Convert it to a Markdown link, or put the name in a code span "
                            "if it is a literal mention"
                        ),
                    )
                )
        return out


def _plain_text(tokens: list[Token]) -> Iterator[tuple[int, str]]:
    """The runs of text outside a link, as (body line, text).

    Inline code, images, raw HTML, fenced and indented code blocks, and link reference
    definitions are not text, so none of them is read. An inline token carries only the line
    its block starts on, so a run's line is that plus the line breaks before the run's place
    in the block's source.
    """
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        first = token.map[0] + 1 if token.map else 1
        source = token.content
        cursor = 0
        in_link = 0
        for child in token.children:
            if child.type == "link_open":
                in_link += 1
            elif child.type == "link_close":
                in_link -= 1
            elif child.type == "text":
                found = source.find(child.content, cursor)
                if found != -1:
                    cursor = found
                if not in_link:
                    yield first + source.count("\n", 0, cursor), child.content
                if found != -1:
                    cursor += len(child.content)
