"""StaleReaperCheck — deprecated docs that have aged past the threshold.

Once a doc is `status: deprecated`, the clock starts. After
`deprecated_threshold_days` (default 180) without a fresh `last_reviewed`, the
doc is past due — either delete it, mark it `removed`, or rewrite and re-review.
"""

from __future__ import annotations

import datetime as _dt
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum


class StaleReaperCheck:
    name: ClassVar[str] = "stale-reaper"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        threshold = graph.config.checks.stale_reaper.deprecated_threshold_days
        today = _dt.date.today()

        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.status != StatusEnum.deprecated:
                continue
            age = (today - node.frontmatter.last_reviewed).days
            if age <= threshold:
                continue
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(f"deprecated doc unrevisited for {age} days (threshold {threshold})"),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "remove the doc, set status: removed, or rewrite + bump last_reviewed"
                    ),
                )
            )

        return out
