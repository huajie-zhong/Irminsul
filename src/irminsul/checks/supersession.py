"""SupersessionCheck — `supersedes`/`superseded_by` reciprocity.

Emits findings when reciprocity is broken. For the deterministic forward case
(`new.supersedes = [old]`), it can also rewrite the old doc's frontmatter to
add `superseded_by:` and flip status.

Severity policy:
- Unknown id referenced from `supersedes` / `superseded_by` → **error** (the
  doc can't render meaningfully).
- Reciprocal pointer missing or `status` not `deprecated` → **warning** (the
  system still renders; metadata is just inconsistent).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from irminsul.checks.base import Finding, Fix, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum
from irminsul.frontmatter_edit import set_value


class SupersessionCheck:
    name: ClassVar[str] = "supersession"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for new_doc in graph.nodes.values():
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
                        )
                    )
                    continue

                if old.frontmatter.status != StatusEnum.deprecated:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=(
                                f"'{old_id}' is superseded by '{new_doc.id}' but "
                                f"status is '{old.frontmatter.status.value}'"
                            ),
                            path=old.path,
                            doc_id=old.id,
                            suggestion=f"set 'status: deprecated' in {old.path.as_posix()}",
                        )
                    )

                if old.frontmatter.superseded_by != new_doc.id:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=(
                                f"'{old_id}' is superseded by '{new_doc.id}' but "
                                f"'superseded_by' on {old.path.as_posix()} is "
                                f"{old.frontmatter.superseded_by!r}"
                            ),
                            path=old.path,
                            doc_id=old.id,
                            suggestion=f"add 'superseded_by: {new_doc.id}' to {old.path.as_posix()}",
                        )
                    )

        # Reverse direction: orphaned superseded_by pointers.
        for node in graph.nodes.values():
            sb = node.frontmatter.superseded_by
            if sb is None:
                continue
            target = graph.nodes.get(sb)
            if target is None:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.error,
                        message=f"'superseded_by' references unknown doc id '{sb}'",
                        path=node.path,
                        doc_id=node.id,
                    )
                )
                continue
            if node.id not in target.frontmatter.supersedes:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"'{node.id}' claims to be superseded by '{sb}' but "
                            f"{target.path.as_posix()} doesn't list it in 'supersedes'"
                        ),
                        path=target.path,
                        doc_id=target.id,
                        suggestion=f"add '{node.id}' to '{sb}.supersedes'",
                    )
                )

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        fixable = {
            (finding.path, finding.doc_id)
            for finding in findings
            if finding.check == self.name and finding.severity == Severity.warning
        }
        out: list[Fix] = []

        for new_doc in graph.nodes.values():
            for old_id in new_doc.frontmatter.supersedes:
                old = graph.nodes.get(old_id)
                if old is None or (old.path, old.id) not in fixable:
                    continue

                if old.frontmatter.status != StatusEnum.deprecated:
                    out.append(
                        Fix(
                            path=old.path,
                            description=(f"set status: deprecated in {old.path.as_posix()}"),
                            apply=_frontmatter_setter("status", StatusEnum.deprecated.value),
                        )
                    )

                if old.frontmatter.superseded_by != new_doc.id:
                    replacement = new_doc.id
                    out.append(
                        Fix(
                            path=old.path,
                            description=(
                                f"set superseded_by: {replacement} in {old.path.as_posix()}"
                            ),
                            apply=_frontmatter_setter("superseded_by", replacement),
                        )
                    )

        return out


def _frontmatter_setter(key: str, value: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return set_value(text, key, value)

    return apply
