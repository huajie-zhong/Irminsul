"""MtimeDriftCheck — flag docs whose `last_reviewed` lags behind their sources.

The drift signal is `max(last_commit_time(source))` vs the doc's own
`last_reviewed` claim. Using `last_reviewed` (rather than the doc's git mtime)
decouples the check from cosmetic edits — bumping the field is the explicit
"yes, I've re-read this" gesture.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.docgraph import DocGraph
from irminsul.git.mtime import last_commit_time_for_paths


class MtimeDriftCheck:
    name: ClassVar[str] = "mtime-drift"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        threshold = graph.config.overrides.mtime_drift_days
        source_files, _missing = walk_source_files(graph.repo_root, graph.config.paths.source_roots)

        out: list[Finding] = []
        today = _dt.date.today().isoformat()

        for node in graph.nodes.values():
            patterns = node.frontmatter.describes
            if not patterns:
                continue

            spec = GitIgnoreSpec.from_lines(patterns)
            matched = [Path(f) for f in source_files if spec.match_file(f)]
            if not matched:
                continue

            src_time = last_commit_time_for_paths(graph.repo_root, matched)
            if src_time.when is None:
                continue

            doc_reviewed = node.frontmatter.last_reviewed
            drift = src_time.when.date() - doc_reviewed
            if drift.days > threshold:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"source last touched {src_time.when.date().isoformat()}; "
                            f"doc last_reviewed {doc_reviewed.isoformat()} "
                            f"({drift.days} days drift, threshold {threshold})"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=f"bump last_reviewed to {today} or update the doc body",
                    )
                )

        return out
