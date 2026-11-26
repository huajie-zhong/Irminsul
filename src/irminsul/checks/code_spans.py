"""Code spans in a doc body, and whole-token matching of identities inside them."""

from __future__ import annotations

import re
from dataclasses import dataclass

from irminsul.config import IrminsulConfig, in_layer
from irminsul.docgraph import DocNode
from irminsul.fences import FenceTracker
from irminsul.frontmatter import StatusEnum

_INLINE_SPAN_RE = re.compile(r"(`+)(.+?)\1")
_SPAN_OR_COMMENT_RE = re.compile(r"(`+)(.+?)\1|<!--|-->")
# A dot is a boundary so `protected_paths` is named by `checks.schema_leak.protected_paths`;
# a hyphen is not, so `--format` is not named by `--format-json`.
_TOKEN_EDGE = r"A-Za-z0-9_-"


def mention_regex(pattern: re.Pattern[str]) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_TOKEN_EDGE}])(?:{pattern.pattern})(?![{_TOKEN_EDGE}])")


@dataclass(frozen=True)
class CodeSpan:
    body_line: int
    text: str
    fenced: bool = False
    """Whether the text is a line of a fenced block rather than an inline span."""


class CommentTracker:
    """Whether a line of a body lies in an HTML comment, fed one line outside fences at a
    time. A comment marker quoted in a code span is prose and opens or closes nothing, so
    `<!-- anchor: path#symbol -->` written as an example does not hide the lines after it."""

    __slots__ = ("inside",)

    def __init__(self) -> None:
        self.inside = False

    def read(self, line: str) -> tuple[bool, list[str]]:
        """Feed one line: whether it began inside a comment, and the text of each code span
        on it that lies outside every comment."""
        began_inside = self.inside
        spans: list[str] = []
        for match in _SPAN_OR_COMMENT_RE.finditer(line):
            token = match.group(0)
            if self.inside:
                self.inside = token != "-->"
            elif token == "<!--":
                self.inside = True
            elif match.group(1):
                spans.append(match.group(2))
        return began_inside, spans


def code_spans(body: str, *, skip_comments: bool = False) -> list[CodeSpan]:
    """Each code span of `body`, a line of a fenced block counted as one. With
    `skip_comments`, a span inside an HTML comment is left out: what a scaffold's guiding
    comment shows is not something the doc names."""
    spans: list[CodeSpan] = []
    fence = FenceTracker()
    comments = CommentTracker()
    for lineno, line in enumerate(body.splitlines(), start=1):
        if not comments.inside:
            kind = fence.classify(line)
            if kind != "outside":
                if kind == "content":
                    spans.append(CodeSpan(lineno, line, fenced=True))
                continue
        if skip_comments:
            spans.extend(CodeSpan(lineno, text) for text in comments.read(line)[1])
            continue
        spans.extend(CodeSpan(lineno, m.group(2)) for m in _INLINE_SPAN_RE.finditer(line))
    return spans


def token_pattern(identity: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_TOKEN_EDGE}]){re.escape(identity)}(?![{_TOKEN_EDGE}])")


def names_token(spans: list[CodeSpan], identity: str) -> bool:
    pattern = token_pattern(identity)
    return any(pattern.search(span.text) for span in spans)


def is_guidance(node: DocNode, config: IrminsulConfig | None) -> bool:
    """Neither an RFC record nor a decision record, which say what held when written."""
    config = config or IrminsulConfig()
    return not in_layer(config, node.path, "rfcs") and not in_layer(config, node.path, "decisions")


def is_live_doc(node: DocNode, config: IrminsulConfig | None) -> bool:
    """Current guidance: stable, and neither an RFC record nor a decision record."""
    return node.frontmatter.status == StatusEnum.stable and is_guidance(node, config)
