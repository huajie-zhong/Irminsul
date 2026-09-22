"""RealityCheck — docs describe what is true now, and say where a choice was recorded.

Three wordings are reported:

- speculative language (planned, roadmap, v1.2) in a layer with `forbid_speculation`;
- history narration (previously, used to be, then we switched) in the same layers, which
  turns a component doc into a changelog;
- decision wording (we chose, we decided) in any live doc whose paragraph does not link to
  a decision record, so a choice cannot live outside the ADRs.
"""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.code_spans import is_live_doc
from irminsul.config import IrminsulConfig, layer_prefix
from irminsul.docgraph import DocGraph, DocNode, layer_rules

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_SPECULATIVE_RE = re.compile(
    r"\b(planned|deferred|sprint|roadmap|future|upcoming|v\d+\.\d+)\b",
    re.IGNORECASE,
)
_HISTORY_RE = re.compile(
    r"\b(previously|formerly|historically|used to (?:be|do|have|work|run|live|call|say)"
    r"|then we|we (?:then )?(?:switched|moved|migrated|replaced|rewrote))\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"\bwe (?:chose|decided|picked|went with|opted)\b|\bthe decision (?:was|is) to\b",
    re.IGNORECASE,
)


def _decision_link_re(graph: DocGraph) -> re.Pattern[str]:
    """A markdown link into the configured decisions folder."""
    folder = layer_prefix(graph.config or IrminsulConfig(), "decisions").rsplit("/", 1)[-1]
    return re.compile(rf"\]\([^)]*(?<![\w-]){re.escape(folder)}/")


CODE_SPECULATIVE_LANGUAGE = "reality/speculative-language"
CODE_HISTORY_NARRATION = "reality/history-narration"
CODE_UNRECORDED_DECISION = "reality/unrecorded-decision"


class RealityCheck:
    name: ClassVar[str] = "reality"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_SPECULATIVE_LANGUAGE: (
            "A doc in a layer that forbids speculation uses speculative language (planned, "
            "roadmap, future, v1.2, ...). Move future plans to an RFC; these docs describe "
            "what is true now."
        ),
        CODE_HISTORY_NARRATION: (
            "A doc in a layer that forbids speculation narrates history (previously, used to "
            "be, then we switched). Describe the present; the reasons for a change belong in "
            "an ADR."
        ),
        CODE_UNRECORDED_DECISION: (
            "A live doc states a decision (we chose, we decided) in a paragraph that links to "
            "no decision record. Record the choice in an ADR and link it, or describe the "
            "behaviour without the decision."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_SPECULATIVE_LANGUAGE: FindingClass.hint,
        CODE_HISTORY_NARRATION: FindingClass.hint,
        CODE_UNRECORDED_DECISION: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            rules = layer_rules(node, graph.config)
            if rules is not None and rules[1].forbid_speculation:
                out.extend(self._speculation(node))
            if is_live_doc(node, graph.config):
                out.extend(self._decisions(node, _decision_link_re(graph)))
        return out

    def _speculation(self, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        for lineno, line in _prose_lines(node.body):
            # A code span such as a `planned` claim state names a value, not a plan.
            prose = _INLINE_CODE_RE.sub("", line)
            m = _SPECULATIVE_RE.search(prose)
            if m:
                out.append(
                    self._finding(
                        node,
                        lineno,
                        CODE_SPECULATIVE_LANGUAGE,
                        f"speculative keyword '{m.group()}' in a layer that forbids speculation",
                        "Move future plans to an RFC or roadmap doc",
                    )
                )
            h = _HISTORY_RE.search(prose)
            if h:
                out.append(
                    self._finding(
                        node,
                        lineno,
                        CODE_HISTORY_NARRATION,
                        f"history narration '{h.group()}' in a layer that describes the present",
                        "describe the current behaviour; record why it changed in an ADR",
                    )
                )
        return out

    def _decisions(self, node: DocNode, decision_link: re.Pattern[str]) -> list[Finding]:
        out: list[Finding] = []
        paragraph: list[tuple[int, str]] = []

        def flush() -> None:
            text = " ".join(line for _, line in paragraph)
            if paragraph and not decision_link.search(text):
                for lineno, line in paragraph:
                    m = _DECISION_RE.search(_INLINE_CODE_RE.sub("", line))
                    if m:
                        out.append(
                            self._finding(
                                node,
                                lineno,
                                CODE_UNRECORDED_DECISION,
                                f"decision wording '{m.group()}' with no link to a decision record",
                                "record the choice in an ADR and link it from this paragraph",
                            )
                        )
            paragraph.clear()

        for lineno, line in _prose_lines(node.body, keep_blank=True):
            if not line.strip():
                flush()
            else:
                paragraph.append((lineno, line))
        flush()
        return out

    def _finding(
        self, node: DocNode, lineno: int, code: str, message: str, suggestion: str
    ) -> Finding:
        return Finding(
            check=self.name,
            code=code,
            category=code.split("/", 1)[1],
            severity=self.default_severity,
            message=message,
            path=node.path,
            doc_id=node.id,
            line=node.file_line(lineno),
            suggestion=suggestion,
        )


def _prose_lines(body: str, *, keep_blank: bool = False) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(body.splitlines(), 1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            if keep_blank:
                out.append((lineno, ""))
            continue
        if in_fence:
            continue
        if line.strip() or keep_blank:
            out.append((lineno, line))
    return out
