"""FoundationReadinessCheck — foundation/architecture docs still on scaffold defaults.

`irminsul init --fresh` writes literal placeholder prompts into the foundation
and architecture docs. A project that moves into components and code while
those docs are still scaffold text has no real root intent. This check warns
when a doc under `00-foundation/` or `10-architecture/` still contains any of
the known scaffold placeholder phrases. It is advisory: a short foundation can
be valid, but a literal scaffold placeholder is not useful project intent.

The placeholder phrase set lives alongside the scaffolds in
`irminsul.init.placeholders`, so this check and the scaffolds stay in sync.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.init.placeholders import SCAFFOLD_PLACEHOLDER_PHRASES


class FoundationReadinessCheck:
    name: ClassVar[str] = "foundation-readiness"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        docs_root = graph.config.paths.docs_root.strip("/\\")
        foundation_prefixes = (
            f"{docs_root}/00-foundation/",
            f"{docs_root}/10-architecture/",
        )

        out: list[Finding] = []
        for node in graph.nodes.values():
            path_posix = node.path.as_posix()
            if not path_posix.startswith(foundation_prefixes):
                continue

            hit = next(
                (p for p in SCAFFOLD_PLACEHOLDER_PHRASES if p in node.body),
                None,
            )
            if hit is None:
                continue

            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"foundation doc '{node.id}' still contains scaffold "
                        f"placeholder text: {hit!r}"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "replace the scaffold prompts with real project intent, "
                        "or run `irminsul seed` to capture the project's "
                        "principle, idea, and belief"
                    ),
                )
            )

        return out
