"""SupersessionCheck — a superseded doc is deprecated or removed.

A newer doc declares `supersedes: [old]`; the inverse is derived from that one list,
never written on the old doc. The check reports a `supersedes` entry that names no doc,
and an old doc that is still live, which `irminsul fix --confirm` deprecates. A doc already
`removed`, the step `stale-reaper` asks of an aged deprecated one, is past deprecated and
stays as it is.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Fix, Severity
from irminsul.docgraph import DocGraph, is_rfc
from irminsul.frontmatter import StatusEnum
from irminsul.frontmatter_edit import setter

CODE_STATUS_NOT_DEPRECATED = "supersession/status-not-deprecated"
CODE_UNKNOWN_SUPERSEDES = "supersession/unknown-supersedes"
_RETIRED = frozenset({StatusEnum.deprecated, StatusEnum.removed})


class SupersessionCheck:
    name: ClassVar[str] = "supersession"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNKNOWN_SUPERSEDES: (
            "A `supersedes` entry references a doc id that does not exist. Fix the id."
        ),
        CODE_STATUS_NOT_DEPRECATED: (
            "A doc named in another doc's `supersedes` is still live: it is not `status: "
            "deprecated` or `removed`. Set `status: deprecated` on the superseded doc."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNKNOWN_SUPERSEDES: FindingClass.certain,
        CODE_STATUS_NOT_DEPRECATED: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for new_doc in graph.nodes.values():
            if is_rfc(new_doc, graph.config):
                continue
            for old_id in new_doc.frontmatter.supersedes:
                old = graph.nodes.get(old_id)
                if old is None:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=(f"'supersedes' references unknown doc id '{old_id}'"),
                            path=new_doc.path,
                            doc_id=new_doc.id,
                            code=CODE_UNKNOWN_SUPERSEDES,
                        )
                    )
                    continue
                if is_rfc(old, graph.config):
                    continue

                if old.frontmatter.status not in _RETIRED:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=(
                                f"'{old_id}' is superseded by '{new_doc.id}' but "
                                f"status is '{old.frontmatter.status.value}'"
                            ),
                            path=old.path,
                            doc_id=old.id,
                            suggestion=f"set 'status: deprecated' in {old.path.as_posix()}",
                            code=CODE_STATUS_NOT_DEPRECATED,
                        )
                    )

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Deprecate each live superseded doc a `status-not-deprecated` finding names.

        Gated on that code, never merely on the doc, so an unknown-id finding on the
        same doc does not inherit fixability. It rewrites load-bearing metadata, so it is
        held behind `--confirm`.
        """
        flagged: set[tuple[Path | None, str | None]] = {
            (finding.path, finding.doc_id)
            for finding in findings
            if finding.code == CODE_STATUS_NOT_DEPRECATED
        }
        out: list[Fix] = []
        for new_doc in graph.nodes.values():
            if is_rfc(new_doc, graph.config):
                continue
            for old_id in new_doc.frontmatter.supersedes:
                old = graph.nodes.get(old_id)
                if old is None or is_rfc(old, graph.config):
                    continue
                if (old.path, old.id) not in flagged:
                    continue
                if old.frontmatter.status not in _RETIRED:
                    out.append(
                        Fix(
                            path=old.path,
                            description=(f"set status: deprecated in {old.path.as_posix()}"),
                            apply=setter("status", StatusEnum.deprecated.value),
                            requires_confirm=True,
                        )
                    )
        return out
