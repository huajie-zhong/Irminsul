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
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Fix, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import StatusEnum
from irminsul.frontmatter_edit import set_value

# Finding categories. `fixes()` keys on these, so the two with a remediation are
# named apart from the three without one.
_CAT_STATUS_NOT_DEPRECATED = "status-not-deprecated"
_CAT_MISSING_SUPERSEDED_BY = "missing-superseded-by"
_CAT_MISSING_SUPERSEDES = "missing-supersedes"
_CAT_UNKNOWN_SUPERSEDES = "unknown-supersedes"
_CAT_UNKNOWN_SUPERSEDED_BY = "unknown-superseded-by"

CODE_STATUS_NOT_DEPRECATED = f"supersession/{_CAT_STATUS_NOT_DEPRECATED}"
CODE_MISSING_SUPERSEDED_BY = f"supersession/{_CAT_MISSING_SUPERSEDED_BY}"
CODE_MISSING_SUPERSEDES = f"supersession/{_CAT_MISSING_SUPERSEDES}"
CODE_UNKNOWN_SUPERSEDES = f"supersession/{_CAT_UNKNOWN_SUPERSEDES}"
CODE_UNKNOWN_SUPERSEDED_BY = f"supersession/{_CAT_UNKNOWN_SUPERSEDED_BY}"


class SupersessionCheck:
    name: ClassVar[str] = "supersession"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNKNOWN_SUPERSEDES: (
            "A `supersedes` entry references a doc id that does not exist. Fix the id."
        ),
        CODE_STATUS_NOT_DEPRECATED: (
            "A doc named in another doc's `supersedes` is not itself `status: "
            "deprecated`. Set `status: deprecated` on the superseded doc."
        ),
        CODE_MISSING_SUPERSEDED_BY: (
            "A doc named in another doc's `supersedes` does not point back via "
            "`superseded_by`. Add `superseded_by:` on the superseded doc."
        ),
        CODE_UNKNOWN_SUPERSEDED_BY: (
            "A `superseded_by` entry references a doc id that does not exist. Fix the id."
        ),
        CODE_MISSING_SUPERSEDES: (
            "A doc claims `superseded_by` another doc, but that doc's `supersedes` "
            "list doesn't name it back. Add the id to the superseding doc's "
            "`supersedes`."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for new_doc in graph.nodes.values():
            if _is_rfc(new_doc):
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
                            category=_CAT_UNKNOWN_SUPERSEDES,
                        )
                    )
                    continue
                if _is_rfc(old):
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
                            code=CODE_STATUS_NOT_DEPRECATED,
                            category=_CAT_STATUS_NOT_DEPRECATED,
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
                            code=CODE_MISSING_SUPERSEDED_BY,
                            category=_CAT_MISSING_SUPERSEDED_BY,
                        )
                    )

        # Reverse direction: orphaned superseded_by pointers.
        for node in graph.nodes.values():
            if _is_rfc(node):
                continue
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
                        code=CODE_UNKNOWN_SUPERSEDED_BY,
                        category=_CAT_UNKNOWN_SUPERSEDED_BY,
                    )
                )
                continue
            if _is_rfc(target):
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
                        code=CODE_MISSING_SUPERSEDES,
                        category=_CAT_MISSING_SUPERSEDES,
                    )
                )

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Stamp the forward-superseded doc's deprecation metadata.

        Each fix is gated on the finding category it remediates, never merely on
        the doc: the reverse-pointer warning (stamped with the *superseding*
        doc's path/id) has no fix, and must not inherit fixability from a
        `status`/`superseded_by` finding that happens to name the same doc.
        """
        flagged = self._flagged_by_category(findings)
        if not flagged:
            return []

        out: list[Fix] = []
        for new_doc in graph.nodes.values():
            if _is_rfc(new_doc):
                continue
            for old_id in new_doc.frontmatter.supersedes:
                old = graph.nodes.get(old_id)
                if old is None or _is_rfc(old):
                    continue
                key = (old.path, old.id)

                if (
                    key in flagged[_CAT_STATUS_NOT_DEPRECATED]
                    and old.frontmatter.status != StatusEnum.deprecated
                ):
                    out.append(
                        Fix(
                            path=old.path,
                            description=(f"set status: deprecated in {old.path.as_posix()}"),
                            apply=_frontmatter_setter("status", StatusEnum.deprecated.value),
                        )
                    )

                if (
                    key in flagged[_CAT_MISSING_SUPERSEDED_BY]
                    and old.frontmatter.superseded_by != new_doc.id
                ):
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

    def _flagged_by_category(
        self, findings: list[Finding]
    ) -> dict[str, set[tuple[Path | None, str | None]]]:
        flagged: dict[str, set[tuple[Path | None, str | None]]] = {
            _CAT_STATUS_NOT_DEPRECATED: set(),
            _CAT_MISSING_SUPERSEDED_BY: set(),
        }
        for finding in findings:
            if finding.check != self.name or finding.severity != Severity.warning:
                continue
            if finding.category in flagged:
                flagged[finding.category].add((finding.path, finding.doc_id))
        return flagged if any(flagged.values()) else {}


def _frontmatter_setter(key: str, value: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return set_value(text, key, value)

    return apply


def _is_rfc(node: DocNode) -> bool:
    path = f"/{node.path.as_posix()}"
    return "/80-evolution/rfcs/" in path and node.path.name != "INDEX.md"
