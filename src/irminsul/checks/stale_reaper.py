"""StaleReaperCheck — deprecated docs that have aged past the threshold.

Once a doc is `status: deprecated`, the clock starts from the doc's own
last git commit time. After `deprecated_threshold_days` (default 180) the doc
is past due — either delete it, mark it `removed`, or rewrite and recommit.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul import clock
from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum
from irminsul.git.mtime import last_commit_time_any_repo


class StaleReaperCheck:
    name: ClassVar[str] = "stale-reaper"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        threshold = graph.config.checks.stale_reaper.deprecated_threshold_days
        today = clock.today(graph.now)

        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.status != StatusEnum.deprecated:
                continue

            doc_abs = graph.repo_root / node.path
            doc_gt = last_commit_time_any_repo(doc_abs, graph.repo_root)
            if doc_gt is None or doc_gt.when is None:
                continue

            age = (today - doc_gt.when.date()).days
            if age <= threshold:
                continue

            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(f"deprecated doc unrevisited for {age} days (threshold {threshold})"),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="remove the doc, set status: removed, or rewrite and recommit",
                )
            )

        return out
