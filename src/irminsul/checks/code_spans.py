"""Code spans in a doc body, and whole-token matching of identities inside them."""

from __future__ import annotations

import re
from dataclasses import dataclass

from irminsul.config import IrminsulConfig, in_layer
from irminsul.docgraph import DocNode
from irminsul.frontmatter import StatusEnum

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_SPAN_RE = re.compile(r"(`+)(.+?)\1")
# A dot is a boundary so `protected_paths` is named by `checks.schema_leak.protected_paths`;
# a hyphen is not, so `--format` is not named by `--format-json`.
_TOKEN_EDGE = r"A-Za-z0-9_-"


def mention_regex(pattern: re.Pattern[str]) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_TOKEN_EDGE}])(?:{pattern.pattern})(?![{_TOKEN_EDGE}])")


@dataclass(frozen=True)
class CodeSpan:
    body_line: int
    text: str


def code_spans(body: str) -> list[CodeSpan]:
    spans: list[CodeSpan] = []
    in_fence = False
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            spans.append(CodeSpan(lineno, line))
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
