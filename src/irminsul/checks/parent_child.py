"""ParentChildCheck — INDEX.md structural invariants.

An INDEX.md auto-owns every sibling `.md` file in its folder. No explicit
`children:` declaration is required or supported.

Three concerns:

1. **Broad-globs ban** — once a parent INDEX has on-disk siblings, its
   `describes:` field must not contain wildcards. Children narrow coverage;
   wildcards on the parent risk silent overlap.
2. **Length cap** — INDEX bodies over `length_warning_lines` (default 300) get
   a warning. INDEX is meant to be navigation, not exposition.
3. **Unlisted siblings** — an INDEX owns every sibling, so it links to each one;
   a sibling it never links is navigation a reader cannot reach from the folder.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Fix, Severity
from irminsul.docgraph import DocGraph, DocNode

_WILDCARD_CHARS = set("*?[")
_LINK_BULLET_RE = re.compile(r"^\s*[-*+]\s+\[[^\]]+\]\([^)]+\)")


def _has_wildcard(pattern: str) -> bool:
    return any(c in pattern for c in _WILDCARD_CHARS)


CODE_WILDCARD_WITH_CHILDREN = "parent-child/wildcard-with-children"
CODE_INDEX_TOO_LONG = "parent-child/index-too-long"
CODE_UNLISTED_SIBLING = "parent-child/unlisted-sibling"


class ParentChildCheck:
    name: ClassVar[str] = "parent-child"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_WILDCARD_WITH_CHILDREN: (
            "A parent INDEX has on-disk sibling docs but still declares a wildcard "
            "`describes` pattern, risking silent overlap with the children's claims. "
            "Enumerate exact files, or drop the claim and let the children cover it."
        ),
        CODE_INDEX_TOO_LONG: (
            "An INDEX.md body exceeds the configured line threshold. INDEX is meant to "
            "be navigation, not exposition — move long-form content into a sibling doc."
        ),
        CODE_UNLISTED_SIBLING: (
            "A doc sits in a folder whose INDEX.md never links to it. Add a link from the "
            "INDEX, or move the doc to the folder it belongs in."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_WILDCARD_WITH_CHILDREN: FindingClass.hint,
        CODE_INDEX_TOO_LONG: FindingClass.hint,
        CODE_UNLISTED_SIBLING: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        length_threshold = graph.config.checks.parent_child.length_warning_lines

        out: list[Finding] = []

        for index_node in graph.nodes.values():
            if index_node.path.name != "INDEX.md":
                continue

            folder = index_node.path.parent

            on_disk_ids: set[str] = set()
            for path, child in graph.by_path.items():
                if path.parent == folder and path.name != "INDEX.md":
                    on_disk_ids.add(child.id)

            for child_id in sorted(on_disk_ids):
                if index_node.id not in graph.inbound_weak.get(child_id, set()):
                    child = graph.nodes[child_id]
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNLISTED_SIBLING,
                            severity=Severity.error,
                            message=f"INDEX does not link sibling doc '{child.path.name}'",
                            path=index_node.path,
                            doc_id=index_node.id,
                            suggestion=f"add a link to {child.path.name} in this INDEX",
                            category="unlisted-sibling",
                            data={"problem": "unlisted-sibling", "sibling": child_id},
                        )
                    )

            # Broad-globs ban: parents with siblings must claim narrowly.
            if on_disk_ids:
                for pattern in index_node.frontmatter.describes:
                    if _has_wildcard(pattern):
                        out.append(
                            Finding(
                                check=self.name,
                                code=CODE_WILDCARD_WITH_CHILDREN,
                                severity=Severity.warning,
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
                        code=CODE_INDEX_TOO_LONG,
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

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Append a navigation bullet for each unlisted sibling to its INDEX.

        It edits the INDEX body, so it is held behind `--confirm`.
        """
        out: list[Fix] = []
        for finding in findings:
            if finding.check != self.name or finding.category != "unlisted-sibling":
                continue
            index = graph.nodes.get(finding.doc_id or "")
            child = graph.nodes.get((finding.data or {}).get("sibling", ""))
            if index is None or child is None:
                continue
            out.append(
                Fix(
                    path=index.path,
                    description=f"link {child.path.name} from {index.path.as_posix()}",
                    apply=_bullet_adder(index, child),
                    requires_confirm=True,
                )
            )
        return out


def _bullet_adder(index: DocNode, child: DocNode) -> Callable[[str], str]:
    target = posixpath.relpath(child.path.as_posix(), index.path.parent.as_posix())
    title = child.frontmatter.summary or child.frontmatter.title

    def apply(text: str) -> str:
        return add_index_link(text, child.id, target, title)

    return apply


def _link_label(text: str) -> str:
    """`text` safe inside a markdown link label.

    A title holding a bracket used to close the label early, so `Foo] bar` wrote
    `- [Foo] bar](target)`: a broken link no run could repair, because the guard above
    sees `](target)` in the file and returns the text unchanged.
    """
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def add_index_link(text: str, doc_id: str, target: str, description: str) -> str:
    """Link a doc from an INDEX body: after its last link bullet, or at the end.

    Idempotent: an INDEX that already links `target` is returned unchanged.
    """
    if f"]({target})" in text:
        return text
    bullet = f"- [{_link_label(description or doc_id)}]({target})\n"
    lines = text.splitlines(keepends=True)
    bullets = [n for n, line in enumerate(lines) if _LINK_BULLET_RE.match(line)]
    if not bullets:
        sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return f"{text}{sep}{bullet}"
    last = bullets[-1]
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    lines.insert(last + 1, bullet)
    return "".join(lines)


def link_from_folder_index(doc_path: Path, doc_id: str, description: str) -> Path | None:
    """Add a new doc to the INDEX.md beside it, if there is one. Returns the INDEX it wrote."""
    index = doc_path.parent / "INDEX.md"
    if doc_path.name == "INDEX.md" or not index.is_file():
        return None
    text = index.read_text(encoding="utf-8")
    updated = add_index_link(text, doc_id, doc_path.name, description)
    if updated == text:
        return None
    index.write_text(updated, encoding="utf-8", newline="\n")
    return index
