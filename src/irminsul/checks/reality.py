"""RealityCheck — flag speculative language in tier-3 living docs."""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph

_SPECULATIVE_RE = re.compile(
    r"\b(planned|deferred|sprint|roadmap|future|upcoming|v\d+\.\d+)\b",
    re.IGNORECASE,
)


class RealityCheck:
    name: ClassVar[str] = "reality"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.tier != 3:
                continue
            for lineno, line in enumerate(node.body.splitlines(), 1):
                m = _SPECULATIVE_RE.search(line)
                if m:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=self.default_severity,
                            message=f"speculative keyword '{m.group()}' in living doc",
                            path=node.path,
                            doc_id=node.id,
                            line=lineno,
                            suggestion="Move future plans to an RFC or roadmap doc",
                        )
                    )
        return out
