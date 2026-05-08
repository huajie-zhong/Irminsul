"""ParentChildCheck — INDEX.md children registry consistency.

Three concerns rolled into one check (per Part VI §4.4 of the reference):

1. **Asymmetry** — every id listed under an INDEX.md's `children:` must exist
   on disk in the parent folder. Conversely, once a parent INDEX has *any*
   declared children, on-disk siblings that aren't listed are flagged as a
   warning so the registry stays a true index.
2. **Broad-globs ban** — once a parent INDEX has on-disk children, its
   `describes:` field must not contain wildcards. Children narrow coverage;
   wildcards on the parent risk silent overlap.
3. **Length cap** — INDEX bodies over `length_warning_lines` (default 300) get
   a warning. INDEX is meant to be navigation, not exposition.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph

_WILDCARD_CHARS = set("*?[")


def _has_wildcard(pattern: str) -> bool:
    return any(c in pattern for c in _WILDCARD_CHARS)


class ParentChildCheck:
    name: ClassVar[str] = "parent-child"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        length_threshold = graph.config.checks.parent_child.length_warning_lines

        out: list[Finding] = []

        for index_node in graph.nodes.values():
            if index_node.path.name != "INDEX.md":
                continue

            folder = index_node.path.parent
            declared = set(index_node.frontmatter.children)

            on_disk_ids: set[str] = set()
            for path, child in graph.by_path.items():
                if path.parent == folder and path.name != "INDEX.md":
                    on_disk_ids.add(child.id)

            extra_in_frontmatter = declared - on_disk_ids
            extra_on_disk = on_disk_ids - declared

            if extra_in_frontmatter:
                listed = ", ".join(sorted(extra_in_frontmatter))
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.error,
                        message=(f"'{index_node.id}.children' lists ids not on disk: {listed}"),
                        path=index_node.path,
                        doc_id=index_node.id,
                        suggestion="remove the entries or create the missing docs",
                    )
                )

            # Only flag asymmetry once the user has opted in to children
            # (declared non-empty). Many components are single-file; spamming
            # those is noise.
            if declared and extra_on_disk:
                listed = ", ".join(sorted(extra_on_disk))
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"on-disk siblings of {index_node.path.as_posix()} not "
                            f"listed in 'children': {listed}"
                        ),
                        path=index_node.path,
                        doc_id=index_node.id,
                        suggestion=f"add to {index_node.path.as_posix()}'s 'children': {listed}",
                    )
                )

            # Broad-globs ban: parents with children must claim narrowly.
            if on_disk_ids:
                for pattern in index_node.frontmatter.describes:
                    if _has_wildcard(pattern):
                        out.append(
                            Finding(
                                check=self.name,
                                severity=Severity.error,
                                message=(
                                    f"parent INDEX with children must not use wildcard "
                                    f"'describes' pattern: '{pattern}'"
                                ),
                                path=index_node.path,
                                doc_id=index_node.id,
                                suggestion=(
                                    "enumerate exact files, or remove the describes "
                                    "claim and let the children's claims cover it"
                                ),
                            )
                        )

            # Length cap.
            line_count = len(index_node.body.splitlines())
            if line_count > length_threshold:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"INDEX body is {line_count} lines (threshold "
                            f"{length_threshold}); INDEX should be navigation, "
                            "not exposition"
                        ),
                        path=index_node.path,
                        doc_id=index_node.id,
                        suggestion="move long-form content into a sibling doc",
                    )
                )

        return out
