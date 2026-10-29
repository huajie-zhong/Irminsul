"""FoundationReadinessCheck — foundation/architecture docs still holding scaffold prompts.

`irminsul init --fresh` writes prompts into the foundation and architecture docs, each
marked `<!-- irminsul:placeholder -->`. A project that moves into components and code while
those docs still carry a marked prompt has no real root intent, so a doc in either layer
that still carries a marker is reported. A short foundation can be valid; a prompt nobody
answered is not project intent.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, certain_severity
from irminsul.config import in_layer
from irminsul.docgraph import DocGraph
from irminsul.init.placeholders import placeholder_lines, without_marker

CODE_SCAFFOLD_PLACEHOLDER = "foundation-readiness/scaffold-placeholder"


class FoundationReadinessCheck:
    name: ClassVar[str] = "foundation-readiness"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_SCAFFOLD_PLACEHOLDER: (
            "A foundation or architecture doc still carries a scaffold prompt marked "
            "`<!-- irminsul:placeholder -->` by `irminsul init --fresh`. Replace the prompt "
            "with real project intent and delete its marker, or run `irminsul seed`."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_SCAFFOLD_PLACEHOLDER: FindingClass.certain,
    }
    drafts_exempt: ClassVar[frozenset[str]] = frozenset({CODE_SCAFFOLD_PLACEHOLDER})

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        out: list[Finding] = []
        for node in graph.nodes.values():
            path_posix = node.path.as_posix()
            if not (
                in_layer(graph.config, path_posix, "foundation")
                or in_layer(graph.config, path_posix, "architecture")
            ):
                continue
            covered = placeholder_lines(node.body)
            if not covered:
                continue
            first = covered[0]
            prompt = without_marker(node.body.splitlines()[first - 1]) or "a marked block"
            if len(prompt) > 80:
                prompt = prompt[:77] + "..."
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_SCAFFOLD_PLACEHOLDER,
                    severity=certain_severity(node),
                    message=(
                        f"foundation doc '{node.id}' still carries a scaffold prompt: {prompt!r}"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(first),
                    suggestion=(
                        "replace the marked prompts with real project intent and delete "
                        "their markers, or run `irminsul seed` to capture the project's "
                        "principle, idea, and belief"
                    ),
                )
            )

        return out
