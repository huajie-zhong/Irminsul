"""MtimeDriftCheck — flag docs whose git mtime lags behind their sources.

The drift signal is `max(last_commit_time(source))` vs the doc file's own
last commit time. This is fully mechanical — no manually maintained field
can lie or go stale.
"""

from __future__ import annotations

from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_configured_source_files
from irminsul.docgraph import DocGraph
from irminsul.git.mtime import GitTime, last_commit_time_any_repo

CODE_NO_GIT_HISTORY = "mtime-drift/no-git-history"
CODE_DRIFT_DETECTED = "mtime-drift/drift-detected"


class MtimeDriftCheck:
    name: ClassVar[str] = "mtime-drift"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_NO_GIT_HISTORY: (
            "A cross-repo source file a doc claims has no git history, so drift can't be "
            "checked. Ensure the code repo has a `.git` directory at its root."
        ),
        CODE_DRIFT_DETECTED: (
            "A doc's claimed source was committed more recently than the doc itself, past "
            "the configured drift threshold. Update the doc body to re-align with the "
            "source changes."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        threshold = graph.config.overrides.mtime_drift_days
        source_files = walk_configured_source_files(graph.repo_root, graph.config).files

        out: list[Finding] = []

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
                            code=CODE_NO_GIT_HISTORY,
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

            doc_abs = graph.repo_root / node.path
            doc_gt = last_commit_time_any_repo(doc_abs, graph.repo_root)
            if doc_gt is None or doc_gt.when is None:
                continue

            drift = latest.when.date() - doc_gt.when.date()
            if drift.days > threshold:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_DRIFT_DETECTED,
                        severity=Severity.warning,
                        message=(
                            f"source last touched {latest.when.date().isoformat()}; "
                            f"doc last committed {doc_gt.when.date().isoformat()} "
                            f"({drift.days} days drift, threshold {threshold})"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="update the doc body to re-align with source changes",
                    )
                )

        return out
