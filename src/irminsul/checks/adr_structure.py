"""AdrStructureCheck — ADR body-structure invariants (RFC-0023).

Every doc with `audience: adr` should carry the conventional ADR sections so the
lifecycle checks that lean on ADR shape (RFC-0017's `resolved_by` / `## Status`
link, RFC-0018's `implements:` back-link) have something real to rely on.

The check verifies section *presence* only — it never inspects what a section
says. Heading matching is by kebab-case slug, so casing variants such as
`## Alternatives considered` satisfy the requirement.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import AudienceEnum

# (heading slug, display name) in conventional ADR order.
_REQUIRED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("status", "## Status"),
    ("context", "## Context"),
    ("decision", "## Decision"),
    ("alternatives-considered", "## Alternatives Considered"),
    ("consequences", "## Consequences"),
)


class AdrStructureCheck:
    name: ClassVar[str] = "adr-structure"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.audience != AudienceEnum.adr:
                continue
            present = {h.slug for h in graph.headings.get(node.id, [])}
            for slug, display in _REQUIRED_SECTIONS:
                if slug in present:
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        category="missing-section",
                        severity=Severity.warning,
                        message=f"ADR is missing a '{display}' section",
                        path=node.path,
                        doc_id=node.id,
                        suggestion=f"add a '{display}' section",
                    )
                )
        return out
