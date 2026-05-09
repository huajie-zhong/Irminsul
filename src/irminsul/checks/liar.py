"""LiarCheck — tier-3 docs must not hand-document fields already in a T1 reference doc."""

from __future__ import annotations

import fnmatch
import re
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph

# Matches `identifier: Type` at the start of a line (0-4 leading spaces).
# Intentionally narrow: requires a non-whitespace word character after `:` to
# avoid matching bare `else:`, `try:`, or blank-value YAML lines.
_FIELD_DEF_RE = re.compile(r"^\s{0,4}\w[\w_]*\s*:\s+\w")


def _is_generated_path(posix_path: str, generated_globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(posix_path, g) for g in generated_globs)


class LiarCheck:
    name: ClassVar[str] = "liar"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        generated_globs = graph.config.tiers.generated

        # Map each source file → list of T1 doc IDs that describe it.
        t1_describes: dict[str, list[str]] = {}
        for node in graph.nodes.values():
            if _is_generated_path(node.path.as_posix(), generated_globs):
                for src in node.frontmatter.describes:
                    t1_describes.setdefault(src, []).append(node.id)

        if not t1_describes:
            return []

        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.tier != 3:
                continue

            overlapping_t1 = [
                t1_id for src in node.frontmatter.describes for t1_id in t1_describes.get(src, [])
            ]
            if not overlapping_t1:
                continue

            # Scan body for field-definition patterns inside code fences.
            in_fence = False
            fence_lang = ""
            field_lines: list[int] = []
            for lineno, line in enumerate(node.body.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("```"):
                    if not in_fence:
                        in_fence = True
                        fence_lang = stripped[3:].strip().lower()
                    else:
                        in_fence = False
                    continue
                if in_fence and fence_lang in ("", "python") and _FIELD_DEF_RE.match(line):
                    field_lines.append(lineno)

            if not field_lines:
                continue

            # Check for an outbound link from this T3 doc to any overlapping T1 doc.
            has_t1_link = any(
                node.id in graph.inbound_weak.get(t1_id, set()) for t1_id in overlapping_t1
            )
            if has_t1_link:
                continue

            t1_ref = ", ".join(overlapping_t1)
            for lineno in field_lines:
                out.append(
                    Finding(
                        check=self.name,
                        severity=self.default_severity,
                        message=(
                            f"tier-3 doc manually lists fields also covered by T1 reference "
                            f"({t1_ref}) without linking to it"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        line=lineno,
                        suggestion=f"Replace inline field docs with a link to [{overlapping_t1[0]}]",
                    )
                )

        return out
