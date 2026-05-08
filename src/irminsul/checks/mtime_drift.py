"""MtimeDriftCheck — flag docs whose `last_reviewed` lags behind their sources.

The drift signal is `max(last_commit_time(source))` vs the doc's own
`last_reviewed` claim. Using `last_reviewed` (rather than the doc's git mtime)
decouples the check from cosmetic edits — bumping the field is the explicit
"yes, I've re-read this" gesture.
"""

from __future__ import annotations

import datetime as _dt
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.docgraph import DocGraph
from irminsul.git.mtime import GitTime, last_commit_time_any_repo


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
            matched = [
                (abs_path, display)
                for abs_path, display in source_files
                if spec.match_file(display)
            ]
            if not matched:
                continue

            latest: GitTime = GitTime(sha=None, when=None)
            for abs_path, display in matched:
                gt = last_commit_time_any_repo(abs_path, graph.repo_root)
                if gt is None:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=f"cross-repo source file has no git history: '{display}' — cannot check mtime drift",
                            path=node.path,
                            doc_id=node.id,
                            suggestion="ensure the code repo has a .git directory at its root",
                        )
                    )
                    continue
                if gt.when is not None and (latest.when is None or gt.when > latest.when):
                    latest = gt

            if latest.when is None:
                continue

            doc_reviewed = node.frontmatter.last_reviewed
            drift = latest.when.date() - doc_reviewed
            if drift.days > threshold:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"source last touched {latest.when.date().isoformat()}; "
                            f"doc last_reviewed {doc_reviewed.isoformat()} "
                            f"({drift.days} days drift, threshold {threshold})"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=f"bump last_reviewed to {today} or update the doc body",
                    )
                )

        return out
